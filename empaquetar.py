"""
empaquetar.py — Etapa 4 (línea A): arma el producto y la ficha del listing.

Avanza en pasos y se detiene donde necesita algo de ti (CONTRATO 3):
  1. Revisión: aplica tu respuesta ("ok" o "quitar 7,64"); si aún no hay y no venció, espera.
  2. Producto: láminas renombradas + Reference Sheet + README → ZIP completo (+ MD5),
     muestra.zip (≤ 18 MB, va en Etsy) y portada.jpg (imagen principal del listing).
  3. Enlace: te pide el enlace de Drive del ZIP completo (no avanza solo: es público).
  4. LEEME_descarga.pdf (botón + QR + instrucciones) y ficha.json (CONTRATO 4).
  5. Borra los intermedios (páginas crudas y láminas sueltas) salvo --conservar.

Uso:
  python3 empaquetar.py deuitlandschekap11779cram
  python3 empaquetar.py deuitlandschekap11779cram --tema "Butterfly" --obra "De Uitlandsche Kapellen, Vol. I"
  python3 empaquetar.py deuitlandschekap11779cram --enlace "https://drive.google.com/…"

Requiere: pip install pillow fpdf2 qrcode cairosvg  (y hoja_referencia.py + plantillas/)
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

import manifiesto as mf
import hoja_referencia as hr
import mocos

AQUI = Path(__file__).parent
PLANTILLAS = AQUI / "plantillas"
MUESTRA_MAX = 18_000_000  # Etsy permite 20 MB por archivo; dejamos margen


def autor_legible(creador):
    """'Cramer, Pieter, -1780; Stoll, Caspar' → 'Pieter Cramer'."""
    primero = creador.split(";")[0]
    partes = [p.strip() for p in primero.split(",") if p.strip() and not re.match(r"^[\d\-–. ]+$", p.strip())]
    return f"{partes[1]} {partes[0]}" if len(partes) >= 2 else (partes[0] if partes else "")


def fecha_legible(meta):
    """Años de publicación para mostrar. Muchas obras salieron por entregas durante años
    (Cramer: 1775-1779): si la ficha trae un rango se usa completo; si no, el año.
    --fecha en la línea de comandos manda sobre todo."""
    if meta.get("fecha_mostrar"):
        return meta["fecha_mostrar"]
    for campo in ("fecha", "titulo"):
        r = re.search(r"\b(1[5-9]\d\d)\s*[-–]\s*(1[5-9]\d\d|\d\d)\b", meta.get(campo) or "")
        if r:
            fin = r.group(2) if len(r.group(2)) == 4 else r.group(1)[:2] + r.group(2)
            return f"{r.group(1)}-{fin}"
    r = re.search(r"\b(1[5-9]\d\d)\b", meta.get("fecha") or "")
    return r.group(1) if r else ""


def obra_corta(titulo):
    t = re.split(r"[,:;/]", titulo)[0].strip()
    return t[:70] if t else titulo[:70]


def slug(texto):
    return re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")[:40] or "bundle"


def md5_de(ruta):
    h = hashlib.md5()
    with open(ruta, "rb") as fh:
        for trozo in iter(lambda: fh.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def latin1(s):
    """fpdf con fuentes estándar solo acepta latin-1."""
    reemplazos = {"–": "-", "—": "-", "’": "'", "“": '"', "”": '"', "…": "...", "→": "->"}
    for a, b in reemplazos.items():
        s = s.replace(a, b)
    return s.encode("latin-1", "replace").decode("latin-1")


# ---------------------------------------------------------------- paso 1: revisión
def aplicar_revision(m):
    if mf.hecho(m, "revision"):
        return True
    r = mf.respuesta(m["id"], "revision")
    if r is None:
        print("Esperando tu revisión de la hoja de contactos (python3 responder.py para verla).")
        return False
    quitar = set()
    if r.lower().startswith("quitar"):
        quitar = {int(n) for n in re.findall(r"\d+", r)}
    for d in m["laminas"]:
        if d.get("incluida") and d["pagina"] in quitar:
            d["incluida"] = False
    mf.marcar(m, "revision", "hecho", excluir=sorted(quitar), respuesta=r)
    print(f"Revisión aplicada: {r}")
    return True


# ---------------------------------------------------------------- paso 2: producto
def armar_producto(m, datos):
    ident = m["id"]
    carpeta = mf.carpeta(ident)
    bundle = carpeta / "bundle"
    contenido = bundle / "contenido"
    if contenido.exists():
        shutil.rmtree(contenido)
    contenido.mkdir(parents=True)
    laminas_dir = carpeta / "laminas"
    elegidas = [d for d in m["laminas"] if d.get("incluida") and d.get("salida")]
    base = slug(f"{datos['obra']}")
    finales, lista = [], []
    for k, d in enumerate(elegidas, 1):
        destino = contenido / f"{base}_plate_{k:03d}.jpg"
        shutil.copy2(laminas_dir / d["salida"], destino)
        finales.append(destino)
        lista.append(f" {k:>3}. Plate {k}  (page {d['pagina']} of the original volume)")
    n = len(finales)
    titulo = f"{n} Antique {datos['tema']} Plates" if datos["tema"] else f"{n} Antique Plates"
    sub = f"{datos['obra']} · {datos['autor']} · {datos['fecha']}"
    cita = f"Originally published by {datos['autor']}, {datos['fecha']}. Digitized by the Internet Archive."

    print(f"Reference Sheet de {n} láminas…")
    svg = hr.llenar(PLANTILLAS / "reference_sheet.svg", finales,
                    {"TITULO": titulo, "SUBTITULO": sub, "CITA": cita, "N": str(n)}, numeros=True)
    ref = hr.renderizar(svg, contenido / f"{base}_reference_sheet.jpg")
    shutil.copy2(ref, bundle / ref.name)  # copia fuera de contenido/: también es imagen del listing
    print("Portada del listing…")
    orden = hr.ranking_color(finales)  # una sola vez: portada y mocos se reparten láminas distintas
    svg = hr.llenar(PLANTILLAS / "reference_sheet.svg", sorted(orden[:6]),
                    {"TITULO": titulo, "SUBTITULO": f"{datos['autor']} · {datos['fecha']} · JPG 300 DPI",
                     "CITA": "Instant download", "N": str(n)}, numeros=False)
    portada = hr.renderizar(svg, bundle / "portada.jpg")
    print("Mocos (detalle, flat lay, incluido, tamaños)…")
    lado = m["etapas"]["procesar"]["params"].get("lado_max", 3508)
    hechos = mocos.generar(finales, bundle / "mocos", titulo, n, lado, vistosas=orden[6:],
                           subtitulo=f"{datos['autor']} · {datos['fecha']}")

    marca = json.loads((PLANTILLAS / "marca.json").read_text(encoding="utf-8"))
    readme = (PLANTILLAS / "readme_A.txt").read_text(encoding="utf-8")
    campos = {"TITULO": titulo, "N": str(n), "OBRA": datos["obra"], "AUTOR": datos["autor"],
              "FECHA": datos["fecha"], "LADO_MAX": str(m["etapas"]["procesar"]["params"].get("lado_max", "")),
              "LISTA": "\n".join(lista), "CITA": f"{cita}\n{m['meta'].get('url', '')}",
              "EMAIL": marca["email"], "INSTAGRAM": marca["instagram"], "TIENDA": marca["tienda"]}
    for c, v in campos.items():
        readme = readme.replace("{" + c + "}", v)
    leeme = contenido / "README.txt"
    leeme.write_text(readme, encoding="utf-8")

    print("ZIP completo…")
    zip_completo = bundle / f"{base}_complete.zip"
    with zipfile.ZipFile(zip_completo, "w", zipfile.ZIP_STORED) as z:  # JPG ya viene comprimido
        for f in [leeme, ref] + finales:
            z.write(f, f.name)
    print("Muestra para Etsy…")
    muestra = bundle / "sample_pack.zip"
    with zipfile.ZipFile(muestra, "w", zipfile.ZIP_STORED) as z:
        z.write(leeme, leeme.name)
        z.write(ref, ref.name)
        for f in hr.mas_coloridas(finales, 10):
            if muestra.stat().st_size + f.stat().st_size > MUESTRA_MAX:
                break
            z.write(f, f.name)
    return {"titulo": titulo, "n": n, "zip": zip_completo.name,
            "mb": round(zip_completo.stat().st_size / 1e6, 1), "md5": md5_de(zip_completo),
            "muestra": muestra.name, "portada": portada.name, "reference": ref.name,
            "mocos": [f"mocos/{h.name}" for h in hechos if not h.name.startswith("pin_")],
            "pin": next((f"mocos/{h.name}" for h in hechos if h.name.startswith("pin_")), None)}


# ---------------------------------------------------------------- paso 4: PDF + ficha
def hacer_pdf(destino, prod, enlace, datos, marca):
    import qrcode
    from fpdf import FPDF
    qr_png = destino.with_suffix(".qr.png")
    qrcode.make(enlace, box_size=10, border=2).save(qr_png)
    pdf = FPDF("P", "mm", "A4")
    pdf.add_page()
    _mc = pdf.multi_cell

    def parrafo(*a, **k):  # cada párrafo vuelve al margen izquierdo y baja de renglón
        _mc(*a, new_x="LMARGIN", new_y="NEXT", **k)
    pdf.multi_cell = parrafo
    pdf.set_fill_color(244, 232, 205)
    pdf.rect(0, 0, 210, 297, "F")
    pdf.set_text_color(43, 29, 18)
    pdf.set_font("Times", "B", 24)
    pdf.set_y(30)
    pdf.multi_cell(0, 11, latin1(prod["titulo"]), align="C")
    pdf.set_font("Times", "", 14)
    pdf.multi_cell(0, 8, latin1(f"{datos['obra']} - {datos['autor']}, {datos['fecha']}"), align="C")
    pdf.ln(12)
    pdf.set_font("Helvetica", "", 12)
    pdf.multi_cell(0, 7, latin1(
        f"Thank you for your purchase! Your full collection ({prod['n']} high-resolution JPG plates, "
        f"reference sheet and README) is a single ZIP file of about {prod['mb']:.0f} MB."), align="C")
    pdf.ln(8)
    # botón
    x, w, h = 45, 120, 18
    y = pdf.get_y()
    pdf.set_fill_color(92, 52, 28)
    pdf.rect(x, y, w, h, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(x, y)
    pdf.cell(w, h, "DOWNLOAD THE FULL COLLECTION", align="C", link=enlace, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(43, 29, 18)
    pdf.set_y(y + h + 6)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, latin1(enlace), align="C", link=enlace)
    pdf.ln(6)
    pdf.image(str(qr_png), x=80, w=50)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, "Or scan this code with your phone.", align="C")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 11)
    pdf.multi_cell(0, 6, latin1(
        "How to use: click the button (or open the link), download the ZIP and unzip it. "
        "On Windows: right-click > Extract All. On Mac: double-click. "
        "A sample pack is also included with this purchase so you can start right away."), align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 10)
    pdf.multi_cell(0, 6, latin1(
        f"Questions? {marca['email']}  -  Instagram {marca['instagram']}\n{marca['tienda']}"), align="C")
    try:
        pdf.output(str(destino))
    finally:
        qr_png.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id")
    ap.add_argument("--tema", help='p. ej. "Butterfly", "Bird", "Botanical"')
    ap.add_argument("--obra", help="título corto de la obra (por defecto, del manifiesto)")
    ap.add_argument("--fecha", help='años de publicación tal como se muestran, p. ej. "1775-1779"')
    ap.add_argument("--enlace", help="enlace de Drive del ZIP completo")
    ap.add_argument("--conservar", action="store_true", help="no borrar páginas crudas ni láminas al final")
    ap.add_argument("--rehacer", action="store_true", help="vuelve a armar el producto aunque ya exista")
    args = ap.parse_args()

    m = mf.leer(args.id)
    if m is None or not mf.hecho(m, "procesar"):
        sys.exit(f"{args.id}: primero hay que correr procesar_laminas.py --libro {args.id}")
    if mf.hecho(m, "empaquetar") and not args.rehacer:
        print(f"{args.id}: ya empaquetado. Ficha en {mf.carpeta(args.id) / 'bundle' / 'ficha.json'}")
        return

    meta = m["meta"]
    if args.tema:
        meta["tema"] = args.tema
    if args.obra:
        meta["obra"] = args.obra
    if args.fecha:
        meta["fecha_mostrar"] = args.fecha
    datos = {"tema": meta.get("tema", ""), "obra": meta.get("obra") or obra_corta(meta.get("titulo", "")),
             "autor": autor_legible(meta.get("autor", "")), "fecha": fecha_legible(meta)}
    mf.guardar(m)

    if not aplicar_revision(m):
        return

    etapa = m["etapas"]["empaquetar"]
    bundle = mf.carpeta(args.id) / "bundle"
    if args.rehacer or "zip" not in etapa or not (bundle / etapa["zip"]).exists():
        prod = armar_producto(m, datos)
        mf.marcar(m, "empaquetar", "esperando", **prod)
        print(f"ZIP completo: {bundle / prod['zip']}  ({prod['mb']} MB, md5 {prod['md5']})")
    prod = {k: m["etapas"]["empaquetar"].get(k) for k in
            ("titulo", "n", "zip", "mb", "md5", "muestra", "portada", "reference", "mocos", "pin")}

    enlace = args.enlace or mf.respuesta(args.id, "enlace")
    if not enlace:
        mf.preguntar(args.id, "enlace",
                     f"Sube {prod['zip']} ({prod['mb']} MB) a Drive → Caligari/entregas, compártelo como "
                     f"'cualquiera con el enlace' y pásame el enlace.",
                     formato="https://drive.google.com/…", adjuntos=[bundle / prod["zip"]], si_no_respondes=None)
        print("Falta el enlace de descarga. Quedó la pregunta en outbox/ (python3 responder.py).")
        return
    if not enlace.startswith("http"):
        sys.exit(f"Eso no parece un enlace: {enlace}")

    marca = json.loads((PLANTILLAS / "marca.json").read_text(encoding="utf-8"))
    pdf = bundle / "LEEME_descarga.pdf"
    hacer_pdf(pdf, prod, enlace, datos, marca)
    ficha = {
        "titulo": f"{prod['titulo']} | {datos['obra']}, {datos['autor']} {datos['fecha']} | Printable JPG Bundle"[:140],
        "descripcion": "",  # se redacta contigo (o con el modelo) en la etapa ficha
        "tags": [],
        "precio_usd": 0,
        "archivos_etsy": [pdf.name, prod["muestra"]],
        "descarga_completa": {"zip": prod["zip"], "mb": prod["mb"], "enlace": enlace, "md5": prod["md5"]},
        "imagenes": [prod["portada"], prod["reference"]] + prod.get("mocos", []),
        "cita": f"{datos['autor']} ({datos['fecha']}). {meta.get('titulo', '')}. Internet Archive. {meta.get('url', '')}",
    }
    (bundle / "ficha.json").write_text(json.dumps(ficha, ensure_ascii=False, indent=2), encoding="utf-8")
    mf.marcar(m, "empaquetar", "hecho", enlace=enlace, pdf=pdf.name)
    mf.marcar(m, "ficha", "esperando")
    if not args.conservar:
        for sub in ("crudo", "laminas"):
            shutil.rmtree(mf.carpeta(args.id) / sub, ignore_errors=True)
        shutil.rmtree(bundle / "contenido", ignore_errors=True)
        print("Intermedios borrados (páginas crudas, láminas sueltas).")
    print(f"Listo. Para Etsy: {pdf.name} + {prod['muestra']}; imágenes: {prod['portada']}, {prod['reference']}")
    if prod.get("pin"):
        print(f"Para Pinterest: {prod['pin']} (súbelo a Drive → T&P/pinterest/)")
    print("RECUERDA: al publicar en Etsy, agrega el listing a su oferta (Marketing → Sales and discounts).\n"
          "          Las ofertas que ya corren NO incluyen listings nuevos. Política de precios: roadmap del proyecto.")
    print(f"Todo en {bundle}")


if __name__ == "__main__":
    main()
