"""Popula o banco com os filmes de backend/seed/filmes.json e sessões para 14 dias.

Uso (de dentro de backend/, com o .env preenchido):  python -m app.seed
"""
import json
import mimetypes
from datetime import date, time, timedelta
from pathlib import Path

from app.database import Base, Filme, SessionLocal, Sessao, engine
from app.main import invalidar_catalogo, log, salvar_poster

SEED = Path(__file__).resolve().parent.parent / "seed"
HORARIOS = [time(13, 30), time(16, 15), time(19, 0), time(21, 45)]
DIAS = 14


def main():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(Filme).count():
            print("O banco já tem filmes; nada a fazer.")
            return
        for i, dados in enumerate(json.loads((SEED / "filmes.json").read_text(encoding="utf-8"))):
            arquivo = SEED / "posters" / dados.pop("poster")
            tipo = mimetypes.guess_type(arquivo.name)[0] or "image/jpeg"
            filme = Filme(**dados, poster_key=salvar_poster(arquivo.read_bytes(), tipo, arquivo.name))
            db.add(filme)
            db.flush()
            # Cada filme fica com 3 dos 4 horários; matinê mais barata.
            horarios = [h for j, h in enumerate(HORARIOS) if j != i % len(HORARIOS)]
            db.add_all(Sessao(filme_id=filme.id, data=date.today() + timedelta(days=d), hora=h,
                              preco=22 if h.hour < 17 else 30)
                       for d in range(DIAS) for h in horarios)
            db.commit()
            log("CREATE", "filme", {**dados, "id": filme.id, "poster_key": filme.poster_key,
                                    "sessoes_criadas": DIAS * len(horarios), "origem": "seed"})
            print(f"{filme.titulo}: {DIAS * len(horarios)} sessões")
    invalidar_catalogo()


if __name__ == "__main__":
    main()
