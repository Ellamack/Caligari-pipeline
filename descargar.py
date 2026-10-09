"""
descargar.py — Etapa 2: baja las páginas de un libro de Archive.org y crea su manifiesto.

Qué hace:
  1. Lee la ficha del libro en Archive.org (título, autor, fecha, derechos, archivos).
  2. Escoge la mejor fuente en cascada (principio 4):
       _jp2.zip  →  _orig_jp2.tar  →  si solo hay PDF, se detiene y avisa.
  3. Descarga con reanudación (si se corta, sigue donde iba) y verifica el MD5.
  4. Descomprime las páginas en libros/<id>/crudo/ y borra el ZIP para ahorrar disco.
  5. Crea/actualiza libros/<id>/manifiesto.json (CONTRATO 2), etapa "descarga".

Si se vuelve a correr y la etapa ya está "hecho", no hace nada.

Uso:
  python descargar.py deuitlandschekap11779cram
  python descargar.py deuitlandschekap11779cram --linea B
  python descargar.py deuitlandschekap11779cram --forzar      # repite aunque ya esté hecho

Carpeta base: /home/minion/caligari (o la variable de entorno CALIGARI_BASE).
Solo usa la biblioteca estándar de Python.
"""
import argparse
import hashlib
import os
import shutil
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

import manifiesto as mf
from buscar_libros import AGENTE, FICHA, DETALLE, evaluar_derechos, laminas_declaradas, pedir_json, texto

DESCARGA = os.environ.get("CALIGARI_DESCARGA", "https://archive.org/download/{id}/{archivo}")
EXT_PAGINA = (".jp2", ".jpg", ".jpeg", ".tif", ".tiff", ".png")
BLOQUE = 1 << 20  # 1 MB


def escoger_fuente(ident, archivos):
    """Cascada: _jp2.zip → _orig_jp2.tar. Devuelve el dict del archivo o None."""
    por_nombre = {f.get("name", ""): f for f in archivos}
    for sufijo in ("_jp2.zip", "_orig_jp2.tar"):
        for nombre, f in por_nombre.items():
            if nombre.endswith(sufijo):
                return f
    return None


def md5_de(ruta):
    h = hashlib.md5()
    with open(ruta, "rb") as fh:
        for trozo in iter(lambda: fh.read(BLOQUE), b""):
            h.update(trozo)
    return h.hexdigest()


def bajar(url, destino, tamano_esperado, intentos=5):
    """Descarga con reanudación (HTTP Range) y reintentos con espera creciente."""
    espera = 5
    for intento in range(1, intentos + 1):
        ya = destino.stat().st_size if destino.exists() else 0
        if tamano_esperado and ya >= tamano_esperado:
            return
        headers = {"User-Agent": AGENTE}
        if ya:
            headers["Range"] = f"bytes={ya}-"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                reanuda = ya and r.status == 206
                modo = "ab" if reanuda else "wb"
                hecho = ya if reanuda else 0
                siguiente_aviso = 10
                with open(destino, modo) as fh:
                    while True:
                        trozo = r.read(BLOQUE)
                        if not trozo:
                            break
                        fh.write(trozo)
                        hecho += len(trozo)
                        if tamano_esperado:
                            pct = hecho * 100 // tamano_esperado
                            if pct >= siguiente_aviso:
                                print(f"    {pct}%  ({hecho // 1_000_000} de {tamano_esperado // 1_000_000} MB)")
                                siguiente_aviso = (pct // 10 + 1) * 10
            if tamano_esperado and destino.stat().st_size < tamano_esperado:
                # el servidor cerró antes de tiempo: se reanuda en el siguiente intento
                raise IOError(f"conexión cortada en {destino.stat().st_size // 1_000_000} MB")
            return
        except Exception as e:
            print(f"    intento {intento}/{intentos} falló: {e}", file=sys.stderr)
            if intento == intentos:
                raise
            time.sleep(espera)
            espera *= 2


def extraer(paquete, destino):
    """Saca solo las imágenes de página, sin subcarpetas (todo plano en destino/)."""
    destino.mkdir(parents=True, exist_ok=True)
    n = 0
    if paquete.suffix == ".zip":
        with zipfile.ZipFile(paquete) as z:
            for info in z.infolist():
                nombre = Path(info.filename).name
                if not info.is_dir() and nombre.lower().endswith(EXT_PAGINA):
                    with z.open(info) as src, open(destino / nombre, "wb") as dst:
                        shutil.copyfileobj(src, dst, BLOQUE)
                    n += 1
    else:
        with tarfile.open(paquete) as t:
            for miembro in t.getmembers():
                nombre = Path(miembro.name).name
                if miembro.isfile() and nombre.lower().endswith(EXT_PAGINA):
                    with t.extractfile(miembro) as src, open(destino / nombre, "wb") as dst:
                        shutil.copyfileobj(src, dst, BLOQUE)
                    n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id", help="identificador de Archive.org (columna ID de candidatos)")
    ap.add_argument("--linea", choices=("A", "B"), default="A")
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args()
    ident = args.id

    m = mf.leer(ident)
    if m and mf.hecho(m, "descarga") and not args.forzar:
        print(f"{ident}: la descarga ya está hecha ({m['etapas']['descarga'].get('paginas')} páginas). Nada que hacer.")
        return

    print(f"Leyendo la ficha de {ident}…")
    ficha = pedir_json(FICHA.format(id=ident))
    meta = ficha.get("metadata", {})
    anio_txt = texto(meta.get("year") or meta.get("date"))
    anio = int(anio_txt[:4]) if anio_txt[:4].isdigit() else None
    apto, nota_derechos = evaluar_derechos(meta, anio)
    datos_meta = {
        "titulo": texto(meta.get("title")),
        "autor": texto(meta.get("creator")),
        "fecha": anio_txt[:20],
        "derechos": nota_derechos,
        "laminas_declaradas": laminas_declaradas(texto(meta.get("description"))),
        "url": DETALLE.format(id=ident),
    }
    if m is None:
        m = mf.nuevo(ident, datos_meta, args.linea)
    else:
        m["meta"].update(datos_meta)
    mf.guardar(m)

    if not apto:
        mf.marcar(m, "descarga", "error", motivo=nota_derechos)
        sys.exit(f"ALTO: {nota_derechos}. Revisa la ficha antes de usar este libro: {datos_meta['url']}")

    fuente = escoger_fuente(ident, ficha.get("files", []))
    if fuente is None:
        mf.marcar(m, "descarga", "error", motivo="sin _jp2.zip ni _orig_jp2.tar (solo PDF)")
        sys.exit("ALTO: este libro solo tiene PDF. No se procesa: la compresión del PDF degrada las láminas.")

    nombre = fuente["name"]
    tamano = int(fuente.get("size", 0))
    crudo = mf.carpeta(ident) / "crudo"
    crudo.mkdir(parents=True, exist_ok=True)
    paquete = crudo / nombre
    mf.marcar(m, "descarga", "en_curso", archivo=nombre, mb=round(tamano / 1e6, 1))

    print(f"Descargando {nombre} ({tamano // 1_000_000} MB)…")
    url = DESCARGA.format(id=ident, archivo=nombre)
    md5_ok = False
    for vuelta in (1, 2):
        bajar(url, paquete, tamano)
        print("  Verificando MD5…")
        md5_ok = (not fuente.get("md5")) or md5_de(paquete) == fuente["md5"]
        if md5_ok:
            break
        print("  MD5 no coincide: el archivo llegó dañado. Se borra y se baja otra vez.", file=sys.stderr)
        paquete.unlink()
    if not md5_ok:
        mf.marcar(m, "descarga", "error", motivo="MD5 no coincide tras 2 descargas")
        sys.exit("ERROR: el archivo llega dañado dos veces seguidas. Intenta más tarde.")

    print("  Descomprimiendo páginas…")
    paginas = extraer(paquete, crudo / "paginas")
    paquete.unlink()  # el ZIP ya no hace falta: ahorra 140–270 MB de disco
    mf.marcar(m, "descarga", "hecho", archivo=nombre, md5_ok=True, paginas=paginas,
              carpeta=str(crudo / "paginas"))
    print(f"Listo: {paginas} páginas en {crudo / 'paginas'}")
    if m["meta"]["laminas_declaradas"]:
        print(f"  La ficha declara {m['meta']['laminas_declaradas']} láminas (sirve para validar la etapa 3).")


if __name__ == "__main__":
    main()
