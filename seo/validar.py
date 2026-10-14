"""
seo/validar.py — Validador mecánico de Caligari (código, no modelo). Base de conocimiento, capa 4.4.

Dos usos:
  · validar(propuesta, catalogo)  → lista de problemas de UNA propuesta (lo usará el generador: si hay
    problemas, el modelo corrige y se vuelve a validar; nunca llega a Elandrés algo que no pase).
  · auditar(catalogo)             → problemas de TODOS los listings actuales + parejas que se canibalizan.

Un listing (o propuesta) es un dict con: titulo, tags (lista), descripcion, linea ("A"/"B"), id (opcional).
Las reglas viven en seo/reglas.json.
"""
import json
import re
from itertools import combinations
from pathlib import Path

REGLAS = json.loads((Path(__file__).parent / "reglas.json").read_text(encoding="utf-8"))


def norm_tag(t):
    """Etsy guarda los tags en minúsculas; '_' y espacios cuentan igual para comparar."""
    return re.sub(r"[\s_]+", " ", t.strip().lower())


def linea_de(listing):
    """A o B. Si el listing no lo dice, se deduce: los SVG son línea B."""
    if listing.get("linea") in ("A", "B"):
        return listing["linea"]
    texto = (listing.get("titulo", "") + " " + " ".join(listing.get("tags", []))).lower()
    return "B" if "svg" in texto else "A"


def solapamiento(tags_a, tags_b):
    """Fracción de tags compartidos respecto al listing con menos tags (0 a 1)."""
    a, b = {norm_tag(t) for t in tags_a}, {norm_tag(t) for t in tags_b}
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def validar(p, catalogo=(), reglas=REGLAS):
    """Problemas de una propuesta o listing. Cada problema: (código, texto en español)."""
    r = []
    titulo, tags = p.get("titulo", ""), p.get("tags", [])
    palabras = len(titulo.split())
    if palabras > reglas["titulo_max_palabras"]:
        r.append(("titulo_largo", f"título de {palabras} palabras (máx. {reglas['titulo_max_palabras']})"))
    if len(titulo) > reglas["titulo_max_caracteres"]:
        r.append(("titulo_caracteres", f"título de {len(titulo)} caracteres (máx. {reglas['titulo_max_caracteres']})"))
    subj = [w for w in reglas["palabras_subjetivas_titulo"] if re.search(rf"\b{w}\b", titulo, re.I)]
    if subj:
        r.append(("titulo_subjetivo", f"palabras subjetivas en el título (van a la descripción): {', '.join(subj)}"))
    if len(tags) != reglas["tags_exactos"]:
        r.append(("tags_numero", f"{len(tags)} tags (deben ser {reglas['tags_exactos']})"))
    largos = [t for t in tags if len(t) > reglas["tag_max_caracteres"]]
    if largos:
        r.append(("tag_largo", f"tags de más de {reglas['tag_max_caracteres']} caracteres: {', '.join(largos)}"))
    vistos, repetidos = set(), []
    for t in tags:
        n = norm_tag(t)
        if n in vistos:
            repetidos.append(t)
        vistos.add(n)
    if repetidos:
        r.append(("tag_repetido", f"tags repetidos: {', '.join(repetidos)}"))
    prohibidos = {norm_tag(k): v for k, v in reglas["tags_prohibidos"].items() if not k.startswith("_")}
    malos = [f"{t} ({prohibidos[norm_tag(t)]})" for t in tags if norm_tag(t) in prohibidos]
    if malos:
        r.append(("tag_prohibido", "tags por revisar: " + "; ".join(malos)))
    if linea_de(p) == "A":
        texto = f"{titulo} {' '.join(tags)} {p.get('descripcion', '')}".lower()
        for w in reglas["palabras_prohibidas_linea_A"]:
            if w in texto:
                r.append(("linea_A_restaurado", f"línea A con «{w}…»: las láminas A no se restauran"))
    for otro in catalogo:
        if otro.get("id") is not None and otro.get("id") == p.get("id"):
            continue
        s = solapamiento(tags, otro.get("tags", []))
        if s >= reglas["max_solapamiento_hermanos"]:
            r.append(("canibaliza", f"comparte {s:.0%} de tags con «{otro.get('titulo', '')[:60]}» ({otro.get('id')})"))
    return r


def auditar(catalogo, reglas=REGLAS):
    """{id: [problemas]} de cada listing (sin la regla de hermanos) + parejas que se canibalizan."""
    por_listing = {x["id"]: validar(x, (), reglas) for x in catalogo}
    parejas = []
    for a, b in combinations(catalogo, 2):
        s = solapamiento(a.get("tags", []), b.get("tags", []))
        if s >= reglas["max_solapamiento_hermanos"]:
            parejas.append((s, a, b))
    parejas.sort(key=lambda x: -x[0])
    return por_listing, parejas
