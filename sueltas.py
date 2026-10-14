"""
sueltas.py — Línea B: las figuras que elegiste con «sueltas 5, 18» salen además como listings individuales.

Por qué: la gente busca especies por su nombre ("death's head hawkmoth", "luna moth"). Una pieza suelta con ese
nombre en el título responde exactamente a esa búsqueda; la colección completa responde a otras. No compiten.

Por cada pieza suelta (en bundle/sueltas/<n>_<nombre>/):
  <nombre>.svg, <nombre>.png   los archivos que se suben DIRECTO a Etsy (son chicos: no hace falta enlace de Drive)
  portada.jpg                  la figura sola sobre papel claro, grande, sin texto (Etsy: un solo producto, sin collage)
  detalle.jpg                  acercamiento al 100%
  ficha.jpg                    qué recibe el comprador (1 SVG + 1 PNG, tamaño, usos)
  pin_pinterest.jpg            pin vertical
Lo llama empaquetar.py (armar_producto_b). Los nombres vienen de la pregunta «especies» de restaurar.py.
"""
import re
import shutil
import string
from pathlib import Path

from PIL import Image, ImageDraw

import diseno
import mocos

LIENZO = (2400, 2400)


def slug(texto):
    return re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")[:50] or "figura"


def ajustar(fig, ancho, alto):
    """Escala la figura (hacia arriba o abajo) para que quepa en ancho × alto."""
    k = min(ancho / fig.width, alto / fig.height)
    return fig.resize((max(1, int(fig.width * k)), max(1, int(fig.height * k))), Image.LANCZOS)


def nombre_bonito(comun):
    return string.capwords(comun)  # "death's head hawkmoth" → "Death's Head Hawkmoth" (no "Death'S")


def portada(png, destino, lado=LIENZO[0]):
    """La figura sola, grande y centrada sobre papel claro: lo que Etsy pide para la primera foto."""
    fondo = mocos.fondo("papel", (lado, lado)).convert("RGBA")
    claro = Image.new("RGBA", fondo.size, diseno.color("marco", 170))  # papel aclarado para que la figura destaque
    fondo.alpha_composite(claro)
    fig = ajustar(Image.open(png).convert("RGBA"), int(lado * 0.8), int(lado * 0.8))
    mocos.con_sombra(fondo, fig, (lado - fig.width) // 2, (lado - fig.height) // 2, desplaz=10, difus=18, opacidad=70)
    fondo.convert("RGB").save(destino, "JPEG", quality=92, dpi=(300, 300))
    return destino


def ficha(png, svg, destino, comun, cientifico, obra, autor, fecha):
    """Qué recibe el comprador, en una imagen (como hacen las tiendas grandes de clipart)."""
    lienzo = mocos.fondo("papel", LIENZO).convert("RGBA")
    d = ImageDraw.Draw(lienzo)
    w = LIENZO[0]
    fig = ajustar(Image.open(png).convert("RGBA"), 900, 900)
    mocos.con_sombra(lienzo, fig, (w - fig.width) // 2, 230 + (900 - fig.height) // 2, desplaz=8, difus=14, opacidad=60)
    t = nombre_bonito(comun)
    mocos.texto_centrado(d, 90, t, mocos.ajustada(d, t, 96, w - 200, negrita=True), w)
    y = 1220
    if cientifico:
        mocos.texto_centrado(d, y, cientifico, mocos.ajustada(d, cientifico, 60, w - 200, italica=True), w)
        y += 100
    origen = f"{obra} · {autor} · {fecha}"
    mocos.texto_centrado(d, y, origen, mocos.ajustada(d, origen, 44, w - 200, italica=True), w)
    with Image.open(png) as im:
        px = im.size
    lineas = [
        "1 SVG — vector, scales to any size",
        f"1 PNG — transparent background, {px[0]} × {px[1]} px, 300 DPI",
        "Restored from the original antique plate",
        "Personal & commercial use (no resale of the files)",
        "Instant download",
    ]
    y += 150
    f = mocos.fuente(56)
    for linea in lineas:
        d.text((360, y), "•  " + linea, font=f, fill=diseno.color("tinta"))
        y += 100
    lienzo.convert("RGB").save(destino, "JPEG", quality=90, dpi=(300, 300))
    return destino


def pin_suelta(png, destino, titulo, subtitulo, linea3):
    """Pin vertical 1000×1500: la figura grande sobre papel y el nombre en la banda."""
    tam = (1000, 1500)
    lienzo = mocos.fondo("papel", tam).convert("RGBA")
    banda_h = 290
    fig = ajustar(Image.open(png).convert("RGBA"), 820, tam[1] - banda_h - 140)
    mocos.con_sombra(lienzo, fig, (tam[0] - fig.width) // 2, (tam[1] - banda_h - fig.height) // 2,
                     desplaz=8, difus=14, opacidad=70)
    lienzo.alpha_composite(Image.new("RGBA", (tam[0], banda_h), diseno.color("banda", 240)), (0, tam[1] - banda_h))
    d = ImageDraw.Draw(lienzo)
    mocos.texto_centrado(d, tam[1] - banda_h + 55, titulo, mocos.ajustada(d, titulo, 64, tam[0] - 80, 36, negrita=True), tam[0])
    mocos.texto_centrado(d, tam[1] - banda_h + 150, subtitulo, mocos.ajustada(d, subtitulo, 38, tam[0] - 80, 26, italica=True), tam[0])
    mocos.texto_centrado(d, tam[1] - banda_h + 210, linea3, mocos.ajustada(d, linea3, 34, tam[0] - 80, 22), tam[0])
    lienzo.convert("RGB").save(destino, "JPEG", quality=90)
    return destino


def armar_sueltas(m, datos, contenido, bundle):
    """Una carpeta por pieza suelta. Devuelve la lista para el manifiesto (y para Caligari y el borrador de Etsy)."""
    r = m["etapas"]["restaurar"]
    especies = r.get("especies") or {}
    quedan = r["quedan"]
    salida = bundle / "sueltas"
    if salida.exists():
        shutil.rmtree(salida)
    hechas = []
    for k, nombre in (r.get("sueltas") or {}).items():
        if nombre not in quedan or k not in especies:
            continue
        idx = quedan.index(nombre) + 1  # mismo número que en la colección: el archivo ya está en contenido/
        png = next(contenido.glob(f"*_{idx:03d}.png"), None)
        svg = next(contenido.glob(f"*_{idx:03d}.svg"), None)
        if not png or not svg:
            continue
        e = especies[k]
        stem = slug(f"{e['comun']} {datos['autor'].split()[-1]} {datos['fecha'][:4]}")
        carpeta = salida / f"{k}_{slug(e['comun'])}"
        carpeta.mkdir(parents=True)
        shutil.copy2(png, carpeta / f"{stem}.png")
        shutil.copy2(svg, carpeta / f"{stem}.svg")
        vista = carpeta / "_vista.jpg"
        portada(png, vista, lado=2000)
        imagenes = [portada(png, carpeta / "portada.jpg")]
        mocos.detalle(vista, carpeta / "detalle.jpg", nombre_bonito(e["comun"]))
        imagenes.append(carpeta / "detalle.jpg")
        imagenes.append(ficha(png, svg, carpeta / "ficha.jpg", e["comun"], e.get("cientifico", ""),
                              datos["obra"], datos["autor"], datos["fecha"]))
        pin_suelta(png, carpeta / "pin_pinterest.jpg", nombre_bonito(e["comun"]),
                   e.get("cientifico") or datos["obra"], f"{datos['autor']} · {datos['fecha']} · SVG + PNG")
        imagenes.append(carpeta / "pin_pinterest.jpg")
        vista.unlink(missing_ok=True)
        hechas.append({"n": k, "comun": e["comun"], "cientifico": e.get("cientifico", ""),
                       "carpeta": str(carpeta.relative_to(bundle)),
                       "archivos_etsy": [f"{stem}.svg", f"{stem}.png"],
                       "imagenes": [str(p.relative_to(bundle)) for p in imagenes]})
        print(f"Pieza suelta: {e['comun']} ({k})")
    return hechas
