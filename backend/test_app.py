"""Teste de fumaça da API com Postgres e Redis reais e AWS (S3/SNS/DynamoDB) falsa.

Uso, de dentro de backend/:
    DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres \
    REDIS_URL=redis://localhost:6379 python test_app.py
Requer httpx (pip install httpx). APAGA os dados do banco apontado.
"""
import os

assert "amazonaws.com" not in os.environ["DATABASE_URL"], "não rode este teste contra o RDS"
for k, v in {"S3_BUCKET": "teste", "SNS_TOPIC_ARN": "arn:aws:sns:us-east-1:0:t", "ADMIN_TOKEN": "segredo"}.items():
    os.environ.setdefault(k, v)

from fastapi.testclient import TestClient  # noqa: E402

import app.main as m  # noqa: E402


class FakeAWS:
    def __init__(self):
        self.chamadas = []

    def __getattr__(self, nome):
        def chamada(**kw):
            self.chamadas.append((nome, kw))
            return {"Items": []}
        return chamada


m.s3, m.sns, m.logs = FakeAWS(), FakeAWS(), FakeAWS()
A = {"X-Admin-Token": "segredo"}
POSTER = {"poster": ("p.jpg", b"img", "image/jpeg")}

with TestClient(m.app) as c:
    with m.engine.begin() as conn:
        conn.exec_driver_sql("TRUNCATE ingressos, sessoes, filmes RESTART IDENTITY CASCADE")
    m.cache.flushdb()

    # admin exige senha
    assert c.post("/admin/filmes", data={"titulo": "X"}, files=POSTER).status_code == 401

    # CRUD filme + pôster vai para S3 e SNS
    f = c.post("/admin/filmes", headers=A, data={"titulo": "Filme", "ano": "2025"}, files=POSTER).json()
    assert "/thumbs/" in f["thumb_url"] and f["thumb_url"].endswith(".jpg")
    assert [n for n, _ in m.sns.chamadas] == ["publish"]
    s = c.post("/admin/sessoes", headers=A, json={"filme_id": f["id"], "data": "2026-10-10", "hora": "19:00", "preco": 30}).json()

    # catálogo com cache
    cat = c.get("/catalogo").json()
    assert cat["filmes"][0]["sessoes"][0]["id"] == s["id"]
    assert m.cache.get("catalogo") and c.get("/catalogo").json() == cat

    # reserva temporária no Redis
    url = f"/sessoes/{s['id']}/reservas"
    assert c.post(url, json={"assento": "B8", "client_id": "cliente-a1"}).status_code == 200
    assert c.post(url, json={"assento": "B8", "client_id": "cliente-a1"}).status_code == 200  # própria reserva
    assert c.post(url, json={"assento": "B8", "client_id": "cliente-b2"}).status_code == 409
    assert c.post(url, json={"assento": "Z99", "client_id": "cliente-a1"}).status_code == 422
    assert 0 < m.cache.ttl(m.chave(s["id"], "B8")) <= 300
    mapa = c.get(f"/sessoes/{s['id']}/assentos?client_id=cliente-b2").json()
    assert mapa == {"vendidos": [], "reservados": ["B8"], "meus": []}

    # compra só com reserva própria
    compra = {"sessao_id": s["id"], "assentos": ["B8"], "nome": "Ana", "email": "ana@x.com"}
    assert c.post("/compras", json={**compra, "client_id": "cliente-b2"}).status_code == 409
    r = c.post("/compras", json={**compra, "client_id": "cliente-a1"})
    assert r.status_code == 200 and r.json()["total"] == 30
    assert c.get(f"/sessoes/{s['id']}/assentos").json()["vendidos"] == ["B8"]
    assert c.post(url, json={"assento": "B8", "client_id": "cliente-b2"}).status_code == 409

    # UNIQUE no banco segura mesmo com reserva forjada no Redis
    m.cache.set(m.chave(s["id"], "B8"), "cliente-b2")
    assert c.post("/compras", json={**compra, "client_id": "cliente-b2"}).status_code == 409

    # liberar só a própria reserva
    c.post(url, json={"assento": "C1", "client_id": "cliente-a1"})
    c.delete(f"{url}/C1?client_id=cliente-b2")
    assert m.cache.get(m.chave(s["id"], "C1")) == "cliente-a1"
    c.delete(f"{url}/C1?client_id=cliente-a1")
    assert m.cache.get(m.chave(s["id"], "C1")) is None

    # exclusão bloqueada com venda; update funciona e invalida o cache
    assert c.delete(f"/admin/sessoes/{s['id']}", headers=A).status_code == 409
    assert c.delete(f"/admin/filmes/{f['id']}", headers=A).status_code == 409
    assert c.put(f"/admin/filmes/{f['id']}", headers=A, data={"titulo": "Novo"}).json()["titulo"] == "Novo"
    assert m.cache.get("catalogo") is None

    # filme sem vendas sai junto com as sessões
    f2 = c.post("/admin/filmes", headers=A, data={"titulo": "Outro"}, files=POSTER).json()
    c.post("/admin/sessoes", headers=A, json={"filme_id": f2["id"], "data": "2026-10-11", "hora": "14:00", "preco": 22})
    assert c.delete(f"/admin/filmes/{f2['id']}", headers=A).status_code == 200
    assert [x["id"] for x in c.get("/catalogo").json()["filmes"]] == [f["id"]]

    assert len(c.get("/admin/ingressos", headers=A).json()) == 1
    acoes = {kw["Item"]["acao"] for n, kw in m.logs.chamadas if n == "put_item"}
    assert {"CREATE", "READ", "UPDATE", "DELETE"} <= acoes, acoes

print("ok")
