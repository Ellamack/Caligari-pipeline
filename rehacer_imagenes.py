"""
rehacer_imagenes.py — Vuelve a generar las imágenes del listing (portada, mocos, pin) de un libro ya
empaquetado, sacando las láminas de su ZIP. No toca el ZIP, ni el PDF, ni el enlace de los compradores.

Sirve cuando cambia el diseño (plantillas/diseno.json, un estilo, una fuente, los mocos) o un dato
(tema, obra, fecha) después de empaquetar.

Uso:
  python3 rehacer_imagenes.py ID                 rehace con el estilo del libro; sube el kit a Drive
  python3 rehacer_imagenes.py ID vintage         cambia el libro al estilo "vintage" y rehace
  python3 rehacer_imagenes.py ID base            vuelve al estilo base (diseno.json)
  python3 rehacer_imagenes.py ID vintage --prueba
        solo prueba: te manda por Telegram una vista previa de todo el listing con ese estilo;
        no cambia el libro, ni sus imágenes, ni Drive.
En Telegram: /imagenes ID [estilo]   ·   /probar ID [estilo]
"""
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

import diseno
import manifiesto as mf
from empaquetar import (autor_legible, estilo_del_libro, fecha_legible, imagenes_listing, obra_corta,
                        subir_kit, vistas_b)
from telegram_puente import avisar


def vista_previa(imagenes, destino, ancho=1800):
    """Todas las imágenes del listing en una sola, en el orden de Etsy (una foto en Telegram, no ocho)."""
    cols = 3
    celda = ancho // cols
    filas = -(-len(imagenes) // cols)
    hoja = Image.new("RGB", (ancho, filas * celda), (235, 228, 214))
    for k, ruta in enumerate(imagenes):
        with Image.open(ruta) as im:
            im = im.convert("RGB")
            im.thumbnail((celda - 20, celda - 20))
            f, c = divmod(k, cols)
            hoja.paste(im, (c * celda + (celda - im.width) // 2, f * celda + (celda - im.height) // 2))
    hoja.save(destino, "JPEG", quality=85)
    return destino


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    prueba = "--prueba" in sys.argv
    if not 1 <= len(args) <= 2:
        sys.exit(__doc__)
    ident, estilo = args[0], (args[1] if len(args) == 2 else None)
    m = mf.leer(ident)
    if m is None or not mf.hecho(m, "empaquetar"):
        avisar(f"✖ {ident}: todavía no está empaquetado; no hay imágenes que rehacer.")
        sys.exit(1)
    if estilo and estilo not in ("base", "default") and estilo not in diseno.estilos_disponibles():
        avisar(f"✖ No existe el estilo «{estilo}». Hay: base, {', '.join(diseno.estilos_disponibles()) or '(ninguno más)'}")
        sys.exit(1)
    e = m["etapas"]["empaquetar"]
    bundle = mf.carpeta(ident) / "bundle"
    zip_completo = bundle / e["zip"]
    if not zip_completo.exists():
        avisar(f"✖ {ident}: no encuentro {zip_completo.name} en el VPS; sin él no hay láminas para rehacer.")
        sys.exit(1)

    meta = m["meta"]
    if estilo and not prueba:  # el estilo queda guardado en el libro: la próxima vez se rehace igual
        meta.pop("estilo", None) if estilo in ("base", "default") else meta.update(estilo=estilo)
        mf.guardar(m)
    nombre_estilo, ajustes = estilo_del_libro(m)
    if prueba and estilo:
        nombre_estilo = estilo
    diseno.usar(nombre_estilo, ajustes)
    print(diseno.resumen())

    datos = {"tema": meta.get("tema", ""), "obra": meta.get("obra") or obra_corta(meta.get("titulo", "")),
             "autor": autor_legible(meta.get("autor", "")), "fecha": fecha_legible(meta)}
    lado = m["etapas"]["procesar"].get("params", {}).get("lado_max", 3508)

    tmp = Path(tempfile.mkdtemp(prefix=f"{ident}_"))
    destino = tmp / "bundle" if prueba else bundle  # la prueba no pisa las imágenes buenas
    destino.mkdir(exist_ok=True)
    try:
        linea = m.get("linea", "A")
        with zipfile.ZipFile(zip_completo) as z:
            for n in z.namelist():
                if (linea == "B" and n.startswith("PNG/") and n.lower().endswith(".png")) or \
                        ("_plate_" in n and n.lower().endswith(".jpg")):
                    z.extract(n, tmp / "laminas")
        if linea == "B":  # figuras transparentes → sobre papel (si no, la transparencia sale negra)
            finales = vistas_b(sorted((tmp / "laminas").rglob("*.png")), tmp / "vistas")
        else:
            finales = sorted((tmp / "laminas").rglob("*_plate_*.jpg"))
        print(f"{len(finales)} {'figuras' if linea == 'B' else 'láminas'} sacadas del ZIP")
        portada, hechos = imagenes_listing(finales, destino, e["titulo"], datos, len(finales), lado, linea=linea)
        if prueba:
            vista = vista_previa([portada] + hechos, tmp / "vista_previa.jpg")
            avisar(f"👁 Prueba de estilo «{diseno.actual()['nombre']}» para {ident} "
                   f"({len(hechos)} mocos: {', '.join(diseno.lista_mocos())}).\n"
                   f"No cambié nada. Si te gusta: /imagenes {ident} {diseno.actual()['nombre']}", imagen=vista)
            return
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # la vista previa de prueba ya salió por Telegram

    prod = {**e, "portada": portada.name,
            "mocos": [f"mocos/{h.name}" for h in hechos if not h.name.startswith("pin_")],
            "pin": next((f"mocos/{h.name}" for h in hechos if h.name.startswith("pin_")), None),
            "pines": [f"mocos/{h.name}" for h in hechos if h.name.startswith("pin_")]}
    pdf = bundle / e["pdf"] if e.get("pdf") else None
    kit = subir_kit(ident, bundle, prod, pdf)
    mf.marcar(m, "empaquetar", "hecho", mocos=prod["mocos"], pin=prod["pin"], pines=prod["pines"], **({"kit": kit} if kit else {}))
    vista = vista_previa([portada] + hechos, bundle / "vista_previa.jpg")
    avisar(f"🖼 {ident}: imágenes rehechas con el estilo «{diseno.actual()['nombre']}» "
           f"({datos['obra']} · {datos['fecha']}).\nEn Etsy van en este orden: portada, "
           + ", ".join(Path(x).stem for x in prod["mocos"]) + "."
           + (f"\nKit del listing en Drive → {kit}" if kit else ""), imagen=vista)
    for k, pin in enumerate(prod["pines"], 1):
        avisar(f"{ident} · pin vertical {k}/{len(prod['pines'])}", imagen=bundle / pin)


if __name__ == "__main__":
    main()
