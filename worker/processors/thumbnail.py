"""Gera thumbnail de pôsteres."""
from io import BytesIO
from PIL import Image


def gerar_thumbnail(imagem_bytes: bytes, return_bytes: bool = False):
    """
    Gera thumbnail 300x450 de uma imagem.

    Args:
        imagem_bytes: Conteúdo da imagem original
        return_bytes: Se True, retorna os bytes do thumbnail; se False, retorna apenas tamanhos

    Returns:
        Se return_bytes=True: bytes do thumbnail JPEG
        Se return_bytes=False: tupla (tamanho_original, tamanho_final)
    """
    img = Image.open(BytesIO(imagem_bytes)).convert('RGB')
    tamanho_original = img.size

    img.thumbnail((300, 450))
    tamanho_final = img.size

    buf = BytesIO()
    img.save(buf, 'JPEG', quality=85)
    thumb_bytes = buf.getvalue()

    if return_bytes:
        return thumb_bytes
    return tamanho_original, tamanho_final
