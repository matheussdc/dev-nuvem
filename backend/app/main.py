import json
import os
import secrets
import socket
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timezone
from typing import Annotated, List, Optional

import boto3
import redis
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, Filme, Ingresso, Sessao, engine, get_db

s3 = boto3.client("s3", region_name=settings.AWS_REGION)
sns = boto3.client("sns", region_name=settings.AWS_REGION)
logs = boto3.resource("dynamodb", region_name=settings.AWS_REGION).Table(settings.DYNAMO_TABLE)
cache = redis.from_url(settings.REDIS_URL, decode_responses=True)

S3_URL = f"https://{settings.S3_BUCKET}.s3.amazonaws.com/"
FILEIRAS, LUGARES = "ABCDEFG", 16
ASSENTO = r"^[A-G](1[0-6]|[1-9])$"
RESERVA_TTL = 300  # 5 min
ClientId = Annotated[str, Field(min_length=8, max_length=64)]


@asynccontextmanager
async def lifespan(_):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Cinematix", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------- utilitários ----------

def log(acao: str, entidade: str, dados: dict):
    logs.put_item(Item={
        "id": str(uuid.uuid4()),
        "acao": acao,
        "entidade": entidade,
        "dados": json.dumps(dados, default=str, ensure_ascii=False),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def admin(x_admin_token: str = Header("")):
    if not secrets.compare_digest(x_admin_token, settings.ADMIN_TOKEN):
        raise HTTPException(401, "Senha do admin inválida")


def commit(db: Session, erro: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, erro)


def thumb_key(poster_key: str) -> str:
    return "thumbs/" + poster_key.rsplit("/", 1)[-1].rsplit(".", 1)[0] + ".jpg"


def salvar_poster(conteudo: bytes, content_type: str, filename: str) -> str:
    """Grava o original no S3 e pede o thumbnail ao worker via SNS."""
    if not content_type.startswith("image/"):
        raise HTTPException(400, "O pôster precisa ser uma imagem")
    key = f"posters/{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower() or '.jpg'}"
    s3.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=conteudo, ContentType=content_type)
    sns.publish(TopicArn=settings.SNS_TOPIC_ARN, Subject="Thumbnail de pôster",
                Message=json.dumps({"action": "thumbnail", "key": key, "thumb_key": thumb_key(key)}))
    return key


def filme_json(f: Filme) -> dict:
    return {
        "id": f.id, "titulo": f.titulo, "ano": f.ano, "duracao_min": f.duracao_min, "sinopse": f.sinopse,
        "imdb": f.imdb, "letterboxd": f.letterboxd, "critica": f.critica,
        "poster_url": S3_URL + f.poster_key if f.poster_key else None,
        "thumb_url": S3_URL + thumb_key(f.poster_key) if f.poster_key else None,
    }


def sessao_json(s: Sessao) -> dict:
    return {"id": s.id, "filme_id": s.filme_id, "data": s.data.isoformat(),
            "hora": s.hora.strftime("%H:%M"), "preco": float(s.preco)}


def chave(sid: int, assento: str) -> str:
    return f"reserva:{sid}:{assento}"


def invalidar_catalogo():
    cache.delete("catalogo")


# ---------- público ----------

@app.get("/health")
def health():
    return {"status": "healthy", "instancia": socket.gethostname()}


@app.get("/catalogo")
def catalogo(db: Session = Depends(get_db)):
    """Filmes com suas sessões. Consulta mais frequente do app, fica no Redis."""
    cached = cache.get("catalogo")
    if cached:
        log("READ", "catalogo", {"cache": "hit"})
        return json.loads(cached)
    sessoes = db.scalars(select(Sessao).order_by(Sessao.data, Sessao.hora)).all()
    filmes = [
        {**filme_json(f), "sessoes": [sessao_json(s) for s in sessoes if s.filme_id == f.id]}
        for f in db.scalars(select(Filme).order_by(Filme.id))
    ]
    resultado = {"filmes": filmes}
    cache.setex("catalogo", 300, json.dumps(resultado))
    log("READ", "catalogo", {"cache": "miss"})
    return resultado


@app.get("/sessoes/{sid}/assentos")
def assentos(sid: int, client_id: str = "", db: Session = Depends(get_db)):
    vendidos = db.scalars(select(Ingresso.assento).where(Ingresso.sessao_id == sid)).all()
    todos = [f"{f}{n}" for f in FILEIRAS for n in range(1, LUGARES + 1)]
    donos = cache.mget([chave(sid, a) for a in todos])
    return {
        "vendidos": vendidos,
        "reservados": [a for a, d in zip(todos, donos) if d and d != client_id],
        "meus": [a for a, d in zip(todos, donos) if d and d == client_id],
    }


class ReservaIn(BaseModel):
    assento: str = Field(pattern=ASSENTO)
    client_id: ClientId


@app.post("/sessoes/{sid}/reservas")
def reservar(sid: int, r: ReservaIn, db: Session = Depends(get_db)):
    if not db.get(Sessao, sid):
        raise HTTPException(404, "Sessão não encontrada")
    if db.scalar(select(Ingresso.id).where(Ingresso.sessao_id == sid, Ingresso.assento == r.assento)):
        raise HTTPException(409, "Assento já vendido")
    k = chave(sid, r.assento)
    if not cache.set(k, r.client_id, nx=True, ex=RESERVA_TTL) and cache.get(k) != r.client_id:
        raise HTTPException(409, "Assento reservado por outra pessoa")
    return {"ok": True, "expira_em": RESERVA_TTL}


@app.delete("/sessoes/{sid}/reservas/{assento}")
def liberar(sid: int, assento: str, client_id: str):
    k = chave(sid, assento)
    # ponytail: GET + DEL não é atômico; troque por um script Lua se a corrida virar problema
    if cache.get(k) == client_id:
        cache.delete(k)
    return {"ok": True}


class CompraIn(BaseModel):
    sessao_id: int
    assentos: List[Annotated[str, Field(pattern=ASSENTO)]] = Field(min_length=1, max_length=10)
    nome: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)
    client_id: ClientId


@app.post("/compras")
def comprar(c: CompraIn, db: Session = Depends(get_db)):
    sessao = db.get(Sessao, c.sessao_id)
    if not sessao:
        raise HTTPException(404, "Sessão não encontrada")
    escolhidos = sorted(set(c.assentos))
    chaves = [chave(c.sessao_id, a) for a in escolhidos]
    if any(dono != c.client_id for dono in cache.mget(chaves)):
        raise HTTPException(409, "Sua reserva expirou. Selecione os assentos de novo.")
    db.add_all([Ingresso(sessao_id=c.sessao_id, assento=a, nome=c.nome, email=c.email) for a in escolhidos])
    commit(db, "Um dos assentos já foi vendido")
    cache.delete(*chaves)
    total = float(sessao.preco) * len(escolhidos)
    log("CREATE", "ingresso", {"sessao_id": c.sessao_id, "assentos": escolhidos, "nome": c.nome,
                               "email": c.email, "total": total})
    return {"ok": True, "assentos": escolhidos, "total": total}


# ---------- admin: filmes ----------

def filme_form(
    titulo: str = Form(..., min_length=1, max_length=200),
    ano: Optional[int] = Form(None),
    duracao_min: Optional[int] = Form(None),
    sinopse: str = Form(""),
    imdb: str = Form("", max_length=20),
    letterboxd: str = Form("", max_length=20),
    critica: str = Form("", max_length=20),
) -> dict:
    return dict(titulo=titulo, ano=ano, duracao_min=duracao_min, sinopse=sinopse,
                imdb=imdb, letterboxd=letterboxd, critica=critica)


@app.post("/admin/filmes", dependencies=[Depends(admin)])
def criar_filme(dados: dict = Depends(filme_form), poster: UploadFile = File(...),
                db: Session = Depends(get_db)):
    filme = Filme(**dados, poster_key=salvar_poster(poster.file.read(), poster.content_type or "",
                                                    poster.filename or ""))
    db.add(filme)
    commit(db, "Erro ao salvar filme")
    invalidar_catalogo()
    log("CREATE", "filme", {**dados, "id": filme.id, "poster_key": filme.poster_key})
    return filme_json(filme)


@app.put("/admin/filmes/{fid}", dependencies=[Depends(admin)])
def editar_filme(fid: int, dados: dict = Depends(filme_form), poster: Optional[UploadFile] = File(None),
                 db: Session = Depends(get_db)):
    filme = db.get(Filme, fid)
    if not filme:
        raise HTTPException(404, "Filme não encontrado")
    for campo, valor in dados.items():
        setattr(filme, campo, valor)
    if poster and poster.filename:
        # ponytail: o pôster antigo fica órfão no S3; apague-o aqui se o custo de storage importar
        filme.poster_key = salvar_poster(poster.file.read(), poster.content_type or "", poster.filename)
    commit(db, "Erro ao salvar filme")
    invalidar_catalogo()
    log("UPDATE", "filme", {**dados, "id": fid, "poster_key": filme.poster_key})
    return filme_json(filme)


@app.delete("/admin/filmes/{fid}", dependencies=[Depends(admin)])
def excluir_filme(fid: int, db: Session = Depends(get_db)):
    filme = db.get(Filme, fid)
    if not filme:
        raise HTTPException(404, "Filme não encontrado")
    dados = filme_json(filme)
    db.delete(filme)
    commit(db, "Este filme tem ingressos vendidos e não pode ser excluído")
    invalidar_catalogo()
    log("DELETE", "filme", dados)
    return {"ok": True}


# ---------- admin: sessões ----------

class SessaoIn(BaseModel):
    filme_id: int
    data: date
    hora: time
    preco: float = Field(gt=0, lt=1000)


@app.post("/admin/sessoes", dependencies=[Depends(admin)])
def criar_sessao(s: SessaoIn, db: Session = Depends(get_db)):
    sessao = Sessao(**s.model_dump())
    db.add(sessao)
    commit(db, "Filme inexistente")
    invalidar_catalogo()
    log("CREATE", "sessao", sessao_json(sessao))
    return sessao_json(sessao)


@app.put("/admin/sessoes/{sid}", dependencies=[Depends(admin)])
def editar_sessao(sid: int, s: SessaoIn, db: Session = Depends(get_db)):
    sessao = db.get(Sessao, sid)
    if not sessao:
        raise HTTPException(404, "Sessão não encontrada")
    for campo, valor in s.model_dump().items():
        setattr(sessao, campo, valor)
    commit(db, "Filme inexistente")
    invalidar_catalogo()
    log("UPDATE", "sessao", sessao_json(sessao))
    return sessao_json(sessao)


@app.delete("/admin/sessoes/{sid}", dependencies=[Depends(admin)])
def excluir_sessao(sid: int, db: Session = Depends(get_db)):
    sessao = db.get(Sessao, sid)
    if not sessao:
        raise HTTPException(404, "Sessão não encontrada")
    dados = sessao_json(sessao)
    db.delete(sessao)
    commit(db, "Esta sessão tem ingressos vendidos e não pode ser excluída")
    invalidar_catalogo()
    log("DELETE", "sessao", dados)
    return {"ok": True}


# ---------- admin: consultas e stress ----------

@app.get("/admin/ingressos", dependencies=[Depends(admin)])
def listar_ingressos(db: Session = Depends(get_db)):
    linhas = db.execute(
        select(Ingresso, Sessao, Filme.titulo)
        .join(Sessao, Ingresso.sessao_id == Sessao.id)
        .join(Filme, Sessao.filme_id == Filme.id)
        .order_by(Ingresso.id.desc()).limit(200)
    ).all()
    return [{"id": i.id, "filme": titulo, "data": s.data.isoformat(), "hora": s.hora.strftime("%H:%M"),
             "assento": i.assento, "nome": i.nome, "email": i.email, "preco": float(s.preco),
             "criado_em": i.criado_em.isoformat()} for i, s, titulo in linhas]


@app.get("/admin/logs", dependencies=[Depends(admin)])
def listar_logs():
    # ponytail: scan da tabela inteira; crie um GSI por data se a tabela crescer
    itens, kwargs = [], {}
    while True:
        r = logs.scan(**kwargs)
        itens += r["Items"]
        if "LastEvaluatedKey" not in r:
            break
        kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    return sorted(itens, key=lambda i: i.get("timestamp", ""), reverse=True)[:100]


@app.post("/admin/stress", dependencies=[Depends(admin)])
def stress(segundos: int = 120):
    """Ocupa todas as vCPUs desta instância para disparar o Auto Scaling."""
    segundos = max(1, min(segundos, 600))
    codigo = f"import time\nt = time.time() + {segundos}\nwhile time.time() < t: pass"
    cpus = os.cpu_count() or 1
    for _ in range(cpus):
        subprocess.Popen([sys.executable, "-c", codigo])
    return {"instancia": socket.gethostname(), "cpus": cpus, "segundos": segundos}
