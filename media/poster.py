import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = BASE_DIR / "templates" / "poster_base.png"
FONT_PATH = BASE_DIR / "templates" / "Montserrat-Bold.ttf"

BOX = (994, 2580, 1423, 2680)  # x0, y0, x1, y1
CENTRO = (1208, 2630)
FONT_SIZE_INIZIALE = 80
FONT_SIZE_MINIMO = 20
MAX_LARGHEZZA_RATIO = 0.86
MAX_ALTEZZA_RATIO = 0.60


def genera_poster(host_code, out_path):
    img = Image.open(TEMPLATE_PATH)
    draw = ImageDraw.Draw(img)

    larghezza_box = BOX[2] - BOX[0]
    altezza_box = BOX[3] - BOX[1]
    max_larghezza = larghezza_box * MAX_LARGHEZZA_RATIO
    max_altezza = altezza_box * MAX_ALTEZZA_RATIO

    font = None
    size = FONT_SIZE_INIZIALE
    while size >= FONT_SIZE_MINIMO:
        candidato = ImageFont.truetype(str(FONT_PATH), size)
        left, top, right, bottom = draw.textbbox((0, 0), host_code, font=candidato)
        if (right - left) <= max_larghezza and (bottom - top) <= max_altezza:
            font = candidato
            break
        size -= 2
    if font is None:
        font = ImageFont.truetype(str(FONT_PATH), FONT_SIZE_MINIMO)

    draw.text(CENTRO, host_code, font=font, fill="black", anchor="mm")
    img.save(out_path, "PNG", dpi=(300, 300))


def jpeg_per_invio(path):
    """Converte un PNG in JPEG (qualità 92) in memoria, per allegati email
    più leggeri. Il file sorgente non viene toccato."""
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92, optimize=True, dpi=(300, 300))
    return buf.getvalue()
