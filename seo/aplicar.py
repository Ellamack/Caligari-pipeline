"""
seo/aplicar.py — Aplica en Etsy las propuestas de Caligari que apruebas (título y tags; descripción solo si lo pides).

Seguridad:
  · Sin --si no cambia nada: solo muestra qué cambiaría.
  · Antes de escribir, vuelve a leer el listing en Etsy. Si alguien lo editó después de la propuesta (título o tags
    distintos a los que Caligari vio), lo salta y avisa: no pisa cambios hechos a mano.
  · Solo aplica propuestas que pasaron todas las reglas (sin «_problemas»).
  · Guarda un respaldo antes/después en seo/datos/aplicados/; --deshacer ID devuelve el listing a como estaba.

Uso (en el VPS, como root, desde la carpeta del pipeline):
  python3 -m seo.aplicar --todos                         muestra lo que cambiaría en todos
  python3 -m seo.aplicar --todos --si                    lo aplica
  python3 -m seo.aplicar --todos --excepto 111,222 --si  todos menos esos
  python3 -m seo.aplicar --listing 4572865407 --si       uno
  python3 -m seo.aplicar --deshacer 4572865407 --si      regresa ese listing a como estaba antes de aplicar
  Opciones: --descripcion (también cambia la descripción) · --telegram (manda el resumen)
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import etsy  # noqa: E402
from seo import inventario  # noqa: E402
from seo.validar import norm_tag  # noqa: E402

PROPUESTAS = inventario.DATOS / "propuestas"
APLICADOS = inventario.DATOS / "aplicados"


def propuestas(ids=None):
    r = []
    for f in sorted(PROPUESTAS.glob("*.json")):
        p = json.loads(f.read_text(encoding="utf-8"))
        if ids is None or str(p.get("_id")) in ids:
            r.append((f, p))
    return r


def mismos_tags(a, b):
    return sorted(norm_tag(t) for t in (a or [])) == sorted(norm_tag(t) for t in (b or []))


def actual(listing_id):
    import html
    x = etsy.llamar("GET", f"/listings/{listing_id}")
    return {"titulo": html.unescape(x.get("title", "")), "tags": [html.unescape(t) for t in x.get("tags", [])],
            "descripcion": html.unescape(x.get("description", "")), "estado": x.get("state")}


def escribir(shop_id, listing_id, titulo, tags, descripcion=None):
    datos = {"title": titulo, "tags": ",".join(tags)}
    if descripcion is not None:
        datos["description"] = descripcion
    return etsy.llamar("PATCH", f"/shops/{shop_id}/listings/{listing_id}", datos=datos)


def aplicar(seleccion, shop_id, si, con_descripcion):
    hechos, saltados = [], []
    for f, p in seleccion:
        lid = p["_id"]
        if p.get("_problemas"):
            saltados.append((lid, "no pasa las reglas: " + "; ".join(p["_problemas"])))
            continue
        if p.get("_aplicado"):
            saltados.append((lid, f"ya aplicada el {p['_aplicado']}"))
            continue
        ahora = actual(lid)
        antes = p["_antes"]
        if ahora["titulo"] != antes.get("titulo") or not mismos_tags(ahora["tags"], antes.get("tags")):
            saltados.append((lid, "el listing cambió en Etsy después de la propuesta; vuelve a generarla"))
            continue
        desc = p.get("descripcion_en") if con_descripcion else None
        print(f"\n{lid}\n  título: {ahora['titulo']}\n       → {p['titulo_en']}\n  tags:   {', '.join(ahora['tags'])}"
              f"\n       → {', '.join(p['tags_en'])}" + ("\n  descripción: se reemplaza" if desc else ""))
        if not si:
            continue
        APLICADOS.mkdir(parents=True, exist_ok=True)
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        (APLICADOS / f"{lid}_{sello}.json").write_text(json.dumps(
            {"id": lid, "antes": ahora, "despues": {"titulo": p["titulo_en"], "tags": p["tags_en"], "descripcion": desc}},
            ensure_ascii=False, indent=1), encoding="utf-8")
        escribir(shop_id, lid, p["titulo_en"], p["tags_en"], desc)
        p["_aplicado"] = sello
        f.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        hechos.append(lid)
        time.sleep(0.3)  # muy por debajo del límite de la API
    return hechos, saltados


def deshacer(lid, shop_id, si):
    respaldos = sorted(APLICADOS.glob(f"{lid}_*.json"))
    if not respaldos:
        sys.exit(f"No hay respaldo de {lid} en {APLICADOS}")
    r = json.loads(respaldos[-1].read_text(encoding="utf-8"))
    a = r["antes"]
    print(f"{lid} vuelve a:\n  {a['titulo']}\n  {', '.join(a['tags'])}")
    if si:
        escribir(shop_id, lid, a["titulo"], a["tags"], a["descripcion"] if r["despues"].get("descripcion") else None)
        prop = PROPUESTAS / f"{lid}.json"
        if prop.exists():  # la propuesta vuelve a quedar pendiente
            p = json.loads(prop.read_text(encoding="utf-8"))
            p.pop("_aplicado", None)
            prop.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        print("Hecho.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--listing")
    g.add_argument("--todos", action="store_true")
    g.add_argument("--deshacer")
    ap.add_argument("--excepto", default="")
    ap.add_argument("--si", action="store_true", help="sin esto no cambia nada")
    ap.add_argument("--descripcion", action="store_true")
    ap.add_argument("--telegram", action="store_true")
    a = ap.parse_args()
    foto = inventario.ultima_foto()
    if not foto:
        sys.exit("No hay foto del catálogo: corre /seo primero.")
    shop_id = foto["shop_id"]
    if a.deshacer:
        deshacer(a.deshacer, shop_id, a.si)
        return
    excepto = {x.strip() for x in a.excepto.split(",") if x.strip()}
    seleccion = [(f, p) for f, p in propuestas(None if a.todos else {a.listing}) if str(p["_id"]) not in excepto]
    if not seleccion:
        sys.exit("No encontré propuestas. Primero: python3 -m seo.generar --todos")
    hechos, saltados = aplicar(seleccion, shop_id, a.si, a.descripcion)
    texto = (("✅ Aplicados en Etsy: " if a.si else "Vista previa (nada cambió; agrega --si): ")
             + f"{len(hechos) if a.si else len(seleccion) - len(saltados)} listings."
             + ("".join(f"\n· {lid}: {motivo}" for lid, motivo in saltados) if saltados else ""))
    print("\n" + texto)
    if a.si and hechos:
        print("Para comparar en 2–3 semanas: /seo toma otra foto y muestra vistas y favoritos ganados por listing.")
    if a.telegram:
        from telegram_puente import avisar
        avisar(texto)


if __name__ == "__main__":
    main()
