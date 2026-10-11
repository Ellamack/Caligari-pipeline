"""
rehacer_imagenes.py — Vuelve a generar las imágenes del listing (portada, mocos, pin) de un libro ya
empaquetado, sacando las láminas de su ZIP. No toca el ZIP, ni el PDF, ni el enlace de los compradores.

Sirve cuando cambia el diseño de las imágenes o un dato (tema, obra, fecha) después de empaquetar.
Al terminar: sube el kit del listing a Drive y te manda portada y pin por Telegram.

Uso:  python3 rehacer_imagenes.py ID          (o en Telegram: /imagenes ID)
"""
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import manifiesto as mf
from empaquetar import autor_legible, fecha_legible, imagenes_listing, obra_corta, subir_kit
from telegram_puente import avisar


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    ident = sys.argv[1]
    m = mf.leer(ident)
    if m is None or not mf.hecho(m, "empaquetar"):
        avisar(f"✖ {ident}: todavía no está empaquetado; no hay imágenes que rehacer.")
        sys.exit(1)
    e = m["etapas"]["empaquetar"]
    bundle = mf.carpeta(ident) / "bundle"
    zip_completo = bundle / e["zip"]
    if not zip_completo.exists():
        avisar(f"✖ {ident}: no encuentro {zip_completo.name} en el VPS; sin él no hay láminas para rehacer.")
        sys.exit(1)
    meta = m["meta"]
    datos = {"tema": meta.get("tema", ""), "obra": meta.get("obra") or obra_corta(meta.get("titulo", "")),
             "autor": autor_legible(meta.get("autor", "")), "fecha": fecha_legible(meta)}
    lado = m["etapas"]["procesar"].get("params", {}).get("lado_max", 3508)

    tmp = Path(tempfile.mkdtemp(prefix=f"{ident}_"))
    try:
        with zipfile.ZipFile(zip_completo) as z:
            laminas = [n for n in z.namelist() if "_plate_" in n and n.lower().endswith(".jpg")]
            for n in laminas:
                z.extract(n, tmp)
        finales = sorted(tmp.rglob("*_plate_*.jpg"))
        print(f"{len(finales)} láminas sacadas del ZIP")
        portada, hechos = imagenes_listing(finales, bundle, e["titulo"], datos, len(finales), lado)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    prod = {**e, "portada": portada.name,
            "mocos": [f"mocos/{h.name}" for h in hechos if not h.name.startswith("pin_")],
            "pin": next((f"mocos/{h.name}" for h in hechos if h.name.startswith("pin_")), None)}
    pdf = bundle / e["pdf"] if e.get("pdf") else None
    kit = subir_kit(ident, bundle, prod, pdf)
    mf.marcar(m, "empaquetar", "hecho", mocos=prod["mocos"], pin=prod["pin"], **({"kit": kit} if kit else {}))
    avisar(f"🖼 {ident}: imágenes rehechas ({datos['obra']} · {datos['fecha']})."
           + (f"\nKit del listing en Drive → {kit}" if kit else ""), imagen=portada)
    if prod["pin"]:
        avisar(f"{ident} · pin vertical", imagen=bundle / prod["pin"])


if __name__ == "__main__":
    main()
