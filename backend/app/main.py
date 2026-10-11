import hmac
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
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
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

    novos = [Ingresso(sessao_id=c.sessao_id, assento=a, nome=c.nome, email=c.email) for a in escolhidos]
    db.add_all(novos)
    commit(db, "Um dos assentos já foi vendido")
    cache.delete(*chaves)

    # Recarrega os ingressos com IDs gerados
    db.refresh(novos[0])
    for i in novos[1:]:
        db.refresh(i)

    total = float(sessao.preco) * len(escolhidos)
    ids = sorted(i.id for i in novos)

    log("CREATE", "ingresso", {
        "ids": ids, "sessao_id": c.sessao_id, "assentos": escolhidos,
        "nome": c.nome, "email": c.email, "total": total
    })

    # === NOVO: Publica no SNS para o worker gerar o PDF ===
    filme = db.get(Filme, sessao.filme_id)
    linhas_pdf = [
        {
            "ingresso": {
                "id": i.id,
                "assento": i.assento,
                "nome": i.nome,
                "email": i.email,
            },
            "sessao": {
                "data": sessao.data.isoformat(),
                "hora": sessao.hora.strftime("%H:%M"),
                "preco": float(sessao.preco),
            },
            "filme": {
                "titulo": filme.titulo,
                "ano": filme.ano,
                "duracao_min": filme.duracao_min,
            },
        }
        for i in novos
    ]

    lista_ids = ",".join(map(str, ids))
    pdf_key = f"ingressos/pdf/{assinatura(lista_ids)}.pdf"

    sns.publish(
        TopicArn=settings.SNS_TOPIC_ARN,
        Subject="Gerar PDF de ingresso",
        Message=json.dumps({
            "action": "generate_pdf",
            "pdf_key": pdf_key,
            "poster_key": filme.poster_key,
            "linhas": linhas_pdf,
        })
    )

    log("CREATE", "ingresso_pdf", {
        "pdf_key": pdf_key,
        "ingressos_ids": ids,
        "status": "pending"
    })

    return {
        "ok": True,
        "assentos": escolhidos,
        "total": total,
        "pdf_url": f"/ingressos/pdf?ids={lista_ids}&token={assinatura(lista_ids)}"
    }


@app.get("/ingressos/pdf")
def ingresso_pdf(ids: str, token: str, db: Session = Depends(get_db)):
    if not hmac.compare_digest(token, assinatura(ids)):
        raise HTTPException(403, "Link de ingresso inválido")

    pdf_key = f"ingressos/pdf/{token}.pdf"

    # Tenta buscar do S3 (gerado pelo worker)
    try:
        obj = s3.get_object(Bucket=settings.S3_BUCKET, Key=pdf_key)
        pdf_bytes = obj['Body'].read()
        log("READ", "ingresso_pdf", {"ids": ids, "source": "s3"})
        return Response(
            pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="ingresso-cinematix-{ids.split(",")[0]}.pdf"'}
        )
    except s3.exceptions.NoSuchKey:
        # PDF ainda não foi gerado pelo worker
        log("READ", "ingresso_pdf", {"ids": ids, "status": "pending"})
        raise HTTPException(
            202,
            "PDF ainda está sendo gerado. Tente novamente em alguns segundos.",
            headers={"Retry-After": "3"}
        )
