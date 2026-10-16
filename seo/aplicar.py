"""
seo/aplicar.py — Aplica en Etsy las propuestas de Caligari que apruebas: título y tags en inglés Y en español
(la traducción que ven los compradores con Etsy en español). La descripción solo si lo pides (--descripcion, inglés).

Seguridad:
  · Sin --si no cambia nada: solo muestra qué cambiaría.
  · Antes de escribir, vuelve a leer el listing en Etsy. Si alguien lo editó después de la propuesta (título o tags
    distintos a los que Caligari vio), lo salta y avisa: no pisa cambios hechos a mano.
  · Solo aplica propuestas que pasaron todas las reglas (sin «_problemas»).
  · Guarda un respaldo antes/después en seo/datos/aplicados/; --deshacer ID devuelve el listing a como estaba
    (inglés y español).
  · Español: la descripción en español se conserva; solo cambian título y tags. Si la propuesta no trae versión en
    español (propuestas anteriores al 15 oct), la pide al modelo a partir del inglés aprobado y la valida.

Uso (en el VPS, como root, desde la carpeta del pipeline):
  python3 -m seo.aplicar --todos                         muestra lo que cambiaría en todos
  python3 -m seo.aplicar --todos --si                    lo aplica
  python3 -m seo.aplicar --todos --excepto 111,222 --si  todos menos esos
  python3 -m seo.aplicar --listing 4572865407 --si       uno
  python3 -m seo.aplicar --todos --solo-es --si          solo el español de los que ya se aplicaron en inglés
  python3 -m seo.aplicar --deshacer 4572865407 --si      regresa ese listing a como estaba antes de aplicar
  Opciones: --descripcion (también cambia la descripción en inglés) · --telegram (manda el resumen)
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import etsy  # noqa: E402
from seo import espanol, inventario  # noqa: E402
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


def respaldo(nombre, contenido):
    APLICADOS.mkdir(parents=True, exist_ok=True)
    (APLICADOS / nombre).write_text(json.dumps(contenido, ensure_ascii=False, indent=1), encoding="utf-8")


def guardar(f, p):
    f.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")


def parte_ingles(f, p, shop_id, si, con_descripcion):
    """None si quedó (o quedaría) aplicado; texto con el motivo si se salta."""
    lid = p["_id"]
    ahora = actual(lid)
    antes = p["_antes"]
    if ahora["titulo"] != antes.get("titulo") or not mismos_tags(ahora["tags"], antes.get("tags")):
        return "el listing cambió en Etsy después de la propuesta; vuelve a generarla"
    desc = p.get("descripcion_en") if con_descripcion else None
    print(f"\n{lid} · INGLÉS\n  título: {ahora['titulo']}\n       → {p['titulo_en']}\n  tags:   {', '.join(ahora['tags'])}"
          f"\n       → {', '.join(p['tags_en'])}" + ("\n  descripción: se reemplaza" if desc else ""))
    if si:
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        respaldo(f"{lid}_{sello}.json", {"id": lid, "antes": ahora,
                                         "despues": {"titulo": p["titulo_en"], "tags": p["tags_en"], "descripcion": desc}})
        escribir(shop_id, lid, p["titulo_en"], p["tags_en"], desc)
        p["_aplicado"] = sello
        guardar(f, p)
    return None


def parte_espanol(f, p, shop_id, si):
    """None si quedó (o quedaría) aplicado; texto si no hay nada que hacer o falló."""
    lid = p["_id"]
    if p.get("_aplicado_es"):
        return "español ya aplicado"
    ahora = espanol.actual_es(shop_id, lid)
    if ahora is None:
        return "no tiene traducción al español en Etsy (Etsy traduce solo)"
    espanol.asegurar_es(f, p, ahora)
    if p.get("_problemas_es"):
        return "la versión en español no pasa las reglas: " + "; ".join(p["_problemas_es"])
    print(f"\n{lid} · ESPAÑOL\n  título: {ahora['titulo']}\n       → {p['titulo_es']}\n  tags:   {', '.join(ahora['tags'])}"
          f"\n       → {', '.join(p['tags_es'])}")
    if si:
        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        respaldo(f"{lid}_es_{sello}.json", {"id": lid, "antes": ahora,
                                            "despues": {"titulo": p["titulo_es"], "tags": p["tags_es"]}})
        espanol.escribir_es(shop_id, lid, p["titulo_es"], p["tags_es"], ahora["descripcion"])
        p["_aplicado_es"] = sello
        guardar(f, p)
    return None


def aplicar(seleccion, shop_id, si, con_descripcion, solo_es=False):
    """Devuelve (listos, saltados, avisos): listos = [(id, 'inglés y español' | 'inglés' | 'español')]."""
    listos, saltados, avisos = [], [], []
    for f, p in seleccion:
        lid = p["_id"]
        if p.get("_problemas"):
            saltados.append((lid, "no pasa las reglas: " + "; ".join(p["_problemas"])))
            continue
        hecho = []
        if not p.get("_aplicado"):
            if solo_es:
                saltados.append((lid, "el inglés aún no se aplica"))
                continue
            motivo = parte_ingles(f, p, shop_id, si, con_descripcion)
            if motivo:
                saltados.append((lid, motivo))
                continue
            hecho.append("inglés")
        try:
            motivo = parte_espanol(f, p, shop_id, si)
        except Exception as e:  # noqa: BLE001  el inglés ya quedó; el español se reintenta con --solo-es
            motivo = f"español falló: {e}"
        if motivo is None:
            hecho.append("español")
        elif motivo != "español ya aplicado":
            avisos.append((lid, motivo))
        if hecho:
            listos.append((lid, " y ".join(hecho)))
        elif motivo == "español ya aplicado":
            saltados.append((lid, f"ya aplicada el {p['_aplicado']}"))
        time.sleep(0.3)  # muy por debajo del límite de la API
    return listos, saltados, avisos


def deshacer(lid, shop_id, si):
    ingles = sorted(APLICADOS.glob(f"{lid}_2*.json"))
    esp = sorted(APLICADOS.glob(f"{lid}_es_*.json"))
    if not ingles and not esp:
        sys.exit(f"No hay respaldo de {lid} en {APLICADOS}")
    prop = PROPUESTAS / f"{lid}.json"
    p = json.loads(prop.read_text(encoding="utf-8")) if prop.exists() else None
    if ingles:
        r = json.loads(ingles[-1].read_text(encoding="utf-8"))
        a = r["antes"]
        print(f"{lid} (inglés) vuelve a:\n  {a['titulo']}\n  {', '.join(a['tags'])}")
        if si:
            escribir(shop_id, lid, a["titulo"], a["tags"], a["descripcion"] if r["despues"].get("descripcion") else None)
            if p:
                p.pop("_aplicado", None)
    if esp:
        a = json.loads(esp[-1].read_text(encoding="utf-8"))["antes"]
        print(f"{lid} (español) vuelve a:\n  {a['titulo']}\n  {', '.join(a['tags'])}")
        if si:
            espanol.escribir_es(shop_id, lid, a["titulo"], a["tags"], a["descripcion"])
            if p:
                p.pop("_aplicado_es", None)
    if si:
        if p:  # la propuesta vuelve a quedar pendiente
            guardar(prop, p)
        print("Hecho.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--listing")
    g.add_argument("--todos", action="store_true")
    g.add_argument("--deshacer")
    ap.add_argument("--excepto", default="")
    ap.add_argument("--si", action="store_true", help="sin esto no cambia nada")
    ap.add_argument("--solo-es", action="store_true", help="solo el español de los ya aplicados en inglés")
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
    if a.solo_es:  # solo interesan los que ya tienen el inglés aplicado
        seleccion = [(f, p) for f, p in seleccion if p.get("_aplicado")]
    if not seleccion:
        sys.exit("No encontré propuestas. Primero: python3 -m seo.generar --todos")
    listos, saltados, avisos = aplicar(seleccion, shop_id, a.si, a.descripcion, a.solo_es)
    # nombre legible: el título en inglés que hoy ves en la tienda (el nuevo si ya se aplicó, el de antes si no)
    titulos = {str(p["_id"]): (p.get("titulo_en") if p.get("_aplicado") else p.get("_antes", {}).get("titulo", ""))
               for _, p in seleccion}
    nombre = lambda lid, n: f"{titulos.get(str(lid), '')[:n]} ({lid})"  # noqa: E731
    props = {str(p["_id"]): p for _, p in seleccion}

    def detalle(lid, que):
        """En la vista previa se ve QUÉ cambiaría, no solo que algo cambiaría (en pocos listings, completo)."""
        p, d = props[str(lid)], ""
        if not a.si and len(listos) <= 3:
            if "inglés" in que:
                d += f"\n   EN: {p.get('titulo_en')}\n   tags: {', '.join(p.get('tags_en', []))}"
            if "español" in que:
                d += f"\n   ES: {p.get('titulo_es')}\n   tags: {', '.join(p.get('tags_es', []))}"
        elif not a.si and "español" in que:
            d += f"\n   ES: {p.get('titulo_es')}"
        return d

    texto = (("✅ Aplicados en Etsy: " if a.si else "Vista previa (nada cambió; agrega «si»): ") + f"{len(listos)} listings."
             + "".join(f"\n✓ {nombre(lid, 45)} — {que}{detalle(lid, que)}" for lid, que in listos))
    if avisos:
        texto += "\nOjo:" + "".join(f"\n· {nombre(lid, 30)}: {m[:150]}" for lid, m in avisos)
    if saltados:  # resumen corto: Telegram corta los mensajes de más de 4,000 caracteres
        canib = [nombre(lid, 30) for lid, m in saltados if "comparte" in m]
        otros = [(lid, m) for lid, m in saltados if "comparte" not in m]
        if canib:
            texto += f"\nSaltados por repetir tags con otro listing ({len(canib)}):" + "".join(f"\n· {c}" for c in canib)
        texto += "".join(f"\n· {nombre(lid, 30)}: {m[:150]}" for lid, m in otros)
    print("\n" + texto)
    if saltados:
        print("\nDetalle de saltados:" + "".join(f"\n· {lid}: {m}" for lid, m in saltados))
    if a.si and listos:
        print("Para comparar en 2–3 semanas: /seo toma otra foto y muestra vistas y favoritos ganados por listing.")
    if a.telegram:
        from telegram_puente import avisar
        avisar(texto)


if __name__ == "__main__":
    main()
