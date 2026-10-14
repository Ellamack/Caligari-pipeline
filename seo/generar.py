"""
seo/generar.py — Caligari propone título, 13 tags y descripción para un listing, y el validador los revisa.

Flujo (base de conocimiento 4.4): datos del producto + reglas + hermanos del catálogo → modelo → propuesta JSON
→ validador mecánico → si hay problemas, se los devuelve al modelo para corregir (máx. 3 intentos) → propuesta
guardada en seo/datos/propuestas/<id>.json. No toca Etsy: aplicar es otro paso, con tu aprobación.

Uso:
  sudo python3 -m seo.generar --listing 4592286111     un listing que ya existe (de la última foto del catálogo)
  sudo python3 -m seo.generar --libro deuitlandschekap31782cram     un libro del pipeline (listing nuevo)
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from seo import inventario  # noqa: E402
from seo.modelo import pedir_json  # noqa: E402
from seo.validar import REGLAS, linea_de, solapamiento, validar  # noqa: E402

AQUI = Path(__file__).parent
BASE_CONOCIMIENTO = AQUI / "base_conocimiento.md"
SECCIONES = ("2.4", "2.5", "2.6", "2.7", "2.10", "4.1", "4.2")  # lo que el modelo necesita; no la base entera
INTENTOS = 3


def extracto_base():
    """Solo las secciones útiles para escribir un listing (menos tokens = menos costo)."""
    texto = BASE_CONOCIMIENTO.read_text(encoding="utf-8")
    partes = re.split(r"(?m)^(?=### )", texto)
    return "\n".join(p.strip() for p in partes if any(p.startswith(f"### {s} ") for s in SECCIONES))


SISTEMA = """You are Caligari, the SEO specialist of The Caligari Cabinet, an Etsy shop of antique natural-history
illustrations. You write listing titles, tags and descriptions in English for English-speaking buyers.
Follow the shop's knowledge base below. Be accurate: never claim anything the product is not.
Answer ONLY with a JSON object with exactly these keys:
{"busqueda_principal": str, "titulo_en": str, "tags_en": [13 strings], "descripcion_en": str,
 "justificacion": str (in Spanish, 2-4 sentences: why these words, how they differ from sibling listings)}

KNOWLEDGE BASE (excerpt):
"""


def producto_desde_libro(ident):
    import manifiesto as mf
    m = mf.leer(ident)
    if m is None:
        sys.exit(f"No existe el libro {ident}")
    meta, e = m["meta"], m["etapas"].get("empaquetar", {})
    return {"id": ident, "linea": m.get("linea", "A"), "titulo": e.get("titulo", ""), "tags": [],
            "datos": {"obra": meta.get("obra"), "autor": meta.get("autor"), "fecha": meta.get("fecha_mostrar"),
                      "tema": meta.get("tema"), "volumen": meta.get("volumen"), "n": e.get("n"),
                      "formato": "SVG + transparent PNG (restored, vectorized)" if m.get("linea") == "B"
                      else "JPG plates 300 DPI, taken from a scan of the original book (not restored)",
                      "fuente": meta.get("url")}}


def hermanos(producto, catalogo, n=15):
    """Los listings del catálogo que más tags comparten con este (o los de títulos más parecidos)."""
    palabras = set(re.findall(r"[a-z]+", producto.get("titulo", "").lower()))
    def cercania(x):
        s = solapamiento(producto.get("tags", []), x["tags"]) if producto.get("tags") else 0
        return s + 0.05 * len(palabras & set(re.findall(r"[a-z]+", x["titulo"].lower())))
    otros = [x for x in catalogo if x["id"] != producto.get("id")]
    return sorted(otros, key=cercania, reverse=True)[:n]


def pedido(producto, sibs):
    lineas = [f"PRODUCT LINE: {linea_de(producto)} "
              + ("(restored SVG: may say 'restored')" if linea_de(producto) == "B"
                 else "(scanned plates: NEVER say restored)")]
    if producto.get("titulo"):
        lineas.append(f"CURRENT TITLE: {producto['titulo']}")
    if producto.get("tags"):
        lineas.append(f"CURRENT TAGS: {', '.join(producto['tags'])}")
    if producto.get("descripcion"):
        lineas.append(f"CURRENT DESCRIPTION (first 1200 chars): {producto['descripcion'][:1200]}")
    if producto.get("datos"):
        lineas.append("PRODUCT DATA: " + json.dumps(producto["datos"], ensure_ascii=False))
    lineas.append("\nSIBLING LISTINGS IN THE SHOP (share less than half of their tags with each of them):")
    lineas += [f"- {x['titulo']} | tags: {', '.join(x['tags'])}" for x in sibs]
    prohibidos = [k for k in REGLAS["tags_prohibidos"] if not k.startswith("_")]
    lineas.append(f"\nRULES: title max {REGLAS['titulo_max_palabras']} words; exactly {REGLAS['tags_exactos']} tags, "
                  f"each max {REGLAS['tag_max_caracteres']} characters, lowercase, no duplicates; "
                  f"never use these tags: {', '.join(prohibidos)}.")
    return "\n".join(lineas)


def generar(producto, catalogo):
    sistema = SISTEMA + extracto_base()
    sibs = hermanos(producto, catalogo)
    usuario = pedido(producto, sibs)
    gasto, problemas = 0.0, []
    for intento in range(1, INTENTOS + 1):
        texto = usuario if not problemas else (
            usuario + "\n\nYOUR PREVIOUS PROPOSAL:\n" + json.dumps(prop, ensure_ascii=False)
            + "\n\nIT FAILED THESE CHECKS (fix them, keep the rest):\n" + "\n".join(f"- {t}" for _, t in problemas))
        prop, uso = pedir_json(sistema, texto, etiqueta=f"generar {producto['id']} #{intento}")
        gasto += uso["usd"]
        prop["tags_en"] = [t.strip().lower() for t in prop.get("tags_en", [])]
        candidato = {"id": producto["id"], "titulo": prop.get("titulo_en", ""), "tags": prop["tags_en"],
                     "descripcion": prop.get("descripcion_en", ""), "linea": linea_de(producto)}
        problemas = validar(candidato, sibs)
        if not problemas:
            break
    prop.update({"_id": producto["id"], "_linea": linea_de(producto), "_intentos": intento,
                 "_usd": round(gasto, 4), "_problemas": [t for _, t in problemas],
                 "_antes": {"titulo": producto.get("titulo"), "tags": producto.get("tags")}})
    destino = inventario.DATOS / "propuestas" / f"{producto['id']}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(prop, ensure_ascii=False, indent=1), encoding="utf-8")
    return prop, destino


def resumen(prop):
    a = prop["_antes"]
    lineas = [f"Caligari · {prop['_id']} (línea {prop['_linea']}) · búsqueda principal: «{prop.get('busqueda_principal')}»"]
    if a.get("titulo"):
        lineas.append(f"ANTES: {a['titulo']}")
    lineas.append(f"AHORA: {prop.get('titulo_en')}")
    if a.get("tags"):
        quitados = sorted(set(a["tags"]) - set(prop["tags_en"]))
        nuevos = [t for t in prop["tags_en"] if t not in (a["tags"] or [])]
        lineas.append(f"Tags que salen: {', '.join(quitados) or '—'}")
        lineas.append(f"Tags que entran: {', '.join(nuevos) or '—'}")
    else:
        lineas.append(f"Tags: {', '.join(prop['tags_en'])}")
    lineas.append(f"Por qué: {prop.get('justificacion', '')}")
    lineas.append(f"({prop['_intentos']} intento(s), US$ {prop['_usd']})"
                  + (f"\n⚠ Sigue sin pasar: {'; '.join(prop['_problemas'])}" if prop["_problemas"] else ""))
    return "\n".join(lineas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--listing")
    g.add_argument("--libro")
    ap.add_argument("--telegram", action="store_true")
    a = ap.parse_args()
    foto = inventario.ultima_foto() or {"listings": []}
    catalogo = foto["listings"]
    if a.listing:
        producto = next((x for x in catalogo if str(x["id"]) == a.listing), None)
        if producto is None:
            sys.exit(f"El listing {a.listing} no está en la última foto del catálogo (corre /seo primero).")
    else:
        producto = producto_desde_libro(a.libro)
    prop, destino = generar(producto, catalogo)
    texto = resumen(prop)
    print(texto)
    print(f"Propuesta completa: {destino}")
    if a.telegram:
        from telegram_puente import avisar
        avisar(texto)


if __name__ == "__main__":
    main()
