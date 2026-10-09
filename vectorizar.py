"""
vectorizar.py — Convierte los PNG transparentes (salida de quitar_fondo.py) en SVG a color.

Reemplaza el flujo manual de Inkscape:
  importar → Trazar mapa de bits (multicolor, apilado, N pasos) → borrar el PNG
  → borrar restos de fondo → guardar como SVG optimizado → (opcional) exportar PNG

Qué hace:
  1. Opacidad binaria: lo semitransparente (orillas) se decide como figura o vacío,
     así no aparecen trazos de "orilla color papel" (los restos que borras a mano).
  2. Reduce la imagen a N colores (como los "pasos" de Inkscape), con k-means en
     espacio Lab para que los grupos de color se parezcan a como los ve el ojo.
  3. Traza cada color en modo apilado (cada capa cubre a la de abajo, sin huecos).
  4. Guarda un SVG compacto (coordenadas con pocos decimales).
  5. Opcional: re-exporta el SVG a PNG con Inkscape (la versión "simplificada").

Uso:
  python vectorizar.py cramer_png cramer_svg
  python vectorizar.py cramer_png cramer_svg --colores 24 --png
  python vectorizar.py figura.png salida --colores 34 --motas 6

Opciones:
  --colores N     número de colores (los "pasos" de Inkscape). Default 34
  --motas PX      ignora manchas de menos de PX píxeles al trazar. Default 4
  --suavizar      filtro de mediana antes de reducir colores (quita grano del papel/escaneo)
  --png           además exporta cada SVG a PNG usando Inkscape (debe estar instalado)

Requiere: pip install vtracer opencv-python-headless numpy pillow
"""
import argparse
import re
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import vtracer
from PIL import Image


def reducir_colores(rgba, n, suavizar):
    rgb = np.ascontiguousarray(rgba[..., :3])
    if suavizar:
        rgb = cv2.medianBlur(rgb, 3)
    opaco = rgba[..., 3] >= 128
    pix = rgb[opaco]
    if len(pix) == 0:
        return rgba
    lab = cv2.cvtColor(pix.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    # k-means sobre una muestra (rápido), luego cada píxel al centro más cercano
    rng = np.random.default_rng(0)
    muestra = lab[rng.choice(len(lab), min(len(lab), 60000), replace=False)]
    k = min(n, len(np.unique(muestra, axis=0)))
    criterio = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    cv2.setRNGSeed(0)
    _, _, centros = cv2.kmeans(muestra, k, None, criterio, 3, cv2.KMEANS_PP_CENTERS)
    etiquetas = np.empty(len(lab), np.int32)
    for i in range(0, len(lab), 200000):  # por bloques para no agotar memoria
        d = ((lab[i:i + 200000, None, :] - centros[None]) ** 2).sum(axis=2)
        etiquetas[i:i + 200000] = d.argmin(axis=1)
    centros_rgb = cv2.cvtColor(np.clip(centros, 0, 255).astype(np.uint8).reshape(-1, 1, 3),
                               cv2.COLOR_LAB2RGB).reshape(-1, 3)
    salida = np.zeros_like(rgba)
    salida[opaco, :3] = centros_rgb[etiquetas]
    salida[opaco, 3] = 255
    return salida


def compactar(svg):
    svg = re.sub(r"<!--.*?-->\s*", "", svg, flags=re.S)
    svg = re.sub(r"(\d+\.\d)\d+", r"\1", svg)  # 1 decimal basta a esta escala
    return svg


def inkscape():
    for c in (shutil.which("inkscape"),
              r"C:\Program Files\Inkscape\bin\inkscape.exe",
              r"C:\Program Files (x86)\Inkscape\bin\inkscape.exe"):
        if c and Path(c).exists():
            return c
    return None


def procesar(ruta_in, carpeta_out, args):
    rgba = np.array(Image.open(ruta_in).convert("RGBA"))
    q = reducir_colores(rgba, args.colores, args.suavizar)
    h, w = q.shape[:2]
    pixeles = [tuple(int(v) for v in p) for p in q.reshape(-1, 4)]
    svg = vtracer.convert_pixels_to_svg(
        pixeles, size=(w, h), colormode="color", hierarchical="stacked", mode="spline",
        filter_speckle=args.motas, color_precision=8, layer_difference=1,
        corner_threshold=60, length_threshold=4.0, max_iterations=10,
        splice_threshold=45, path_precision=2)
    svg = compactar(svg)
    destino = carpeta_out / f"{ruta_in.stem}.svg"
    destino.write_text(svg, encoding="utf-8")
    n_paths = svg.count("<path")
    nota = f"{n_paths} trazos, {destino.stat().st_size // 1024} KB"
    if args.png:
        exe = inkscape()
        if exe:
            subprocess.run([exe, str(destino), "--export-type=png",
                            f"--export-filename={carpeta_out / (ruta_in.stem + '_simplificado.png')}"],
                           check=False, capture_output=True)
            nota += ", PNG exportado"
        else:
            nota += ", (no encontré Inkscape para el PNG)"
    return f"{ruta_in.name}: {nota}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path, help="PNG transparente o carpeta de PNG")
    ap.add_argument("salida", type=Path)
    ap.add_argument("--colores", type=int, default=34)
    ap.add_argument("--motas", type=int, default=4)
    ap.add_argument("--suavizar", action="store_true")
    ap.add_argument("--png", action="store_true")
    args = ap.parse_args()
    args.salida.mkdir(parents=True, exist_ok=True)
    archivos = (sorted(p for p in args.entrada.iterdir()
                       if p.suffix.lower() == ".png" and not p.stem.endswith("_simplificado"))
                if args.entrada.is_dir() else [args.entrada])
    for i, p in enumerate(archivos, 1):
        print(f"[{i}/{len(archivos)}] {procesar(p, args.salida, args)}")
    print(f"Listo: {len(archivos)} SVG en {args.salida}")


if __name__ == "__main__":
    main()
