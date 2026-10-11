"""
caligari.py — Hace avanzar un libro por todas las etapas, solo, hasta la próxima pregunta.

Mira el manifiesto (CONTRATO 2), corre la etapa que sigue y repite. Se detiene cuando:
  · una etapa deja una pregunta sin contestar (te llega por Telegram),
  · el libro queda listo, o
  · algo falla (te llega el error con las últimas líneas del registro).
Volver a correrlo es siempre seguro: retoma donde se quedó.

Uso (normalmente lo lanza telegram_puente.py):
  python3 caligari.py ID [--tema "Butterfly"] [--obra "De Uitlandsche Kapellen, Vol. III"] [--fecha "1779-1782"]

Registro de cada libro: libros/<ID>/registro.log
"""
import argparse
import fcntl
import json
import re
import subprocess
import sys
from pathlib import Path

import manifiesto as mf
from telegram_puente import avisar

AQUI = Path(__file__).parent
MAX_PASOS = 12  # cinturón de seguridad contra un bucle


def correr(ident, script, *args):
    """Corre una etapa; su salida va al registro del libro. Devuelve (ok, últimas líneas)."""
    log = mf.carpeta(ident) / "registro.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(f"\n===== {script} {' '.join(args)}\n")
        fh.flush()
        r = subprocess.run([sys.executable, str(AQUI / script), *args], cwd=AQUI,
                           stdout=fh, stderr=subprocess.STDOUT)
    cola = log.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
    return r.returncode == 0, "\n".join(cola)


def foto(m):
    """Estado de todas las etapas: si no cambia tras correr una, el libro está esperando."""
    return json.dumps({k: v["estado"] for k, v in m["etapas"].items()}, sort_keys=True) if m else ""


def umbral_de_respuesta(ident):
    """Respuesta a la pregunta 'procesar': 'ok' = el sugerido; 'umbral 25' o '25' = ese."""
    r = mf.respuesta(ident, "procesar")
    if r is None:
        return None
    if r.strip().lower() in ("ok", "si", "sí", "va"):
        q = mf.BASE / "outbox" / f"{ident}_procesar.json"
        return json.loads(q.read_text(encoding="utf-8")).get("sugerido") if q.exists() else None
    n = re.search(r"\d+(?:[.,]\d+)?", r)
    return float(n.group().replace(",", ".")) if n else None


def siguiente(ident, m, linea):
    """Qué etapa toca. Devuelve (script, args) o None si el libro espera o ya terminó."""
    if m is None or not mf.hecho(m, "descarga"):
        return "descargar.py", [ident, "--linea", linea]
    if not mf.hecho(m, "procesar"):
        if m["etapas"]["procesar"]["estado"] == "esperando":
            u = umbral_de_respuesta(ident)
            return ("procesar_laminas.py", ["--libro", ident, "--umbral", str(u)]) if u else None
        return "procesar_laminas.py", ["--libro", ident]
    if not mf.hecho(m, "empaquetar"):
        return "empaquetar.py", [ident]
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id")
    ap.add_argument("--tema")
    ap.add_argument("--obra")
    ap.add_argument("--fecha")
    ap.add_argument("--linea", choices=("A", "B"), default="A")
    a = ap.parse_args()
    ident = a.id

    # un solo caligari.py por libro a la vez (si llegan dos respuestas juntas, el segundo se retira)
    mf.carpeta(ident).mkdir(parents=True, exist_ok=True)
    candado = open(mf.carpeta(ident) / ".caligari.lock", "w")
    try:
        fcntl.flock(candado, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(f"{ident}: ya hay otro caligari.py trabajando en este libro.")
        return

    datos_listing = {"tema": a.tema, "obra": a.obra, "fecha_mostrar": a.fecha}
    for _ in range(MAX_PASOS):
        m = mf.leer(ident)
        if m and any(datos_listing.values()):  # tema/obra/fecha de /nuevo: al manifiesto, una vez
            m["meta"].update({k: v for k, v in datos_listing.items() if v})
            mf.guardar(m)
            datos_listing = {}
        paso = siguiente(ident, m, a.linea)
        if paso is None:
            break
        script, args = paso
        antes = foto(m)
        ok, cola = correr(ident, script, *args)
        if not ok:
            avisar(f"✖ {ident}: falló {script}.\n\nÚltimas líneas:\n{cola}\n\n"
                   f"Cuando esté resuelto: /seguir {ident}")
            return
        m = mf.leer(ident)
        if foto(m) == antes:  # la etapa corrió pero no avanzó: está esperando una respuesta
            break

    m = mf.leer(ident)
    if m and mf.hecho(m, "empaquetar"):
        bundle = mf.carpeta(ident) / "bundle"
        e = m["etapas"]["empaquetar"]
        avisar(f"✅ {ident} listo: {e.get('titulo', '')}\n"
               f"ZIP {e.get('mb')} MB · enlace en el PDF.\n"
               f"Para Etsy: {e.get('pdf')} + {e.get('muestra')}; imágenes en {bundle}.\n"
               "Recuerda agregarlo a la oferta Bundles 50% al publicar.",
               imagen=bundle / "portada.jpg")
        pin = bundle / "mocos" / "pin_pinterest.jpg"
        if pin.exists():
            avisar(f"{ident} · pin vertical para Pinterest", imagen=pin)
    elif m and not any(q for q in (mf.BASE / "outbox").glob(f"{ident}_*.json")
                       if not (mf.BASE / "inbox" / q.name).exists()):
        estados = ", ".join(f"{k}: {v['estado']}" for k, v in m["etapas"].items())
        avisar(f"⚠ {ident} se detuvo sin pregunta pendiente ({estados}). Revisa registro.log o /seguir {ident}.")


if __name__ == "__main__":
    main()
