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
# Caracteres que Etsy acepta (documentación de updateListing): tags = letras, números, espacios, - ' ™ © ®;
# título = además puntuación y símbolos matemáticos, y %, :, & y + como máximo una vez cada uno.
TAG_MALO = re.compile(r"[^\w\s\-'™©®]|_")
TITULO_UNA_VEZ = "%:&+"


def norm_tag(t):
    """Etsy guarda los tags en minúsculas; '_' y espacios cuentan igual; Etsy junta singular y plural (2.10)."""
    palabras = re.sub(r"[\s_]+", " ", t.strip().lower()).split(" ")
    return " ".join(re.sub(r"(?<=[a-z]{3})(es|s)$", "", w) if len(w) > 4 else w for w in palabras)


def linea_de(listing):
    """A o B. Si el listing no lo dice, se deduce: los SVG son línea B."""
    if listing.get("linea") in ("A", "B"):
        return listing["linea"]
    texto = (listing.get("titulo", "") + " " + " ".join(listing.get("tags", []))).lower()
    return "B" if "svg" in texto else "A"


def capa_ancha(reglas=REGLAS):
    return {norm_tag(t) for t in reglas.get("capa_ancha", {}).get("lista", [])}


def solapamiento(tags_a, tags_b, excluir=frozenset()):
    """Fracción de tags compartidos respecto al listing con menos tags (0 a 1), sin contar los de `excluir`."""
    a = {norm_tag(t) for t in tags_a} - set(excluir)
    b = {norm_tag(t) for t in tags_b} - set(excluir)
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
    if p.get("busqueda_principal"):
        inicio = " ".join(titulo.lower().split()[:5])
        faltan = [w for w in p["busqueda_principal"].lower().split() if w not in inicio]
        if faltan:
            r.append(("busqueda_no_al_inicio", f"la búsqueda principal «{p['busqueda_principal']}» no está al inicio del título (faltan: {', '.join(faltan)})"))
    sin = [w for w in reglas.get("titulo_sin", {}).get("lista", []) if w in titulo.lower()]
    if sin:
        r.append(("titulo_oferta", f"precio/envío/oferta en el título (Etsy ya lo muestra): {', '.join(sin)}"))
    libres = set(reglas.get("titulo_palabras_que_pueden_repetirse", []))
    cuenta = {}
    for w in re.findall(r"[a-z]+", titulo.lower()):
        if len(w) > 2 and w not in libres:
            cuenta[w] = cuenta.get(w, 0) + 1
    dobles_t = sorted(w for w, n in cuenta.items() if n > 1)
    if dobles_t:
        r.append(("titulo_repite", f"el título repite palabras (Etsy pide no repetir): {', '.join(dobles_t)}"))
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
    raros = [t for t in tags if TAG_MALO.search(t)]
    if raros:
        r.append(("tag_caracteres", f"tags con caracteres que Etsy no acepta: {', '.join(raros)}"))
    dobles = [c for c in TITULO_UNA_VEZ if titulo.count(c) > 1]
    if dobles:
        r.append(("titulo_caracteres_repetidos", f"el título repite {' '.join(dobles)} (Etsy solo acepta uno de cada)"))
    try:
        from seo import demanda
        datos = demanda.insights()
        sin_demanda = [f"{t} ({demanda.veredicto(t, datos)})" for t in tags if demanda.veredicto(t, datos)]
        fuera = [t for t in tags if demanda.temporada_vigente(t, titulo) is False]
    except Exception:  # noqa: BLE001  sin datos de demanda, el validador sigue con lo demás
        sin_demanda, fuera = [], []
    if sin_demanda:
        r.append(("tag_sin_demanda", "tags que los datos de Etsy desaconsejan: " + "; ".join(sin_demanda)))
    if fuera:
        r.append(("tag_fuera_de_temporada", f"tags de temporada vencidos o que no corresponden a este producto: {', '.join(fuera)}"))
    prohibidos = {norm_tag(k): v for k, v in reglas["tags_prohibidos"].items() if not k.startswith("_")}
    malos = [f"{t} ({prohibidos[norm_tag(t)]})" for t in tags if norm_tag(t) in prohibidos]
    if malos:
        r.append(("tag_prohibido", "tags por revisar: " + "; ".join(malos)))
    desc = p.get("descripcion", "").lower()
    usos = [f"{k} ({v})" for k, v in reglas.get("palabras_prohibidas_descripcion", {}).items()
            if not k.startswith("_") and k in desc]
    if usos:
        r.append(("descripcion_usos_falsos", "la descripción promete usos que el archivo no sirve: " + "; ".join(usos)))
    if linea_de(p) == "B":
        malos_b = sorted({w for w in reglas.get("prohibido_tags_y_titulo_linea_B", {}).get("lista", [])
                          for t in tags + [titulo] if w in t.lower()})
        if malos_b:
            r.append(("linea_B_escaneo", f"línea B (restaurada y vectorizada) descrita como escaneo: {', '.join(malos_b)}"))
    if linea_de(p) == "A":
        malos_a = sorted({w for w in reglas.get("prohibido_tags_y_titulo_linea_A", {}).get("lista", [])
                          for t in tags + [titulo] if re.search(rf"\b{w}", t.lower())})
        if malos_a:
            r.append(("linea_A_formato", f"línea A (JPG escaneado) con palabras de otro formato: {', '.join(malos_a)}"))
        debe = reglas.get("descripcion_linea_A_debe_decir", {}).get("alguna_de", [])
        if desc and debe and not any(w in desc for w in debe):
            r.append(("linea_A_entrega", "la descripción de línea A no dice que se recibe un PDF con enlace de descarga"))
        texto = f"{titulo} {' '.join(tags)} {p.get('descripcion', '')}".lower()
        for w in reglas["palabras_prohibidas_linea_A"]:
            if w in texto:
                r.append(("linea_A_restaurado", f"línea A con «{w}…»: las láminas A no se restauran"))
    otros = [o for o in catalogo if not (o.get("id") is not None and o.get("id") == p.get("id"))]
    if otros:
        ajenos = {norm_tag(t) for o in otros for t in o.get("tags", [])}
        propios = [t for t in tags if norm_tag(t) not in ajenos]
        regla = reglas.get("tags_propios", {})
        con_especies = bool((p.get("ficha") or {}).get("especies"))
        minimo = regla.get("con_especies", 3) if con_especies else regla.get("sin_especies", 1)
        if len(propios) < minimo:
            r.append(("canibaliza", f"solo {len(propios)} tag(s) que ningún otro listing usa (mínimo {minimo}"
                                    + ("" if con_especies else ", la ficha no trae especies") + ")"))
    ficha = p.get("ficha")
    if ficha:
        permitidos = {str(ficha.get("figuras"))} | set(re.findall(r"\d+", str(ficha.get("anio", ""))))
        permitidos |= set(re.findall(r"\d+", str(ficha.get("obra", "")) + " " + str(ficha.get("nombre", ""))))
        raros_n = [n for n in re.findall(r"\b\d+\b", titulo) if n not in permitidos]
        if raros_n:
            r.append(("ficha_numero", f"el título dice {', '.join(raros_n)} y la ficha no (figuras: {ficha.get('figuras')}, año: {ficha.get('anio')})"))
    return r


def auditar(catalogo, reglas=REGLAS):
    """{id: [problemas]} de cada listing (sin la regla de hermanos) + parejas que se canibalizan."""
    por_listing = {x["id"]: validar(x, (), reglas) for x in catalogo}
    parejas = []
    for a, b in combinations(catalogo, 2):
        s = solapamiento(a.get("tags", []), b.get("tags", []), capa_ancha(reglas))
        if s >= reglas["max_solapamiento_hermanos"]:
            parejas.append((s, a, b))
    parejas.sort(key=lambda x: -x[0])
    return por_listing, parejas
