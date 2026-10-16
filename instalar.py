"""
instalar.py — Instalar un paquete de código mandado por Telegram, sin terminal (15 oct 2026).

Por qué: cada cambio de código esperaba a que Elandrés llegara a casa (scp + unzip + md5sum desde su terminal).
Ahora: manda el .zip al bot con el texto «/instalar» → el bot muestra qué cambia → «/instalar si» lo instala.

Seguridad (las mismas reglas que a mano, hechas por código):
  · Solo llega desde el chat autorizado (lo filtra telegram_puente.py antes de llamar aquí).
  · El zip debe traer su HUELLAS_*.md5 y cada archivo debe coincidir (md5sum -c). Ojo: esto prueba que el zip
    llegó entero, no quién lo hizo; la autoría la garantiza que solo tu chat puede mandarlo.
  · Solo rutas relativas dentro del pipeline, sin «..», sin .git, sin /etc, y solo tipos de texto conocidos.
  · Antes de escribir, respalda cada archivo que reemplaza en respaldos/instalar_<fecha>/.
  · Compila los .py nuevos; si alguno falla, restaura el respaldo y no deja nada a medias.
  · Hace commit local como el dueño de la carpeta (el push sigue siendo desde tu terminal).
  · /instalar deshacer → vuelve a la versión anterior desde el último respaldo.
"""
import hashlib
import io
import json
import py_compile
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).parent
RESPALDOS = AQUI.parent / "respaldos"
PENDIENTE = AQUI.parent / "instalar_pendiente.zip"
TIPOS = {".py", ".json", ".md", ".txt", ".csv", ".md5", ".svg", ".service"}
MAX_BYTES = 5 * 1024 * 1024


class Rechazo(Exception):
    pass


def _ruta_segura(nombre):
    p = Path(nombre)
    if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0] in (".git", "etc") or nombre.endswith("/"):
        raise Rechazo(f"ruta no permitida en el zip: {nombre}")
    if p.suffix not in TIPOS:
        raise Rechazo(f"tipo de archivo no permitido: {nombre}")
    return p


def revisar(datos):
    """Lee el zip en memoria y lo valida. Devuelve {ruta: bytes} sin tocar el disco."""
    if len(datos) > MAX_BYTES:
        raise Rechazo("el zip pasa de 5 MB")
    try:
        z = zipfile.ZipFile(io.BytesIO(datos))
    except zipfile.BadZipFile:
        raise Rechazo("no es un zip válido") from None
    archivos = {}
    for info in z.infolist():
        if info.is_dir():
            continue
        archivos[str(_ruta_segura(info.filename))] = z.read(info)
    huellas = [k for k in archivos if Path(k).name.startswith("HUELLAS_") and k.endswith(".md5")]
    if len(huellas) != 1:
        raise Rechazo("el zip debe traer exactamente un HUELLAS_*.md5")
    esperadas = {}
    for linea in archivos[huellas[0]].decode().splitlines():
        if linea.strip():
            md5, nombre = linea.split(None, 1)
            esperadas[nombre.strip().lstrip("*")] = md5
    contenido = {k: v for k, v in archivos.items() if k != huellas[0]}
    faltan = sorted(set(contenido) ^ set(esperadas))
    if faltan:
        raise Rechazo("HUELLAS no coincide con los archivos del zip: " + ", ".join(faltan))
    malos = [k for k, v in contenido.items() if hashlib.md5(v).hexdigest() != esperadas[k]]
    if malos:
        raise Rechazo("md5 no coincide (zip dañado): " + ", ".join(malos))
    return contenido


def resumen(contenido):
    """Qué archivo es nuevo y cuánto cambia cada uno (en líneas)."""
    filas = []
    for k, v in sorted(contenido.items()):
        actual = AQUI / k
        if not actual.exists():
            filas.append(f"＋ {k} (nuevo, {len(v.splitlines())} líneas)")
            continue
        viejo = actual.read_bytes()
        if viejo == v:
            filas.append(f"= {k} (igual)")
            continue
        import difflib
        d = list(difflib.unified_diff(viejo.decode(errors="replace").splitlines(),
                                      v.decode(errors="replace").splitlines(), lineterm="", n=0))
        mas = sum(1 for x in d if x.startswith("+") and not x.startswith("+++"))
        menos = sum(1 for x in d if x.startswith("-") and not x.startswith("---"))
        filas.append(f"✎ {k} (+{mas} −{menos})")
    return "\n".join(filas)


def _como_dueno():
    import os
    import pwd
    dueno = pwd.getpwuid(AQUI.stat().st_uid).pw_name
    return (["runuser", "-u", dueno, "--"] if os.geteuid() == 0 and dueno != "root" else []), AQUI.stat()


def _escribir(destino, datos, st):
    import os
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)
    if os.geteuid() == 0:
        os.chown(destino, st.st_uid, st.st_gid)


def instalar(contenido, nombre_zip):
    """Respalda, escribe, compila, hace commit. Si algo falla, restaura todo. Devuelve texto para Telegram."""
    antes, st = _como_dueno()
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    respaldo = RESPALDOS / f"instalar_{sello}"
    nuevos = []
    for k in contenido:
        actual = AQUI / k
        if actual.exists():
            (respaldo / k).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(actual, respaldo / k)
        else:
            nuevos.append(k)
    respaldo.mkdir(parents=True, exist_ok=True)
    (respaldo / "_nuevos.json").write_text(json.dumps(nuevos), encoding="utf-8")
    try:
        for k, v in contenido.items():
            _escribir(AQUI / k, v, st)
        for k in contenido:
            if k.endswith(".py"):
                py_compile.compile(str(AQUI / k), doraise=True)
    except Exception as e:  # noqa: BLE001
        _restaurar(respaldo)
        respaldo.rename(respaldo.with_name(respaldo.name.replace("instalar_", "fallido_")))
        raise Rechazo(f"no compila, dejé todo como estaba: {e}") from None
    git = antes + ["git", "-C", str(AQUI)]
    subprocess.run(git + ["add", "--", *contenido], capture_output=True, text=True)
    r = subprocess.run(git + ["commit", "-m", f"Instalado por Telegram: {nombre_zip}"], capture_output=True, text=True)
    commit = subprocess.run(git + ["log", "-1", "--format=%h"], capture_output=True, text=True).stdout.strip()
    return (f"✔ Instalado {nombre_zip}: {len(contenido)} archivos, commit local {commit if r.returncode == 0 else '(sin cambios)'}.\n"
            f"Respaldo en {respaldo}. Para volver atrás: /instalar deshacer\n"
            "El push a GitHub sigue siendo desde tu terminal (git push).")


def _restaurar(respaldo):
    _, st = _como_dueno()
    nuevos = json.loads((respaldo / "_nuevos.json").read_text(encoding="utf-8")) if (respaldo / "_nuevos.json").exists() else []
    for f in respaldo.rglob("*"):
        if f.is_file() and f.name != "_nuevos.json":
            _escribir(AQUI / f.relative_to(respaldo), f.read_bytes(), st)
    for k in nuevos:
        (AQUI / k).unlink(missing_ok=True)


def deshacer():
    hechos = sorted(RESPALDOS.glob("instalar_*"))
    if not hechos:
        raise Rechazo("no hay instalaciones que deshacer")
    ultimo = hechos[-1]
    _restaurar(ultimo)
    antes, _ = _como_dueno()
    git = antes + ["git", "-C", str(AQUI)]
    subprocess.run(git + ["add", "-A", "--", "."], capture_output=True, text=True)
    subprocess.run(git + ["commit", "-m", f"Deshecho: {ultimo.name}"], capture_output=True, text=True)
    ultimo.rename(ultimo.with_name(ultimo.name.replace("instalar_", "deshecho_")))
    return f"↩ Volví a la versión anterior a {ultimo.name}. Reinicio el bot."
