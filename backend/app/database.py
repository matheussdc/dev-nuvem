from datetime import datetime

from sqlalchemy import (Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time,
                        UniqueConstraint, create_engine)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Filme(Base):
    __tablename__ = "filmes"
    id = Column(Integer, primary_key=True)
    titulo = Column(String(200), nullable=False)
    ano = Column(Integer)
    duracao_min = Column(Integer)
    sinopse = Column(Text, default="")
    imdb = Column(String(20), default="")
    letterboxd = Column(String(20), default="")
    critica = Column(String(20), default="")
    poster_key = Column(String(300))


class Sessao(Base):
    __tablename__ = "sessoes"
    id = Column(Integer, primary_key=True)
    # Excluir um filme apaga as sessões dele; o FK de ingressos bloqueia se houver venda.
    filme_id = Column(Integer, ForeignKey("filmes.id", ondelete="CASCADE"), nullable=False, index=True)
    data = Column(Date, nullable=False)
    hora = Column(Time, nullable=False)
    preco = Column(Numeric(8, 2), nullable=False)


class Ingresso(Base):
    __tablename__ = "ingressos"
    id = Column(Integer, primary_key=True)
    sessao_id = Column(Integer, ForeignKey("sessoes.id", ondelete="RESTRICT"), nullable=False)
    assento = Column(String(3), nullable=False)  # ex.: "B8"
    nome = Column(String(120), nullable=False)
    email = Column(String(200), nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)
    # Garantia final contra venda duplicada, mesmo se a reserva no Redis falhar.
    __table_args__ = (UniqueConstraint("sessao_id", "assento"),)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
