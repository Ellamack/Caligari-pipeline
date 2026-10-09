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
ETAPAS = ("descarga", "procesar", "revision", "empaquetar", "ficha")
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
    m["etapas"][etapa].update(datos)
    m["etapas"][etapa]["estado"] = estado
    m["etapas"][etapa]["fecha"] = datetime.now().isoformat(timespec="seconds")
    guardar(m)


def hecho(m, etapa):
    return m["etapas"][etapa]["estado"] == "hecho"
