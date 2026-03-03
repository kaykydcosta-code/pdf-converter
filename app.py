from flask import Flask, request, abort
import fitz  # PyMuPDF
from PIL import Image
import io, zipfile, os

app = Flask(__name__)
SECRET = os.environ.get("CONVERTER_SECRET", "")

# ---------- Funções de recorte ----------
def recortar_imagem_bytes(img_bytes: bytes, geral=False) -> bytes:
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size
    px = img.load()

    black_threshold = 40
    margin = 6

    left, right, top, bottom = w, 0, h, 0
    found_black = False

    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r <= black_threshold and g <= black_threshold and b <= black_threshold:
                found_black = True
                if x < left: left = x
                if x > right: right = x
                if y < top: top = y
                if y > bottom: bottom = y

    if found_black:
        left = max(0, left - margin)
        top = 0 if geral else max(0, top - margin)
        right = min(w, right + margin)
        bottom = min(h, bottom + margin)
        if right - left > 10 and bottom - top > 10:
            cropped = img.crop((left, top, right, bottom))
            out = io.BytesIO()
            cropped.save(out, format="PNG")
            return out.getvalue()

    # fallback: cortar rodapé branco
    corte = h
    min_y = max(int(h * 0.4), 0)
    channel_threshold = 240
    required_white_ratio = 0.92
    max_samples = 800

    for y in range(h-1, min_y-1, -1):
        step = max(1, w // max_samples)
        white_count = 0
        total = 0
        for x in range(0, w, step):
            r, g, b = px[x,y]
            total += 1
            if r >= channel_threshold and g >= channel_threshold and b >= channel_threshold:
                white_count += 1
        if total > 0 and white_count/total < required_white_ratio:
            corte = min(h, y+5)
            break

    if corte < h:
        cropped = img.crop((0,0,w,corte))
        out = io.BytesIO()
        cropped.save(out, format="PNG")
        return out.getvalue()

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()

# ---------- Endpoint principal ----------
@app.route("/convert", methods=["POST"])
def convert():
    if SECRET:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {SECRET}":
            abort(401)

    pdf_bytes = request.data
    tmp_pdf = "/tmp/input.pdf"
    with open(tmp_pdf, "wb") as f:
        f.write(pdf_bytes)

    doc = fitz.open(tmp_pdf)
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w") as z:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(2,2))
            img_bytes = pix.tobytes(output="png")
            # Detecta se é "Escala Geral" pelo nome do PDF
            geral = "escala geral" in tmp_pdf.lower()
            cropped = recortar_imagem_bytes(img_bytes, geral=geral)
            z.writestr(f"page_{i+1}.png", cropped)
    doc.close()
    mem.seek(0)
    return (mem.read(), 200, {"Content-Type":"application/zip"})
