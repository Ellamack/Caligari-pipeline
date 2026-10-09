"""
quitar_fondo.py — Quita el papel de láminas antiguas y deja la figura sobre fondo transparente (PNG).

Reemplaza el flujo manual de GIMP:
  desaturar → niveles → seleccionar por color → feather → borrar → aplicar al original

Cómo decide qué es figura y qué es papel:
  1. Estima el color del papel (mediana de los píxeles más claros).
  2. Mide qué tan distinto es cada píxel de ese papel (distancia ΔE en espacio Lab:
     cuenta luz Y color, así un ala amarillo pálido no se confunde con papel crema).
  3. Umbral: automático (Otsu) o el que tú le des con --umbral.
  4. Limpia motas sueltas (manchas de foxing, polvo) por tamaño.
  5. Fondo = papel CONECTADO con la orilla. Lo encerrado dentro de la figura
     (manchas claras en alas, reflejos) se queda como figura.
  6. Difumina la orilla (feather) y quita el halo color papel de los bordes.

Uso:
  # 1) Calibrar con una lámina: genera una tira con 5 umbrales para escoger a ojo
  python quitar_fondo.py lamina.jpg salida --probar

  # 2) Procesar una lámina o una carpeta completa con el umbral escogido
  python quitar_fondo.py cramer_listo cramer_png --umbral 18

  # 3) Igual, pero guardando cada ejemplar de la lámina en su propio PNG
  python quitar_fondo.py cramer_listo cramer_png --umbral 18 --separar

Opciones:
  --umbral N        distancia al papel a partir de la cual algo es figura (auto si se omite)
  --difuminado PX   suavizado de la orilla, como el feather de GIMP (default 2)
  --mancha PX       manchas más chicas que esto (en píxeles) se borran (default 150)
  --hueco PCT       huecos encerrados más grandes que este % de la imagen se vuelven
                    transparentes (p. ej. el espacio entre una rama y una hoja); los más
                    chicos se rellenan como figura (default 0.5)
  --separar         un PNG por cada ejemplar de la lámina
  --min-figura PCT  al separar, ignora figuras menores a este % de la imagen (default 0.3)
  --vista           además guarda un JPG de revisión: la figura sobre gris oscuro,
                    donde se notan halos y huecos

Requiere: pip install opencv-python-headless numpy pillow
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

EXTENSIONES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".jp2"}


def color_papel(lab):
    """Mediana Lab de los píxeles más claros (el papel domina las zonas claras)."""
    L = lab[..., 0]
    claros = L >= np.percentile(L, 60)
    return np.median(lab[claros], axis=0)


def distancia_papel(img_bgr):
    """ΔE (CIE76) de cada píxel respecto al color del papel."""
    lab = cv2.cvtColor(img_bgr.astype(np.float32) / 255.0, cv2.COLOR_BGR2LAB)
    papel = color_papel(lab)
    de = np.sqrt(((lab - papel) ** 2).sum(axis=2))
    return de, papel


def umbral_auto(de):
    """Otsu sobre el mapa de distancias (escalado a 0-255)."""
    tope = float(np.percentile(de, 99.5)) or 1.0
    esc = np.clip(de / tope * 255, 0, 255).astype(np.uint8)
    t, _ = cv2.threshold(esc, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return t / 255 * tope


def quitar_motas(mascara, min_px):
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(mascara, connectivity=8)
    grandes = np.zeros(n, bool)
    grandes[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_px
    return (grandes[etiquetas] * 255).astype(np.uint8)


def rellenar_huecos(mascara, hueco_max_px):
    """El fondo es el papel conectado con la orilla; los huecos encerrados se rellenan
    salvo que sean grandes (espacios reales entre partes de la figura)."""
    inv = cv2.bitwise_not(mascara)
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    h, w = mascara.shape
    toca_orilla = np.zeros(n, bool)
    for borde in (etiquetas[0, :], etiquetas[-1, :], etiquetas[:, 0], etiquetas[:, -1]):
        toca_orilla[np.unique(borde)] = True
    es_fondo = toca_orilla | (stats[:, cv2.CC_STAT_AREA] > hueco_max_px)
    es_fondo[0] = False  # etiqueta 0 = la figura misma en la imagen invertida
    fondo = es_fondo[etiquetas] & (inv > 0)
    return np.where(fondo, 0, 255).astype(np.uint8)


def construir_mascara(img, umbral, min_mancha, hueco_pct):
    de, papel = distancia_papel(img)
    t = umbral if umbral is not None else umbral_auto(de)
    m = (de > t).astype(np.uint8) * 255
    # cierre pequeño: reconecta trazos finos (antenas, patas) cortados por el umbral
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    m = quitar_motas(m, min_mancha)
    m = rellenar_huecos(m, hueco_pct / 100 * m.size)
    return m, t, papel, de


def alfa_y_desmanchado(img, mascara, difuminado, papel_lab, de, t):
    """Alfa suave + quita el halo de papel que queda en los píxeles de orilla.

    Dentro de la figura: opaco. En una franja de `difuminado` px alrededor: la opacidad
    sale de cuánta tinta tiene el píxel (su distancia al papel), así una orilla mitad
    tinta queda mitad transparente y los trazos finos no se pierden."""
    alfa = (mascara > 0).astype(np.float32)
    if difuminado > 0:
        k = int(2 * round(difuminado) + 1)
        caja = np.ones((k, k), np.uint8)
        nucleo = cv2.erode(mascara, np.ones((3, 3), np.uint8)) > 0
        # franja = orilla por fuera Y por dentro de la máscara (ahí están los píxeles mezclados)
        franja = (cv2.dilate(mascara, caja) > 0) & ~nucleo
        # "tinta pura" de referencia: la distancia al papel de la figura vecina más cercana
        ref = cv2.dilate((de * nucleo).astype(np.float32), caja)
        sin_ref = ref <= 0  # trazos finos sin núcleo: se quedan opacos dentro de la máscara
        piso = 0.5 * t
        suave = np.clip((de - piso) / np.maximum(ref - piso, 1e-3), 0, 1)
        suave = np.where(sin_ref, np.clip((de - piso) / piso, 0, 1), suave)
        alfa = np.where(franja, suave, alfa).astype(np.float32)
        alfa = cv2.GaussianBlur(alfa, (0, 0), 0.6)
        alfa = np.where(nucleo, 1.0, alfa)
    # color del papel en BGR 0-1
    papel_bgr = cv2.cvtColor(papel_lab.reshape(1, 1, 3).astype(np.float32),
                             cv2.COLOR_LAB2BGR).reshape(3)
    f = img.astype(np.float32) / 255
    a = alfa[..., None]
    orilla = (a > 0.05) & (a < 0.98)
    # píxel observado = a·figura + (1-a)·papel  →  figura = (obs - (1-a)·papel) / a
    limpio = np.where(orilla, (f - (1 - a) * papel_bgr) / np.maximum(a, 0.05), f)
    limpio = np.clip(limpio, 0, 1)
    return (limpio * 255).astype(np.uint8), (alfa * 255).astype(np.uint8)


def recortar_a_caja(rgba, pad=10):
    ys, xs = np.nonzero(rgba[..., 3] > 8)
    if len(xs) == 0:
        return rgba
    y0, y1 = max(0, ys.min() - pad), min(rgba.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(rgba.shape[1], xs.max() + pad + 1)
    return rgba[y0:y1, x0:x1]


def guardar_png(bgr, alfa, ruta):
    rgba = np.dstack([cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), alfa])
    Image.fromarray(recortar_a_caja(rgba)).save(ruta, "PNG", optimize=True, dpi=(300, 300))


def vista_previa(bgr, alfa, gris=40):
    a = alfa.astype(np.float32)[..., None] / 255
    return (bgr.astype(np.float32) * a + gris * (1 - a)).astype(np.uint8)


def figuras(mascara, min_px):
    """Agrupa partes cercanas (una antena suelta sigue siendo del mismo ejemplar)."""
    agrupada = cv2.dilate(mascara, np.ones((25, 25), np.uint8))
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(agrupada, connectivity=8)
    orden = sorted(range(1, n), key=lambda i: (stats[i, cv2.CC_STAT_TOP] // 200,
                                               stats[i, cv2.CC_STAT_LEFT]))
    for i in orden:
        if stats[i, cv2.CC_STAT_AREA] >= min_px:
            yield (etiquetas == i)


def procesar(ruta_in, carpeta_out, args):
    img = cv2.imread(str(ruta_in), cv2.IMREAD_COLOR)
    if img is None:
        return f"{ruta_in.name}: ERROR, no se pudo leer"
    mascara, t, papel, de = construir_mascara(img, args.umbral, args.mancha, args.hueco)
    limpio, alfa = alfa_y_desmanchado(img, mascara, args.difuminado, papel, de, t)
    base = ruta_in.stem
    if args.separar:
        k = 0
        for zona in figuras(mascara, args.min_figura / 100 * mascara.size):
            k += 1
            a = np.where(cv2.dilate(zona.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0, alfa, 0)
            guardar_png(limpio, a.astype(np.uint8), carpeta_out / f"{base}_{k:02d}.png")
        nota = f"{k} figuras"
    else:
        guardar_png(limpio, alfa, carpeta_out / f"{base}.png")
        nota = "1 PNG"
    if args.vista:
        cv2.imwrite(str(carpeta_out / f"{base}_vista.jpg"), vista_previa(limpio, alfa),
                    [cv2.IMWRITE_JPEG_QUALITY, 85])
    return f"{ruta_in.name}: {nota} (umbral {t:.1f})"


def probar(ruta_in, carpeta_out, args):
    """Tira con 5 umbrales alrededor del automático, para escoger a ojo."""
    img = cv2.imread(str(ruta_in), cv2.IMREAD_COLOR)
    de, _ = distancia_papel(img)
    base_t = args.umbral if args.umbral is not None else umbral_auto(de)
    paneles = []
    escala = 700 / img.shape[0]
    for f in (0.6, 0.8, 1.0, 1.25, 1.5):
        t = base_t * f
        m, _, papel, de2 = construir_mascara(img, t, args.mancha, args.hueco)
        limpio, alfa = alfa_y_desmanchado(img, m, args.difuminado, papel, de2, t)
        p = cv2.resize(vista_previa(limpio, alfa), None, fx=escala, fy=escala,
                       interpolation=cv2.INTER_AREA)
        cv2.putText(p, f"--umbral {t:.0f}", (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                    (255, 255, 255), 2, cv2.LINE_AA)
        paneles.append(p)
    tira = np.hstack(paneles)
    salida = carpeta_out / f"{ruta_in.stem}_prueba_umbrales.jpg"
    cv2.imwrite(str(salida), tira, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return f"Tira guardada en {salida}. Escoge el panel que se vea bien y usa ese --umbral."


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path, help="imagen o carpeta de imágenes")
    ap.add_argument("salida", type=Path, help="carpeta de salida")
    ap.add_argument("--umbral", type=float)
    ap.add_argument("--difuminado", type=float, default=2.0)
    ap.add_argument("--mancha", type=int, default=150)
    ap.add_argument("--hueco", type=float, default=0.5)
    ap.add_argument("--separar", action="store_true")
    ap.add_argument("--min-figura", type=float, default=0.3)
    ap.add_argument("--vista", action="store_true")
    ap.add_argument("--probar", action="store_true")
    args = ap.parse_args()

    args.salida.mkdir(parents=True, exist_ok=True)
    if args.entrada.is_dir():
        archivos = sorted(p for p in args.entrada.iterdir() if p.suffix.lower() in EXTENSIONES)
    else:
        archivos = [args.entrada]
    if args.probar:
        print(probar(archivos[0], args.salida, args))
        return
    for i, p in enumerate(archivos, 1):
        print(f"[{i}/{len(archivos)}] {procesar(p, args.salida, args)}")
    print(f"Listo: {len(archivos)} láminas procesadas, en {args.salida}")


if __name__ == "__main__":
    main()
