"""
seo/espanol.py — La versión en español de cada listing (la traducción que ven los compradores con Etsy en español).

Por qué existe (15 oct 2026): /aplicar cambiaba solo el inglés. La traducción al español es un registro aparte en
Etsy (shops/{shop}/listings/{id}/translations/es) y se quedaba con el título y los tags viejos.

Qué hace:
  · GUIA_ES: instrucciones para que el modelo escriba título y 13 tags EN ESPAÑOL DE BÚSQUEDA (lo que teclea un
    comprador de México o España), no una traducción palabra por palabra. generar.py la usa en el mismo pedido.
  · asegurar_es(): si una propuesta vieja no trae titulo_es / tags_es, los pide al modelo a partir de la versión en
    inglés ya aprobada, los valida con las mismas reglas mecánicas y los guarda en la propuesta.
  · actual_es() / escribir_es(): leer y escribir la traducción en Etsy. La descripción en español se conserva tal
    cual (Etsy la exige al escribir la traducción); solo cambian título y tags.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import etsy  # noqa: E402
from seo.validar import validar  # noqa: E402

IDIOMA = "es"
INTENTOS = 3

GUIA_ES = """SPANISH VERSION (titulo_es, tags_es) for buyers who browse Etsy in Spanish (Mexico, Spain, Latin America).
It is NOT a word-by-word translation: use the words a Spanish-speaking buyer would actually type in Etsy search.
- Crafting jargon stays IN ENGLISH, as Spanish-speaking crafters actually type it: svg, png, clipart, scrapbooking,
  junk journal, ephemera, fussy cuts. Never translate 'ephemera' as 'efímera' (nobody searches it).
- Use Spanish common names: mariposa, polilla, escarabajo, insecto, oruga, abeja, avispa, mantis, colibrí, pájaro/ave,
  hongo/seta, flor, rosa, fruta, pez, concha. Never Latin names in tags (they may stay in the title next to the author).
- Title: max 14 words, the main search first in Spanish (e.g. 'Colibrí SVG PNG, ...'), keep author and year at the end,
  the same facts as the English title and nothing more (same number of figures, same formats).
- Tags: exactly 13, lowercase, max 20 characters each, no duplicates, letters/numbers/spaces/hyphens only.
- Line B (restored and vectorized): say 'restaurado/restaurada', never 'escaneado/escaneada'.
- Line A (scanned plates): never 'restaurado/restaurada'. Never 'cricut', 'archivo de corte', 'corte láser'."""

SISTEMA = ("You write the Spanish version of an Etsy listing of The Caligari Cabinet (antique natural-history "
           "illustrations) from its approved English version. Be accurate: never claim anything the product is not.\n"
           + GUIA_ES + '\nAnswer ONLY with a JSON object: {"titulo_es": str, "tags_es": [13 strings]}')


def problemas_es(titulo, tags, linea):
    """Mismas reglas mecánicas que el inglés, sin hermanos ni datos de demanda (no hay datos en español)."""
    return [t for c, t in validar({"titulo": titulo, "tags": tags, "linea": linea}, ())
            if c not in ("canibaliza", "tag_sin_demanda", "tag_fuera_de_temporada")]


def asegurar_es(archivo, p, actual=None):
    """Garantiza que la propuesta tenga titulo_es y tags_es válidos; si faltan, los genera y guarda. Devuelve p."""
    if p.get("titulo_es") and p.get("tags_es"):
        # lo ya generado se vuelve a revisar con las reglas de HOY; si ya no pasa, se rehace
        p["_problemas_es"] = problemas_es(p["titulo_es"], p["tags_es"], p.get("_linea", "B"))
        if not p["_problemas_es"]:
            return p
    from seo.modelo import pedir_json
    usuario = (f"PRODUCT LINE: {p.get('_linea', 'B')}\nENGLISH TITLE: {p.get('titulo_en')}\n"
               f"ENGLISH TAGS: {', '.join(p.get('tags_en', []))}\nMAIN SEARCH (English): {p.get('busqueda_principal')}")
    if actual:
        usuario += f"\nCURRENT SPANISH TITLE (old, for reference only): {actual.get('titulo')}"
    problemas, prop = [], {}
    for _ in range(INTENTOS):
        texto = usuario if not problemas else (usuario + "\n\nYOUR PREVIOUS ANSWER:\n" + json.dumps(prop, ensure_ascii=False)
                                              + "\nIT FAILED THESE CHECKS (fix them):\n" + "\n".join(f"- {x}" for x in problemas))
        prop, uso = pedir_json(SISTEMA, texto, etiqueta=f"espanol {p['_id']}")
        p["_usd"] = round(p.get("_usd", 0) + uso["usd"], 4)
        prop["tags_es"] = [t.strip().lower() for t in prop.get("tags_es", [])]
        problemas = problemas_es(prop.get("titulo_es", ""), prop["tags_es"], p.get("_linea", "B"))
        if not problemas:
            break
    p.update({"titulo_es": prop.get("titulo_es", ""), "tags_es": prop["tags_es"], "_problemas_es": problemas})
    archivo.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def actual_es(shop_id, listing_id):
    """La traducción al español que hoy tiene Etsy, o None si el listing no tiene."""
    import html
    try:
        x = etsy.llamar("GET", f"/shops/{shop_id}/listings/{listing_id}/translations/{IDIOMA}")
    except etsy.ErrorEtsy as e:
        if " 404 " in str(e):
            return None
        raise
    if not x.get("title"):
        return None
    return {"titulo": html.unescape(x.get("title", "")), "tags": [html.unescape(t) for t in x.get("tags") or []],
            "descripcion": html.unescape(x.get("description", ""))}


def escribir_es(shop_id, listing_id, titulo, tags, descripcion):
    return etsy.llamar("PUT", f"/shops/{shop_id}/listings/{listing_id}/translations/{IDIOMA}",
                       datos={"title": titulo, "description": descripcion, "tags": ",".join(tags)})
