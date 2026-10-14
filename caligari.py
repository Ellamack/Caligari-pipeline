"""
caligari.py — Hace avanzar un libro por todas las etapas, solo, hasta la próxima pregunta.

Mira el manifiesto (CONTRATO 2), corre la etapa que sigue y repite. Se detiene cuando:
  · una etapa deja una pregunta sin contestar (te llega por Telegram),
  · el libro queda listo, o
  · algo falla (te llega el error con las últimas líneas del registro).
Volver a correrlo es siempre seguro: retoma donde se quedó.

Uso (normalmente lo lanza telegram_puente.py):
  python3 caligari.py ID [--linea B] [--tema "Butterfly"] [--obra "De Uitlandsche Kapellen, Vol. III"] [--fecha "1779-1782"]

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
    if OK.match(r.strip()):
        q = mf.BASE / "outbox" / f"{ident}_procesar.json"
        return json.loads(q.read_text(encoding="utf-8")).get("sugerido") if q.exists() else None
    n = re.search(r"\d+(?:[.,]\d+)?", r)
    return float(n.group().replace(",", ".")) if n else None


ROMANOS = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
OK = re.compile(r"^(ok|s[ií]|va|vale|listo)[.!]*$", re.I)


def sugerir_datos(ident, m):
    """Tema, obra y fecha para las imágenes del listing, adivinados de la ficha y de libros anteriores."""
    from empaquetar import fecha_legible, obra_corta
    meta = m["meta"]
    tema, obra = meta.get("tema") or "", meta.get("obra") or ""
    # mismo autor ya trabajado → mismo tema y mismo nombre de obra (Cramer → Butterfly, "De Uitlandsche Kapellen")
    for p in sorted((mf.BASE / "libros").glob("*/manifiesto.json")):
        otro = json.loads(p.read_text(encoding="utf-8"))
        if otro["id"] == ident or otro["meta"].get("autor") != meta.get("autor"):
            continue
        tema = tema or otro["meta"].get("tema", "")
        if not obra and otro["meta"].get("obra"):
            obra = re.sub(r",?\s*Vol\.?\s*[IVXLC\d]+\s*$", "", otro["meta"]["obra"], flags=re.I)
    obra = obra or obra_corta(meta.get("titulo", ""))
    n = re.search(r"\d+", meta.get("volumen") or "")
    if n and "vol" not in obra.lower() and int(n.group()) < len(ROMANOS):
        obra = f"{obra}, Vol. {ROMANOS[int(n.group())]}"
    obra = obra[:1].upper() + obra[1:]
    return {"tema": tema, "obra": obra, "fecha": fecha_legible(meta)}


def paginas_de_portada(ident):
    """Las primeras páginas del escaneo (ahí están título, tomo y año), en miniaturas grandes."""
    from procesar_laminas import hoja_contactos
    crudo = sorted((mf.carpeta(ident) / "crudo" / "paginas").glob("*"))[:8]
    hoja = hoja_contactos(crudo, mf.carpeta(ident) / "bundle" / "portada_libro.jpg", ancho=520, columnas=4) if crudo else None
    if hoja:
        import drive
        drive.copia_revision(hoja, f"{ident}_portada_libro.jpg")
    return hoja


def datos_listing(ident, m):
    """True si tema/obra/fecha ya están confirmados; si no, aplica la respuesta o deja la pregunta."""
    if m["meta"].get("datos_ok"):
        return True
    q = mf.BASE / "outbox" / f"{ident}_datos.json"
    r = mf.respuesta(ident, "datos")
    if r is not None and q.exists():
        datos = dict(json.loads(q.read_text(encoding="utf-8")).get("sugerido", {}))
        if not OK.match(r.strip()):
            for linea in r.splitlines():
                c = re.match(r"\s*(tema|obra|fecha)\s*[:=]?\s*(.+)", linea, re.I)
                if c:
                    datos[c.group(1).lower()] = c.group(2).strip()
        if datos.get("tema") and datos.get("obra"):
            m["meta"].update({"tema": datos["tema"], "obra": datos["obra"], "fecha_mostrar": datos.get("fecha", ""),
                              "datos_ok": True})
            mf.guardar(m)
            return True
    s = sugerir_datos(ident, m)
    if r is not None:  # contestó pero falta algo: lo que dijo se conserva en la nueva sugerencia
        s.update({k: v for k, v in (json.loads(q.read_text(encoding="utf-8")).get("sugerido") or {}).items() if v and not s.get(k)})
    portada = paginas_de_portada(ident)
    falta = "" if s["tema"] else "\n⚠ Falta el TEMA (p. ej. Butterfly, Bird, Botanical): escríbelo.\n"
    mf.preguntar(ident, "datos",
                 "Datos que verá el comprador en la portada, el pin y el título:\n\n"
                 f"tema: {s['tema'] or '(falta)'}\nobra: {s['obra']}\nfecha: {s['fecha']}\n{falta}\n"
                 "Compáralos con las primeras páginas del libro (la foto). Si están bien, escribe ok. "
                 "Para corregir, escribe solo la línea que cambia, p. ej.:\nfecha 1779-1782",
                 formato="ok | fecha 1779-1782", adjuntos=[portada] if portada else [], si_no_respondes=None,
                 sugerido=s)
    return False


def siguiente(ident, m, linea):
    """Qué etapa toca. Devuelve (script, args) o None si el libro espera o ya terminó."""
    if m is None or not mf.hecho(m, "descarga"):
        return "descargar.py", [ident, "--linea", linea]
    if not mf.hecho(m, "procesar"):
        if m["etapas"]["procesar"]["estado"] == "esperando":
            u = umbral_de_respuesta(ident)
            return ("procesar_laminas.py", ["--libro", ident, "--umbral", str(u)]) if u else None
        return "procesar_laminas.py", ["--libro", ident]
    if m.get("linea") == "B" and not mf.hecho(m, "restaurar"):
        # línea B: antes de empaquetar, quitar fondo → revisar figuras → (retoque) → vectorizar
        return "restaurar.py", [ident]
    if not mf.hecho(m, "empaquetar"):
        if not datos_listing(ident, m):
            return None
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

    datos_cli = {"tema": a.tema, "obra": a.obra, "fecha_mostrar": a.fecha}
    for _ in range(MAX_PASOS):
        m = mf.leer(ident)
        if m and any(datos_cli.values()):  # tema/obra/fecha de /nuevo: al manifiesto, una vez
            m["meta"].update({k: v for k, v in datos_cli.items() if v})
            if a.tema and a.obra:
                m["meta"]["datos_ok"] = True  # los dio él mismo: no hace falta preguntar
            mf.guardar(m)
            datos_cli = {}
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
               f"Para Etsy: {e.get('pdf')} + {e.get('muestra')}; "
               + (f"todo en Drive → {e['kit']}.\n" if e.get("kit") else f"imágenes en {bundle}.\n") +
               "Recuerda agregarlo a la oferta Bundles 50% al publicar.",
               imagen=bundle / "portada.jpg")
        pines = sorted((bundle / "mocos").glob("pin_*.jpg"))
        for k, pin in enumerate(pines, 1):
            avisar(f"{ident} · pin vertical para Pinterest {k}/{len(pines)}", imagen=pin)
        avisar(f"¿Otro look? /probar {ident} ESTILO te muestra el listing con otro estilo sin cambiar nada "
               "(/estilos para verlos).")
    elif m and not any(q for q in (mf.BASE / "outbox").glob(f"{ident}_*.json")
                       if not (mf.BASE / "inbox" / q.name).exists()):
        estados = ", ".join(f"{k}: {v['estado']}" for k, v in m["etapas"].items())
        avisar(f"⚠ {ident} se detuvo sin pregunta pendiente ({estados}). Revisa registro.log o /seguir {ident}.")


if __name__ == "__main__":
    main()
