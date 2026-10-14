"""
manifiesto.py — Leer y escribir el CONTRATO 2 (libros/<id>/manifiesto.json).

Lo usan todas las etapas. Nadie escribe el manifiesto "a mano": siempre por aquí,
así el formato es el mismo en todas partes (ver CONTRATOS.md).
"""
import json
import os
from datetime import datetime
from pathlib import Path

BASE = Path(os.environ.get("CALIGARI_BASE", "/home/minion/caligari"))
# Todo lo que Elandrés tiene que mirar con sus ojos llega aquí (y de aquí, a Drive con rclone).
REVISION = BASE / "Elandres_revision"
ETAPAS = ("descarga", "procesar", "revision", "restaurar", "empaquetar", "ficha")  # restaurar: solo línea B
ESTADOS = ("pendiente", "en_curso", "hecho", "esperando", "error")


def carpeta(ident):
    return BASE / "libros" / ident


def ruta(ident):
    return carpeta(ident) / "manifiesto.json"


def nuevo(ident, meta, linea="A"):
    return {
        "id": ident,
        "linea": linea,
        "meta": meta,
        "etapas": {e: {"estado": "pendiente"} for e in ETAPAS},
        "laminas": [],
    }


def leer(ident):
    p = ruta(ident)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def guardar(m):
    """Escritura atómica: si el proceso se cae a la mitad, el manifiesto anterior sigue intacto."""
    p = ruta(m["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def marcar(m, etapa, estado, **datos):
    assert etapa in ETAPAS, etapa
    assert estado in ESTADOS, estado
    m["etapas"].setdefault(etapa, {"estado": "pendiente"})  # manifiestos de antes de que existiera la etapa
    m["etapas"][etapa].update(datos)
    m["etapas"][etapa]["estado"] = estado
    m["etapas"][etapa]["fecha"] = datetime.now().isoformat(timespec="seconds")
    guardar(m)


def hecho(m, etapa):
    return m["etapas"].get(etapa, {}).get("estado") == "hecho"


# ---------------------------------------------------------------- CONTRATO 3: preguntas y respuestas
def _outbox(ident, etapa):
    return BASE / "outbox" / f"{ident}_{etapa}.json"


def _inbox(ident, etapa):
    return BASE / "inbox" / f"{ident}_{etapa}.json"


def preguntar(ident, etapa, pregunta, formato, adjuntos=(), si_no_respondes=None, horas=12, **extra):
    """Deja una pregunta en outbox/. si_no_respondes=None → espera siempre (lo público).
    Volver a preguntar anula la respuesta anterior (p. ej. si se reprocesa con otro umbral,
    la revisión vieja ya no vale). `extra`: datos para quien conteste (p. ej. un umbral sugerido)."""
    from datetime import timedelta
    p = _outbox(ident, etapa)
    p.parent.mkdir(parents=True, exist_ok=True)
    datos = {
        "libro": ident,
        "etapa": etapa,
        "pregunta": pregunta,
        "adjuntos": [str(a) for a in adjuntos],
        "formato": formato,
        "si_no_respondes": si_no_respondes,
        "vence": (datetime.now() + timedelta(hours=horas)).isoformat(timespec="minutes")
        if si_no_respondes is not None else None,
        **extra,
    }
    sin_plazo = lambda d: {k: v for k, v in d.items() if k != "vence"}  # noqa: E731
    contestada = _inbox(ident, etapa).exists()
    if p.exists() and not contestada and sin_plazo(json.loads(p.read_text(encoding="utf-8"))) == sin_plazo(datos):
        return p  # la misma pregunta sigue abierta: no se reescribe (ni se te vuelve a mandar)
    _inbox(ident, etapa).unlink(missing_ok=True)  # preguntar de nuevo anula una respuesta vieja
    p.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def respuesta(ident, etapa):
    """La respuesta de Elandrés; si no hay y ya venció, el valor por defecto; si no, None (seguir esperando)."""
    r = _inbox(ident, etapa)
    if r.exists():
        return json.loads(r.read_text(encoding="utf-8"))["respuesta"].strip()
    q = _outbox(ident, etapa)
    if q.exists():
        datos = json.loads(q.read_text(encoding="utf-8"))
        if datos["si_no_respondes"] is not None and datetime.now().isoformat() >= datos["vence"]:
            return datos["si_no_respondes"]
    return None
