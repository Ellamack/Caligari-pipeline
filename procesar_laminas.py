#!/usr/bin/env python3
"""
procesar_laminas.py — Procesa en lote láminas escaneadas para bundles imprimibles.

Para cada imagen de la carpeta de entrada:
  1. Recorta el fondo del escáner y deja solo la página.
  2. Endereza la página si está ligeramente torcida.
  3. Iguala el tono del papel de todas las láminas a un mismo crema antiguo
     (configurable con --papel). NO blanquea el papel: conserva el aspecto viejo.
  4. Guarda un JPG de alta calidad a 300 DPI.

Uso:
    python procesar_laminas.py ENTRADA SALIDA [--margen 0.01] [--calidad 92] [--papel 236,226,203]
                               [--saturacion 1.2] [--contraste 1.1] [--lado-max 3508]

Ejemplo para un bundle imprimible (A4 a 300 DPI, láminas algo desvanecidas,
descartando páginas de texto, cubiertas y guardas estampadas):
    python procesar_laminas.py cramer_original cramer_listo --solo-color --min-papel 25 --saturacion 1.2 --contraste 1.08 --lado-max 3508 --calidad 88

Para calibrar el umbral de color antes de procesar:
    python procesar_laminas.py cramer_original x --medir

Requiere: pip install opencv-python-headless numpy pillow
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

EXTENSIONES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".jp2"}


def recortar_pagina(img):
    """Encuentra el rectángulo de la página (la región clara más grande) y lo recorta."""
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gris = cv2.GaussianBlur(gris, (9, 9), 0)
    # Otsu separa la página (clara) del fondo del escáner (oscuro o de otro tono)
    _, mascara = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mascara = cv2.morphologyEx(mascara, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return img, 0.0
    mayor = max(contornos, key=cv2.contourArea)
    # Si la "página" ocupa casi toda la imagen o casi nada, mejor no tocar
    fraccion = cv2.contourArea(mayor) / (img.shape[0] * img.shape[1])
    if fraccion < 0.30 or fraccion > 0.995:
        return img, 0.0
    (cx, cy), (w, h), angulo = cv2.minAreaRect(mayor)
    # Normaliza el ángulo a [-45, 45]
    if angulo < -45:
        angulo += 90
    elif angulo > 45:
        angulo -= 90
    return (img, mayor, (cx, cy), (w, h), angulo), fraccion


def enderezar_y_recortar(img, margen):
    resultado, fraccion = recortar_pagina(img)
    if fraccion == 0.0:
        return img, "sin recorte"
    img, contorno, centro, tam, angulo = resultado
    if abs(angulo) > 0.2:  # solo rota si vale la pena
        M = cv2.getRotationMatrix2D(centro, angulo, 1.0)
        img = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]),
                             flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    w, h = tam
    if angulo > 45 or angulo < -45:
        w, h = h, w
    x0 = int(centro[0] - w / 2)
    y0 = int(centro[1] - h / 2)
    # Margen hacia adentro para eliminar el borde del escáner que queda en la orilla
    mx, my = int(w * margen), int(h * margen)
    x0, y0 = max(0, x0 + mx), max(0, y0 + my)
    x1 = min(img.shape[1], int(x0 + w - 2 * mx))
    y1 = min(img.shape[0], int(y0 + h - 2 * my))
    return img[y0:y1, x0:x1], f"recortado, giro {angulo:+.2f}°"


def normalizar_color(img, papel_rgb=(236, 226, 203), bajo=0.5):
    """Iguala el tono del papel de todas las láminas a un mismo crema antiguo.

    - Estima el color del papel como la mediana de los píxeles más claros.
    - Escala cada canal para que ese papel quede en `papel_rgb` (conserva el
      aspecto envejecido, pero igual en todo el bundle).
    - Fija un punto negro común (percentil `bajo` de la luminancia) para dar
      contraste a las tintas sin cambiar su color.
    """
    papel_bgr = np.array(papel_rgb[::-1], dtype=np.float32)
    lum = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    claros = lum >= np.percentile(lum, 60)          # el papel domina la mitad clara
    # Un solo punto negro para los tres canales: así no se alteran los colores de las tintas
    # Tope de 40: si la lámina no tiene tinta negra real, no se "aplastan" sus colores oscuros
    negro = min(float(np.percentile(lum, bajo)), 40.0)
    salida = np.empty_like(img)
    for c in range(3):
        canal = img[:, :, c].astype(np.float32)
        papel = np.median(canal[claros])
        if papel - negro < 1:
            salida[:, :, c] = img[:, :, c]
            continue
        canal = (canal - negro) * (papel_bgr[c] / (papel - negro))
        salida[:, :, c] = np.clip(canal, 0, 255).astype(np.uint8)
    return salida


def colorido(img):
    """Índice de colorido de Hasler-Süsstrunk. Texto en b/n ≈ 0–10; láminas iluminadas ≫ 20."""
    small = cv2.resize(img, (400, int(400 * img.shape[0] / img.shape[1])), interpolation=cv2.INTER_AREA)
    b, g, r = [c.astype(np.float32) for c in cv2.split(small)]
    rg = r - g
    yb = 0.5 * (r + g) - b
    return float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))


def fraccion_papel(img):
    """% de la página que parece papel (claro y poco saturado).
    Láminas: mucho papel alrededor de las figuras (típicamente >35%).
    Cubiertas de piel, guardas marmoleadas o estampadas: casi nada de papel."""
    small = cv2.resize(img, (400, int(400 * img.shape[0] / img.shape[1])), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    papel = (hsv[:, :, 1] < 70) & (hsv[:, :, 2] > 140)
    return 100.0 * papel.mean()


def avivar(img, saturacion=1.0, contraste=1.0):
    """Recupera láminas desvanecidas: sube la saturación (HSV) y el contraste medio."""
    if saturacion != 1.0:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * saturacion, 0, 255)
        img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    if contraste != 1.0:
        f = img.astype(np.float32)
        img = np.clip((f - 128.0) * contraste + 128.0, 0, 255).astype(np.uint8)
    return img


def reducir(img, lado_max):
    """Reduce la imagen para que su lado mayor no pase de `lado_max` píxeles."""
    if not lado_max:
        return img
    h, w = img.shape[:2]
    escala = lado_max / max(h, w)
    if escala >= 1:
        return img
    return cv2.resize(img, (round(w * escala), round(h * escala)), interpolation=cv2.INTER_AREA)


def procesar(ruta_in, ruta_out, margen, calidad, papel, saturacion=1.0, contraste=1.0, lado_max=0,
             min_color=None, max_color=None, min_papel=None):
    img = cv2.imread(str(ruta_in), cv2.IMREAD_COLOR)
    if img is None:
        return f"ERROR: no se pudo leer {ruta_in.name}"
    if min_color is not None or max_color is not None:
        indice = colorido(img)
        if min_color is not None and indice < min_color:
            return f"{ruta_in.name}: OMITIDA (colorido {indice:.1f} < {min_color}, probable página de texto)"
        if max_color is not None and indice > max_color:
            return f"{ruta_in.name}: OMITIDA (colorido {indice:.1f} > {max_color}, probable cubierta o guarda)"
    if min_papel is not None:
        fp = fraccion_papel(img)
        if fp < min_papel:
            return f"{ruta_in.name}: OMITIDA (papel {fp:.0f}% < {min_papel:.0f}%, probable cubierta o guarda)"
    img, nota = enderezar_y_recortar(img, margen)
    if papel is not None:
        img = normalizar_color(img, papel)
    img = avivar(img, saturacion, contraste)
    img = reducir(img, lado_max)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    Image.fromarray(rgb).save(ruta_out, "JPEG", quality=calidad, dpi=(300, 300),
                              optimize=True, progressive=True)
    return f"{ruta_in.name}: {nota}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("salida", type=Path)
    ap.add_argument("--margen", type=float, default=0.01,
                    help="fracción a recortar hacia adentro en cada borde (0.01 = 1%%)")
    ap.add_argument("--calidad", type=int, default=92, help="calidad JPG (1-100)")
    ap.add_argument("--papel", default="236,226,203",
                    help="color RGB al que se iguala el papel, o 'original' para no tocar el color")
    ap.add_argument("--saturacion", type=float, default=1.0,
                    help="multiplica la saturación (1.0 = igual; 1.2 = +20%%, para láminas desvanecidas)")
    ap.add_argument("--contraste", type=float, default=1.0,
                    help="multiplica el contraste (1.0 = igual; 1.1 = +10%%)")
    ap.add_argument("--lado-max", type=int, default=0,
                    help="lado mayor máximo en px (3508 = A4 a 300 DPI; 0 = sin reducir)")
    ap.add_argument("--solo-color", nargs="?", type=float, const=15.0, default=None, metavar="UMBRAL",
                    help="omite páginas casi sin color (texto). Umbral por defecto 15; súbelo si se cuelan "
                         "páginas de texto, bájalo si se pierden láminas pálidas")
    ap.add_argument("--max-color", type=float, default=None, metavar="UMBRAL",
                    help="omite páginas con colorido mayor a UMBRAL (cubiertas, guardas estampadas)")
    ap.add_argument("--min-papel", type=float, default=None, metavar="PCT",
                    help="omite páginas con menos de PCT%% de papel visible (cubiertas, guardas). Sugerido: 25")
    ap.add_argument("--medir", action="store_true",
                    help="solo mide el colorido de cada página y lo imprime, sin procesar nada")
    args = ap.parse_args()
    papel = None if args.papel == "original" else tuple(int(v) for v in args.papel.split(","))

    archivos = sorted(p for p in args.entrada.iterdir() if p.suffix.lower() in EXTENSIONES)
    if not archivos:
        sys.exit(f"No hay imágenes en {args.entrada}")
    if args.medir:
        print(f"{'color':>7}  {'papel%':>6}  archivo")
        for p in archivos:
            img = cv2.imread(str(p), cv2.IMREAD_COLOR)
            if img is None:
                print(f"{'ERROR':>7}  {'':>6}  {p.name}")
            else:
                print(f"{colorido(img):7.1f}  {fraccion_papel(img):6.0f}  {p.name}")
        return
    args.salida.mkdir(parents=True, exist_ok=True)
    guardadas = 0
    for i, p in enumerate(archivos, 1):
        destino = args.salida / (p.stem + ".jpg")
        msg = procesar(p, destino, args.margen, args.calidad, papel, args.saturacion, args.contraste,
                       args.lado_max, args.solo_color, args.max_color, args.min_papel)
        guardadas += "OMITIDA" not in msg and not msg.startswith("ERROR")
        print(f"[{i}/{len(archivos)}] {msg}")
    print(f"Listo: {guardadas} láminas guardadas de {len(archivos)} páginas, en {args.salida}")


if __name__ == "__main__":
    main()
