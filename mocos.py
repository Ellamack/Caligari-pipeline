"""
mocos.py — Imágenes de listing (mockups) sin Placeit, generadas por código.

Genera 6 imágenes por bundle (cada una con láminas distintas):
  detalle_1.jpg, detalle_2.jpg  Acercamiento al 100% de la zona con más trabajo de color
                                (+ miniatura de la lámina completa con el recuadro de dónde sale).
  flatlay.jpg                   Láminas apiladas y giradas, con sombra, sobre la textura de madera.
  incluido.jpg                  "What's included" (plantilla SVG plantillas/incluido.svg).
  tamanos.jpg                   Guía de tamaños de impresión (A4, US Letter, 8×10 in).
  pin_pinterest.jpg             Pin vertical 1000×1500 para Pinterest (no se sube a Etsy).

Las de "lámina enmarcada en una pared" necesitan fotos de escena: van en otro paso.

Uso suelto:
  python3 mocos.py carpeta_laminas salida --titulo "96 Antique Butterfly Plates" --n 96 --lado 3508
Desde empaquetar.py se llama a generar(…) automáticamente.

Requiere: pillow numpy (y cairosvg para incluido.jpg, igual que hoja_referencia.py)
"""
import argparse
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import hoja_referencia as hr

AQUI = Path(__file__).parent
PLANTILLAS = AQUI / "plantillas"
TINTA = (43, 29, 18)
LIENZO = (2400, 2400)  # cuadrado: Etsy lo recorta bien en miniatura y en móvil


# ---------------------------------------------------------------- utilidades
def fuente(tam, negrita=False, italica=False):
    nombres = ["DejaVuSerif-Bold.ttf" if negrita else
               ("DejaVuSerif-Italic.ttf" if italica else "DejaVuSerif.ttf"),
               "Georgia.ttf", "georgia.ttf"]
    for n in nombres:
        try:
            return ImageFont.truetype(n, tam)
        except OSError:
            continue
    return ImageFont.load_default(size=tam)


def fondo(nombre, tam):
    """Textura de plantillas/ recortada a `tam` (o un color liso si no existe)."""
    ruta = PLANTILLAS / nombre
    if not ruta.exists():
        return Image.new("RGB", tam, (60, 40, 28))
    img = Image.open(ruta).convert("RGB")
    escala = max(tam[0] / img.width, tam[1] / img.height)
    img = img.resize((math.ceil(img.width * escala), math.ceil(img.height * escala)), Image.LANCZOS)
    x, y = (img.width - tam[0]) // 2, (img.height - tam[1]) // 2
    return img.crop((x, y, x + tam[0], y + tam[1]))


def texto_centrado(draw, y, texto, f, ancho, color=TINTA):
    w = draw.textlength(texto, font=f)
    draw.text(((ancho - w) / 2, y), texto, font=f, fill=color)


def con_sombra(lienzo, img, x, y, desplaz=18, difus=22, opacidad=110):
    """Pega `img` (RGBA) en `lienzo` con una sombra suave debajo."""
    alfa = img.split()[-1]
    sombra = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sombra.putalpha(alfa.point(lambda a: a * opacidad // 255))
    margen = difus * 3
    capa = Image.new("RGBA", (img.width + 2 * margen, img.height + 2 * margen), (0, 0, 0, 0))
    capa.paste(sombra, (margen, margen), sombra)
    capa = capa.filter(ImageFilter.GaussianBlur(difus))
    lienzo.alpha_composite(capa, (x - margen + desplaz, y - margen + desplaz))
    lienzo.alpha_composite(img, (x, y))


def mapa_detalle(img):
    """Dónde hay más 'trabajo': color (rg, yb) + bordes, en una versión reducida."""
    peq = img.convert("RGB").resize((256, int(256 * img.height / img.width)))
    a = np.asarray(peq, dtype=np.float32)
    rg = np.abs(a[..., 0] - a[..., 1])
    yb = np.abs(0.5 * (a[..., 0] + a[..., 1]) - a[..., 2])
    gris = a.mean(axis=2)
    bordes = np.abs(np.diff(gris, axis=0, prepend=gris[:1])) + np.abs(np.diff(gris, axis=1, prepend=gris[:, :1]))
    return rg + yb + 2 * bordes, peq.size


def mejor_ventana(img, fraccion=0.24):
    """Cuadro (en px de la imagen original) con más color y detalle; lado = fraccion del lado corto."""
    m, (pw, ph) = mapa_detalle(img)
    lado = int(min(pw, ph) * fraccion)
    integral = m.cumsum(0).cumsum(1)
    mejor, pos = -1.0, (0, 0)
    paso = max(2, lado // 8)
    for y in range(0, ph - lado, paso):
        for x in range(0, pw - lado, paso):
            s = (integral[y + lado - 1, x + lado - 1] - (integral[y - 1, x + lado - 1] if y else 0)
                 - (integral[y + lado - 1, x - 1] if x else 0) + (integral[y - 1, x - 1] if x and y else 0))
            if s > mejor:
                mejor, pos = s, (x, y)
    k = img.width / pw
    x0, y0 = int(pos[0] * k), int(pos[1] * k)
    return x0, y0, x0 + int(lado * k), y0 + int(lado * k)


# ---------------------------------------------------------------- las 5 imágenes
def detalle(ruta, destino, titulo):
    img = Image.open(ruta).convert("RGB")
    caja = mejor_ventana(img)
    zoom = img.crop(caja).resize((1700, 1700), Image.LANCZOS)
    lienzo = fondo("papel.jpg", LIENZO).convert("RGBA")
    d = ImageDraw.Draw(lienzo)
    texto_centrado(d, 70, "Every detail, at full resolution", fuente(78, negrita=True), LIENZO[0])
    marco = Image.new("RGBA", (zoom.width + 16, zoom.height + 16), (250, 245, 232, 255))
    marco.paste(zoom, (8, 8))
    con_sombra(lienzo, marco, 120, 260)
    # miniatura con el recuadro
    mini_h = 620
    mini = img.resize((int(img.width * mini_h / img.height), mini_h), Image.LANCZOS)
    k = mini_h / img.height
    dm = ImageDraw.Draw(mini)
    dm.rectangle([caja[0] * k, caja[1] * k, caja[2] * k, caja[3] * k], outline=(180, 30, 30), width=5)
    mini_m = Image.new("RGBA", (mini.width + 12, mini.height + 12), (250, 245, 232, 255))
    mini_m.paste(mini, (6, 6))
    con_sombra(lienzo, mini_m, LIENZO[0] - mini_m.width - 90, LIENZO[1] - mini_m.height - 200, desplaz=10, difus=12)
    d.text((120, LIENZO[1] - 150), titulo, font=fuente(54, italica=True), fill=TINTA)
    lienzo.convert("RGB").save(destino, "JPEG", quality=90, dpi=(300, 300))


def flatlay(rutas, destino, titulo, n):
    rnd = random.Random(7)  # siempre la misma composición para el mismo bundle
    lienzo = fondo("madera.jpg", LIENZO).convert("RGBA")
    lado = 1150  # lado mayor de cada lámina en el lienzo
    posiciones = [(-9, 180, 200), (6, 1050, 160), (-3, 560, 520), (11, 1150, 760), (-6, 260, 900)]
    for ruta, (ang, x, y) in zip(rutas[:5], posiciones):
        img = Image.open(ruta).convert("RGB")
        k = lado / max(img.size)
        img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS).convert("RGBA")
        img = img.rotate(ang + rnd.uniform(-1.5, 1.5), resample=Image.BICUBIC, expand=True)
        con_sombra(lienzo, img, x, y, desplaz=26, difus=30, opacidad=140)
    banda = Image.new("RGBA", (LIENZO[0], 260), (244, 232, 205, 235))
    lienzo.alpha_composite(banda, (0, LIENZO[1] - 260))
    d = ImageDraw.Draw(lienzo)
    texto_centrado(d, LIENZO[1] - 225, titulo, fuente(84, negrita=True), LIENZO[0])
    # si el título ya dice el número ("97 Antique…"), la segunda línea no lo repite
    sub = "Printable plates" if titulo.lstrip().startswith(str(n)) else f"{n} printable plates"
    texto_centrado(d, LIENZO[1] - 115, f"{sub} · instant download", fuente(54), LIENZO[0])
    lienzo.convert("RGB").save(destino, "JPEG", quality=90, dpi=(300, 300))


def incluido(rutas, destino, campos):
    plantilla = PLANTILLAS / "incluido.svg"
    svg = hr.llenar(plantilla, rutas[:8], campos, numeros=False)
    hr.renderizar(svg, destino)


def tamanos(ruta, destino):
    """Tres formatos a escala real entre sí, con la lámina encajada en cada uno."""
    img = Image.open(ruta).convert("RGB")
    lienzo = fondo("papel.jpg", LIENZO).convert("RGBA")
    d = ImageDraw.Draw(lienzo)
    texto_centrado(d, 80, "Print at home or at any print shop", fuente(78, negrita=True), LIENZO[0])
    formatos = [("8 × 10 in", 203, 254), ("A4", 210, 297), ("US Letter", 216, 279)]
    hueco, margen = 90, 110
    escala = (LIENZO[0] - 2 * margen - 2 * hueco) / sum(f[1] for f in formatos)  # px por mm
    x = margen
    base_y = 1600
    for nombre, w_mm, h_mm in formatos:
        w, h = int(w_mm * escala), int(h_mm * escala)
        hoja = Image.new("RGBA", (w, h), (252, 248, 238, 255))
        k = min((w - 60) / img.width, (h - 60) / img.height)
        lam = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS)
        hoja.paste(lam, ((w - lam.width) // 2, (h - lam.height) // 2))
        con_sombra(lienzo, hoja, x, base_y - h, desplaz=14, difus=16)
        f = fuente(56, negrita=True)
        d.text((x + (w - d.textlength(nombre, font=f)) / 2, base_y + 40), nombre, font=f, fill=TINTA)
        f2 = fuente(40)
        sub = f"{w_mm} × {h_mm} mm"
        d.text((x + (w - d.textlength(sub, font=f2)) / 2, base_y + 115), sub, font=f2, fill=TINTA)
        x += w + hueco
    texto_centrado(d, LIENZO[1] - 170, "300 DPI files · also great for larger frames at gallery resolution",
                   fuente(44, italica=True), LIENZO[0])
    lienzo.convert("RGB").save(destino, "JPEG", quality=90, dpi=(300, 300))


def pin(rutas, destino, titulo, subtitulo):
    """Pin vertical 2:3 (1000×1500, el formato que Pinterest muestra más grande):
    una lámina protagonista sobre madera, dos asomando detrás, y el título en una banda."""
    tam = (1000, 1500)
    lienzo = fondo("madera.jpg", tam).convert("RGBA")
    # (lámina, lado mayor, giro, centro x, arriba): dos atrás, abiertas en abanico; la protagonista al frente
    capas = [(rutas[1], 700, -9, 330, 90), (rutas[2], 700, 8, 670, 80), (rutas[0], 860, 0, 500, 230)]
    for ruta, lado, ang, cx, y in capas:
        img = hr.abrir_reducida(ruta, lado * 2)
        k = lado / max(img.size)
        img = img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS).convert("RGBA")
        if ang:
            img = img.rotate(ang, resample=Image.BICUBIC, expand=True)
        con_sombra(lienzo, img, int(cx - img.width / 2), y, desplaz=14, difus=16, opacidad=150)
    banda_h = 290
    lienzo.alpha_composite(Image.new("RGBA", (tam[0], banda_h), (244, 232, 205, 240)), (0, tam[1] - banda_h))
    d = ImageDraw.Draw(lienzo)
    tam_letra = 64
    while d.textlength(titulo, font=fuente(tam_letra, negrita=True)) > tam[0] - 80 and tam_letra > 36:
        tam_letra -= 2
    texto_centrado(d, tam[1] - banda_h + 55, titulo, fuente(tam_letra, negrita=True), tam[0])
    texto_centrado(d, tam[1] - banda_h + 150, subtitulo, fuente(38, italica=True), tam[0])
    texto_centrado(d, tam[1] - banda_h + 210, "Printable · instant download", fuente(34), tam[0])
    lienzo.convert("RGB").save(destino, "JPEG", quality=90)


def generar(laminas, salida, titulo, n, lado_px, vistosas=None, subtitulo=""):
    """Genera las imágenes del listing. `laminas`: rutas JPG ya procesadas.
    `vistosas`: láminas ordenadas por color que aún no se usaron (la portada ya tomó las suyas);
    cada imagen toma láminas distintas para que el listing no repita la misma.
    Devuelve la lista de archivos."""
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    orden = list(vistosas) if vistosas else hr.ranking_color(laminas)
    orden = orden or list(laminas)
    siguiente = 0

    def tomar(k):
        """Las k siguientes del orden; si el libro es chico se vuelve a empezar
        (mejor repetir alguna que dejar una imagen vacía)."""
        nonlocal siguiente
        r = [orden[(siguiente + j) % len(orden)] for j in range(k)]
        siguiente += k
        return r

    p_detalle = tomar(2)
    p_flatlay = tomar(5)
    p_incluido = sorted(tomar(8))
    p_pin = tomar(3)
    hechos = []
    for k, ruta in enumerate(p_detalle, 1):
        destino = salida / f"detalle_{k}.jpg"
        detalle(ruta, destino, titulo)
        hechos.append(destino)
    destino = salida / "flatlay.jpg"
    flatlay(p_flatlay, destino, titulo, n)
    hechos.append(destino)
    destino = salida / "incluido.jpg"
    incluido(p_incluido, destino, {"TITULO": titulo, "N": str(n),
                                   "RESOLUCION": f"300 DPI · up to {lado_px} px", "FORMATO": "JPG"})
    hechos.append(destino)
    destino = salida / "tamanos.jpg"
    tamanos(p_detalle[0], destino)  # misma lámina que el primer detalle: aquí solo importa el formato
    hechos.append(destino)
    destino = salida / "pin_pinterest.jpg"  # para Pinterest, no para Etsy
    pin(p_pin, destino, titulo, subtitulo)
    hechos.append(destino)
    return hechos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("laminas", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--titulo", required=True)
    ap.add_argument("--n", type=int, help="número de láminas del bundle (default: las de la carpeta)")
    ap.add_argument("--lado", type=int, default=3508, help="lado mayor de las láminas en px")
    a = ap.parse_args()
    rutas = sorted(p for p in a.laminas.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    for f in generar(rutas, a.salida, a.titulo, a.n or len(rutas), a.lado):
        print(f)


if __name__ == "__main__":
    main()
