"""
drive.py — Subir archivos a Google Drive con rclone y sacar su enlace público.

rclone está configurado en el VPS con el remoto "caligari" (permiso drive.file: solo ve y toca
lo que él mismo creó; las carpetas de Elandrés, como caligari_entregas, quedan fuera de su alcance).

Carpetas que usa (las crea rclone en el Drive de automation.flow.env):
  Caligari_entregas_auto      ZIP completos que descargan los compradores (enlace público)
  Caligari_Elandres_revision  copias de lo que Elandrés revisa (hojas de contactos, portadas)

Principio 4 (cascada): si rclone no está o falla, quien llama sigue por el camino manual
(preguntar el enlace por Telegram). Nada de aquí debe detener el pipeline.
"""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

REMOTO = os.environ.get("CALIGARI_RCLONE", "caligari")
ENTREGAS = "Caligari_entregas_auto"
REVISION = "Caligari_Elandres_revision"


def _rclone(*args, timeout=1800):
    return subprocess.run(["rclone", *args], capture_output=True, text=True, timeout=timeout)


def disponible():
    """¿Hay rclone y está configurado el remoto?"""
    if not shutil.which("rclone"):
        return False
    try:
        r = _rclone("listremotes", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and f"{REMOTO}:" in r.stdout.split()


def _md5(ruta):
    h = hashlib.md5()
    with open(ruta, "rb") as fh:
        for trozo in iter(lambda: fh.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def subir(ruta, carpeta, verificar=True):
    """Sube `ruta` a carpeta/nombre. Si ya existe con ese nombre, rclone la actualiza en su lugar
    (mismo archivo en Drive → mismo enlace). Devuelve la ruta remota o lanza RuntimeError."""
    ruta = Path(ruta)
    destino = f"{REMOTO}:{carpeta}/{ruta.name}"
    r = _rclone("copyto", str(ruta), destino)
    if r.returncode != 0:
        raise RuntimeError(f"rclone no pudo subir {ruta.name}: {r.stderr.strip()[-300:]}")
    if verificar:  # Drive guarda el MD5 de cada archivo: se compara con el local
        r = _rclone("md5sum", destino, timeout=120)
        remoto = r.stdout.split()[0] if r.returncode == 0 and r.stdout.strip() else ""
        if remoto and remoto != _md5(ruta):
            raise RuntimeError(f"{ruta.name}: el MD5 en Drive no coincide con el local (subida dañada)")
    return destino


def enlace(destino):
    """Enlace público ('cualquiera con el enlace') del archivo ya subido."""
    r = _rclone("link", destino, timeout=120)
    url = r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else ""
    if not url.startswith("http"):
        raise RuntimeError(f"rclone no dio enlace para {destino}: {r.stderr.strip()[-300:]}")
    return url


def subir_y_enlazar(ruta, carpeta=ENTREGAS):
    return enlace(subir(ruta, carpeta))


def copia_revision(ruta, nombre=None):
    """Copia (sin enlace público) a la carpeta de revisión. Nunca falla: es solo comodidad."""
    try:
        if not disponible():
            return None
        ruta = Path(ruta)
        if nombre and nombre != ruta.name:
            destino = f"{REMOTO}:{REVISION}/{nombre}"
            return destino if _rclone("copyto", str(ruta), destino).returncode == 0 else None
        return subir(ruta, REVISION, verificar=False)
    except Exception as e:  # noqa: BLE001
        print(f"(copia a Drive no hecha: {e})")
        return None
