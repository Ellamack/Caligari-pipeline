"""
hoja_referencia.py — Llena la plantilla SVG (diseñada en Inkscape) con las láminas de un bundle.

Sirve para el Reference Sheet (todas las láminas, numeradas) y para la imagen principal del
listing (pocas láminas grandes). El diseño vive en plantillas/reference_sheet.svg; este script
solo lo llena (principio 1: lo volátil fuera del código).

Reglas de la plantilla:
  · {TITULO} {SUBTITULO} {CITA} {N} en los textos se reemplazan.
  · El rectángulo id="cuadricula" marca el área de las miniaturas (se oculta al llenar).
  · Las imágenes enlazadas (madera.jpg, papel.jpg) se buscan junto a la plantilla.

Uso:
  python hoja_referencia.py carpeta_laminas salida.jpg --titulo "…" --subtitulo "…" --cita "…"
  python hoja_referencia.py carpeta_laminas portada.jpg --titulo "…" --destacadas 6 --sin-numeros

Render: cairosvg (pip install cairosvg); si no está, Inkscape por línea de comandos.
"""
import argparse
import base64
import io
import math
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", XLINK)
PLANTILLA = Path(__file__).parent / "plantillas" / "reference_sheet.svg"
EXT = (".jpg", ".jpeg", ".png")


def abrir_reducida(ruta, lado):
    """Abre una imagen ya reducida a ~lado px sin decodificarla completa (JPEG 'draft').
    Así 97 láminas de 3508 px no se comen la memoria del VPS."""
    img = Image.open(ruta)
    if lado:
        img.draft("RGB", (lado, lado))
    img = img.convert("RGB")
    if lado and max(img.size) > lado:
        img.thumbnail((lado, lado), Image.LANCZOS)
    return img


def a_data_uri(ruta_o_img, lado_max=None, calidad=82):
    if isinstance(ruta_o_img, Image.Image):
        img = ruta_o_img.convert("RGB")
    else:
        img = abrir_reducida(ruta_o_img, lado_max)
    if lado_max and max(img.size) > lado_max:
        img.thumbnail((lado_max, lado_max), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=calidad)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def mejor_cuadricula(n, ancho, alto, aspecto, alto_etiqueta):
    """Columnas/filas que dan las miniaturas más grandes posibles dentro del área."""
    mejor = None
    for cols in range(1, n + 1):
        filas = math.ceil(n / cols)
        celda_w, celda_h = ancho / cols, alto / filas
        img_h = min(celda_h - alto_etiqueta * (celda_h / 100 if alto_etiqueta else 0), 0.9 * celda_w / aspecto)
        img_h = min(img_h, celda_h * (0.86 if alto_etiqueta else 0.96))
        tam = img_h * img_h * aspecto
        if mejor is None or tam > mejor[0]:
            mejor = (tam, cols, filas, celda_w, celda_h, img_h)
    return mejor[1:]


def llenar(plantilla, laminas, campos, numeros=True):
    texto = plantilla.read_text(encoding="utf-8")
    for clave, valor in campos.items():
        valor = (valor or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        texto = texto.replace("{" + clave + "}", valor)
    raiz = ET.fromstring(texto)
    # texturas enlazadas → incrustadas (el SVG queda autosuficiente y se renderiza en cualquier lado)
    for el in raiz.iter(f"{{{SVG}}}image"):
        href = el.get("href") or el.get(f"{{{XLINK}}}href")
        if href and not href.startswith("data:"):
            ruta = (plantilla.parent / href).resolve()
            if ruta.exists():
                uri = a_data_uri(ruta, lado_max=2400, calidad=88)
                el.set(f"{{{XLINK}}}href", uri)
                el.attrib.pop("href", None)
    # área de la cuadrícula
    caja = next(el for el in raiz.iter(f"{{{SVG}}}rect") if el.get("id") == "cuadricula")
    x0, y0 = float(caja.get("x")), float(caja.get("y"))
    W, H = float(caja.get("width")), float(caja.get("height"))
    caja.set("style", "display:none")
    padre = next(p for p in raiz.iter() if caja in list(p))
    indice = list(padre).index(caja)

    tamanos = []
    for r in laminas:  # solo lee el encabezado de cada archivo, no la imagen
        with Image.open(r) as im:
            tamanos.append(im.size)
    aspecto = sum(w / h for w, h in tamanos) / len(tamanos)
    cols, filas, cw, ch, img_h = mejor_cuadricula(len(tamanos), W, H, aspecto, 12 if numeros else 0)
    grupo = ET.Element(f"{{{SVG}}}g", {"id": "laminas"})
    lado_mini = int(max(img_h * aspecto, img_h) * 1.5)  # resolución suficiente para el render
    for k, ((iw, ih), ruta) in enumerate(zip(tamanos, laminas)):
        f, c = divmod(k, cols)
        n_en_fila = min(cols, len(tamanos) - f * cols)
        desplaz = (W - n_en_fila * cw) / 2  # centra la última fila si está incompleta
        h = img_h
        w = h * iw / ih
        cx = x0 + desplaz + c * cw + cw / 2
        top = y0 + f * ch + (ch - h - (ch * 0.12 if numeros else 0)) / 2
        ET.SubElement(grupo, f"{{{SVG}}}rect", {
            "x": f"{cx - w / 2 + 3:.1f}", "y": f"{top + 4:.1f}", "width": f"{w:.1f}", "height": f"{h:.1f}",
            "fill": "#000", "opacity": "0.25"})
        el = ET.SubElement(grupo, f"{{{SVG}}}image", {
            "x": f"{cx - w / 2:.1f}", "y": f"{top:.1f}", "width": f"{w:.1f}", "height": f"{h:.1f}",
            "preserveAspectRatio": "xMidYMid meet"})
        el.set(f"{{{XLINK}}}href", a_data_uri(ruta, lado_max=lado_mini))  # una a la vez
        if numeros:
            t = ET.SubElement(grupo, f"{{{SVG}}}text", {
                "x": f"{cx:.1f}", "y": f"{top + h + ch * 0.085:.1f}", "text-anchor": "middle",
                "font-family": "Georgia, 'DejaVu Serif', serif",
                "font-size": f"{max(14, ch * 0.065):.0f}", "fill": "#3b2a1c"})
            t.text = str(k + 1)
    padre.insert(indice, grupo)
    return ET.tostring(raiz, encoding="unicode")


def renderizar(svg_texto, destino, ancho=None):
    destino = Path(destino)
    png = destino.with_suffix(".tmp.png")
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=svg_texto.encode("utf-8"), write_to=str(png), output_width=ancho)
    except (ImportError, OSError):
        exe = shutil.which("inkscape")
        if not exe:
            raise SystemExit("No hay cómo renderizar: instala cairosvg (pip) o Inkscape.")
        with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8") as fh:
            fh.write(svg_texto)
        subprocess.run([exe, fh.name, "--export-type=png", f"--export-filename={png}"], check=True)
    img = Image.open(png).convert("RGB")
    img.save(destino, "JPEG", quality=90, dpi=(300, 300))
    png.unlink()
    return destino


def mas_coloridas(rutas, k):
    """Para la portada: las k láminas con más color (las más vistosas)."""
    import numpy as np
    def color(r):
        a = np.asarray(abrir_reducida(r, 300).resize((200, 260)), dtype=np.float32)
        rg = a[..., 0] - a[..., 1]
        yb = 0.5 * (a[..., 0] + a[..., 1]) - a[..., 2]
        return float(np.hypot(rg.std(), yb.std()))
    return sorted(sorted(rutas, key=color, reverse=True)[:k])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("laminas", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--titulo", default="")
    ap.add_argument("--subtitulo", default="")
    ap.add_argument("--cita", default="")
    ap.add_argument("--plantilla", type=Path, default=PLANTILLA)
    ap.add_argument("--destacadas", type=int, help="usa solo las N láminas más coloridas (portada)")
    ap.add_argument("--sin-numeros", action="store_true")
    ap.add_argument("--ancho", type=int, help="ancho final en px (default: el de la plantilla)")
    args = ap.parse_args()
    rutas = sorted(p for p in args.laminas.iterdir() if p.suffix.lower() in EXT)
    if args.destacadas:
        rutas = mas_coloridas(rutas, args.destacadas)
    campos = {"TITULO": args.titulo, "SUBTITULO": args.subtitulo, "CITA": args.cita, "N": str(len(rutas))}
    svg = llenar(args.plantilla, rutas, campos, numeros=not args.sin_numeros)
    print(renderizar(svg, args.salida, args.ancho))


if __name__ == "__main__":
    main()
