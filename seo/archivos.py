"""
seo/archivos.py — Los archivos que recibe el comprador: revisar y cambiar .7z por .zip (15 oct 2026).

Por qué: los listings hechos a mano antes del pipeline entregan .7z. Una Mac no lo abre sin instalar otro programa
y un teléfono tampoco: el comprador paga y no puede abrir lo que compró. El pipeline ya entrega .zip; esto arregla
los viejos.

Etsy no deja descargar por la API los archivos que vendes, así que los .7z originales salen de tu PC:
  1) desde tu PC:  scp *.7z root@VPS:/home/minion/caligari/sietez/
  2) en el VPS:    python3 -m seo.archivos --revisar                 qué archivo entrega cada listing
                   python3 -m seo.archivos --convertir /home/minion/caligari/sietez          vista previa
                   python3 -m seo.archivos --convertir /home/minion/caligari/sietez --si     lo hace

Seguridad: sin --si no cambia nada. Para cada listing: extrae el .7z, arma el .zip con exactamente los mismos
archivos (lo comprueba), sube el .zip y SOLO DESPUÉS borra el .7z del listing; si la subida falla, el .7z se queda.
Los .zip quedan guardados en sietez/zip/ por si hay que volver a subirlos.
"""
import argparse
import json
import mimetypes
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import etsy  # noqa: E402
from seo import inventario  # noqa: E402

MAX_ETSY = 20 * 1024 * 1024


def archivos_de(shop_id, lid):
    return etsy.llamar("GET", f"/shops/{shop_id}/listings/{lid}/files").get("results", [])


def subir(shop_id, lid, ruta, rank=1):
    """POST multipart (etsy.llamar solo manda formularios simples)."""
    limite = f"----caligari{uuid.uuid4().hex}"
    cuerpo = bytearray()
    for k, v in {"name": ruta.name, "rank": str(rank)}.items():
        cuerpo += f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    cuerpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{ruta.name}\"\r\n"
               f"Content-Type: {mimetypes.guess_type(ruta.name)[0] or 'application/zip'}\r\n\r\n").encode()
    cuerpo += ruta.read_bytes() + f"\r\n--{limite}--\r\n".encode()
    url = f"{etsy.API}/shops/{shop_id}/listings/{lid}/files"
    req = urllib.request.Request(url, data=bytes(cuerpo), method="POST", headers={
        "x-api-key": etsy.cabecera_llave(), "Authorization": f"Bearer {etsy.token_vigente()}",
        "Content-Type": f"multipart/form-data; boundary={limite}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise etsy.ErrorEtsy(f"Etsy respondió {e.code} al subir {ruta.name}: {e.read().decode('utf-8', 'replace')[:300]}") from None


def extraer_7z(origen, destino):
    if shutil.which("7z"):
        r = subprocess.run(["7z", "x", "-y", f"-o{destino}", str(origen)], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"7z no pudo abrir {origen.name}: {r.stderr[-300:]}")
        return
    try:
        import py7zr
    except ImportError:
        sys.exit("Falta 7z. Instálalo una vez con:  apt install -y p7zip-full")
    with py7zr.SevenZipFile(origen) as z:
        z.extractall(destino)


def a_zip(origen, carpeta_zip):
    """Convierte X.7z en X.zip con los mismos archivos; comprueba que la lista coincide."""
    carpeta_zip.mkdir(parents=True, exist_ok=True)
    destino = carpeta_zip / (origen.stem + ".zip")
    with tempfile.TemporaryDirectory() as tmp:
        extraer_7z(origen, tmp)
        base = Path(tmp)
        dentro = sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in dentro:
                z.write(base / rel, rel)
    with zipfile.ZipFile(destino) as z:
        if sorted(z.namelist()) != dentro or z.testzip() is not None:
            raise RuntimeError(f"el zip de {origen.name} no quedó igual que el 7z")
    return destino, len(dentro)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--revisar", action="store_true")
    g.add_argument("--convertir", metavar="CARPETA")
    ap.add_argument("--si", action="store_true")
    a = ap.parse_args()
    foto = inventario.ultima_foto()
    if not foto:
        sys.exit("No hay foto del catálogo: corre /seo primero.")
    shop_id = foto["shop_id"]
    resumen = {"zip": 0, "7z": 0, "otro": 0}
    pendientes = []
    for x in foto["listings"]:
        fs = archivos_de(shop_id, x["id"])
        for f in fs:
            ext = Path(f.get("filename", "")).suffix.lower().lstrip(".")
            resumen[ext if ext in resumen else "otro"] += 1
            if ext == "7z":
                pendientes.append((x, f))
        if a.revisar:
            print(f"{x['id']} · {x['titulo'][:50]} → " + ", ".join(f"{f.get('filename')} ({f.get('filesize')})" for f in fs))
    print(f"\nArchivos: {resumen['zip']} .zip · {resumen['7z']} .7z · {resumen['otro']} otros")
    if a.revisar:
        return
    carpeta = Path(a.convertir)
    hechos, faltan = 0, []
    for x, f in pendientes:
        origen = carpeta / f["filename"]
        if not origen.exists():
            faltan.append(f["filename"])
            continue
        nuevo, n = a_zip(origen, carpeta / "zip")
        if nuevo.stat().st_size > MAX_ETSY:
            print(f"✖ {nuevo.name} pesa más de 20 MB; Etsy no lo acepta. Se queda el .7z.")
            continue
        print(f"{x['id']} · {f['filename']} → {nuevo.name} ({n} archivos, {nuevo.stat().st_size // 1024} KB)")
        if a.si:
            subir(shop_id, x["id"], nuevo, rank=f.get("rank", 1))
            etsy.llamar("DELETE", f"/shops/{shop_id}/listings/{x['id']}/files/{f['listing_file_id']}")
            hechos += 1
    print(f"\n{'Cambiados' if a.si else 'Listos para cambiar (agrega --si)'}: {hechos if a.si else len(pendientes) - len(faltan)}")
    if faltan:
        print("No encontré en la carpeta: " + ", ".join(faltan))


if __name__ == "__main__":
    main()
