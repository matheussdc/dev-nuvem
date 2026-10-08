"""Ingresso em PDF desenhado com Pillow: uma página por assento, no visual do app."""
import textwrap
from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

FUNDO, CARTAO, BORDA = (11, 19, 34), (16, 27, 46), (29, 44, 70)
TEXTO, MUDO, DESTAQUE = (232, 238, 248), (127, 139, 163), (43, 140, 240)
LARGURA, ALTURA = 1800, 760
FONTES = "/usr/share/fonts/truetype/dejavu/"  # pacote fonts-dejavu-core (backend.sh instala)


@lru_cache
def _fonte(tamanho, negrito=False):
    try:
        return ImageFont.truetype(FONTES + ("DejaVuSans-Bold.ttf" if negrito else "DejaVuSans.ttf"), tamanho)
    except OSError:
        return ImageFont.load_default(size=tamanho)  # fallback sem acentos


def _brl(valor):
    return f"R$ {float(valor):.2f}".replace(".", ",")


def _duracao(minutos):
    return f"{minutos // 60}h {minutos % 60}min" if minutos else ""


def _pagina(poster, filme, sessao, ingresso):
    img = Image.new("RGB", (LARGURA, ALTURA), FUNDO)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((20, 20, LARGURA - 20, ALTURA - 20), radius=36, fill=CARTAO)

    if poster:
        p = poster.copy()
        p.thumbnail((440, 660))
        img.paste(p, (60 + (440 - p.width) // 2, (ALTURA - p.height) // 2))

    x = 560
    d.text((x, 70), "CINEMATIX  ·  INGRESSO", font=_fonte(26, True), fill=DESTAQUE)
    y = 118
    for linha in textwrap.wrap(filme.titulo, 22)[:2]:
        d.text((x, y), linha, font=_fonte(56, True), fill=TEXTO)
        y += 70
    meta = "  ·  ".join(filter(None, [str(filme.ano or ""), _duracao(filme.duracao_min)]))
    d.text((x, y + 8), meta, font=_fonte(28), fill=MUDO)

    campos = [(0, "DATA", sessao.data.strftime("%d/%m/%Y")), (290, "HORÁRIO", sessao.hora.strftime("%H:%M")),
              (490, "FILEIRA", ingresso.assento[0]), (660, "ASSENTO", ingresso.assento[1:].zfill(2))]
    for dx, rotulo, valor in campos:
        d.text((x + dx, 400), rotulo, font=_fonte(22), fill=MUDO)
        d.text((x + dx, 435), valor, font=_fonte(40, True), fill=TEXTO)
    d.text((x, 545), "COMPRADOR", font=_fonte(22), fill=MUDO)
    d.text((x, 580), ingresso.nome[:28], font=_fonte(32), fill=TEXTO)
    d.text((x + 660, 545), "VALOR", font=_fonte(22), fill=MUDO)
    d.text((x + 660, 580), _brl(sessao.preco), font=_fonte(32), fill=TEXTO)

    # canhoto destacável
    cx = LARGURA - 330
    for yy in range(50, ALTURA - 50, 26):
        d.line((cx, yy, cx, yy + 13), fill=BORDA, width=3)
    centro = cx + 150
    d.text((centro, 230), "ASSENTO", anchor="mm", font=_fonte(24), fill=MUDO)
    d.text((centro, 330), ingresso.assento, anchor="mm", font=_fonte(110, True), fill=DESTAQUE)
    d.text((centro, 460), f"Nº {ingresso.id:06d}", anchor="mm", font=_fonte(30), fill=TEXTO)
    d.text((centro, 510), sessao.data.strftime("%d/%m") + "  " + sessao.hora.strftime("%H:%M"),
           anchor="mm", font=_fonte(26), fill=MUDO)
    return img


def gerar_pdf(poster_bytes, linhas):
    """linhas: [(Ingresso, Sessao, Filme)]. Sem pôster legível, o ingresso sai sem a imagem."""
    poster = None
    if poster_bytes:
        try:
            poster = Image.open(BytesIO(poster_bytes)).convert("RGB")
        except OSError:
            pass
    paginas = [_pagina(poster, f, s, i) for i, s, f in linhas]
    buf = BytesIO()
    paginas[0].save(buf, "PDF", resolution=200, save_all=True, append_images=paginas[1:])
    return buf.getvalue()
