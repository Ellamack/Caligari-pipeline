"""
buscar_libros.py — Busca libros con láminas en Internet Archive y deja la lista de candidatos.

Etapa 1 del pipeline de The Caligari Cabinet.
Salida: CONTRATO 1 (candidatos), en JSON para las máquinas y en Markdown para leerlo tú.

Qué hace:
  1. Consulta el buscador de Archive.org (colección biodiversity, textos, rango de años).
  2. Descarta lo que casi seguro no tiene láminas (catálogos, listas de especímenes,
     libros con muy pocas páginas).
  3. Para cada candidato lee su ficha real (título, autor, fecha, derechos, descripción)
     y la lista de archivos, para saber si existe el _jp2.zip y cuánto pesa.
  4. Intenta leer cuántas láminas declara la ficha ("plates I-XCVI", "96 col. pl.").
  5. Marca si es apto: dominio público y con _jp2.zip disponible.

Uso:
  python buscar_libros.py lepidoptera
  python buscar_libros.py "birds" --desde 1750 --hasta 1850 --max 20
  python buscar_libros.py fungi --salida /home/minion/caligari/candidatos

No necesita clave. Solo usa la biblioteca estándar de Python.
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BUSCADOR = "https://archive.org/advancedsearch.php"
FICHA = "https://archive.org/metadata/{id}"
DETALLE = "https://archive.org/details/{id}"
AGENTE = "CaligariPipeline/1.0 (personal research; contact via archive.org account)"

# Títulos que casi nunca traen láminas: catálogos, listas, índices
SIN_LAMINAS = re.compile(
    r"\b(list of (the )?specimens|catalogue|catalog |katalog|verzeichniss|index|"
    r"check ?list|bibliograph|proceedings|transactions|journal)\b", re.I)
MIN_PAGINAS = 40


# ---------------------------------------------------------------- red (con reintentos)
def pedir_json(url, intentos=4):
    """GET con reintentos y espera creciente (principio 4: redundancia)."""
    espera = 2
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # red caída, 503 de Archive, JSON cortado…
            if i == intentos - 1:
                raise RuntimeError(f"Falló {url}: {e}") from e
            time.sleep(espera)
            espera *= 2


# ---------------------------------------------------------------- utilidades
def texto(v):
    """Archive a veces da un campo como texto y a veces como lista."""
    if v is None:
        return ""
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)


ROMANOS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def romano_a_int(s):
    s = s.upper()
    total = 0
    for a, b in zip(s, s[1:] + " "):
        v = ROMANOS[a]
        total += -v if ROMANOS.get(b, 0) > v else v
    return total


_PLACAS = r"(?:plates?|pl\.?|tab\.?|tafeln?|planches?|taf\.?)"
_TOMO = re.compile(r"\b(?:v|vol|vols|volume|deel|d|t|tome|tomo|bd|band|th|theil|teil)\.?\s*(\d{1,2}|[IVX]{1,4})\b", re.I)


def _a_numero(s):
    return int(s) if s.isdigit() else romano_a_int(s)


def _conteos(d):
    """Todos los conteos de láminas que aparecen en el texto, con su posición."""
    hallados = []
    # rangos: "plates I-XCVI", "pl. 1-96"
    for m in re.finditer(_PLACAS + r"\s*([IVXLCDM]+|\d{1,4})\s*-\s*([IVXLCDM]+|\d{1,4})\b", d, re.I):
        a, b = m.group(1), m.group(2)
        if a.isdigit() != b.isdigit():
            continue
        n = _a_numero(b) - _a_numero(a) + 1
        hallados.append((m.start(), n))
    # cantidades: "96 col. plates", "48 pl.", "120 hand-coloured plates"
    for m in re.finditer(r"\b(\d{1,4})\s*(?:[a-z\-]+\.?\s+){0,3}?" + _PLACAS + r"(?![a-z])", d, re.I):
        hallados.append((m.start(), int(m.group(1))))
    return [(p, n) for p, n in hallados if 0 < n < 2000]


def laminas_declaradas(descripcion, volumen=None):
    """Cuántas láminas declara la ficha PARA ESTE TOMO. None si no se puede saber con certeza.

    Obras en varios tomos: la descripción suele dar los rangos de todos ("v. 1: pl. I-XCVI;
    v. 2: pl. XCVII-CXCII") o el total de la obra ("4 v. : 400 col. pl."). Se busca el tramo del
    tomo que se descarga (campo `volume` de la ficha); si no se encuentra y hay ambigüedad,
    devuelve None. Mejor no validar que validar contra un número equivocado.
    """
    d = (descripcion or "").replace("–", "-").replace("—", "-")
    conteos = _conteos(d)
    if not conteos:
        return None
    marcas = [(m.start(), _a_numero(m.group(1).upper() if not m.group(1).isdigit() else m.group(1)))
              for m in _TOMO.finditer(d)]
    tomo = None
    if volumen:
        m = re.search(r"(\d{1,2}|\b[IVX]{1,4}\b)", str(volumen))
        if m:
            tomo = _a_numero(m.group(1).upper() if not m.group(1).isdigit() else m.group(1))
    if tomo is not None and marcas:
        # tramo de texto que va de la marca de este tomo a la siguiente marca
        for i, (pos, n_tomo) in enumerate(marcas):
            if n_tomo != tomo:
                continue
            hasta = marcas[i + 1][0] if i + 1 < len(marcas) else len(d)
            propios = {n for p, n in conteos if pos <= p < hasta}
            if len(propios) == 1:
                return propios.pop()
    distintos = {n for _, n in conteos}
    varios_tomos = re.search(r"\b(\d{1,2})\s*v(?:ols?)?\.?(?=[\s:;,)]|$)", d, re.I)
    if varios_tomos and int(varios_tomos.group(1)) > 1:
        return None  # el número es del total de la obra, no de este tomo
    return distintos.pop() if len(distintos) == 1 else None


def evaluar_derechos(meta, anio):
    """Devuelve (apto, nota). Conservador: si algo dice 'restrict', se revisa a mano."""
    estado = texto(meta.get("possible-copyright-status")).upper()
    derechos = texto(meta.get("rights")) + " " + texto(meta.get("licenseurl"))
    if re.search(r"restrict|all rights reserved|no comercial|non-?commercial|by-nc", derechos, re.I):
        return False, f"revisar derechos: {derechos.strip()[:120]}"
    if "NOT_IN_COPYRIGHT" in estado or "publicdomain" in derechos.replace(" ", "").lower():
        return True, "dominio público"
    if anio and anio <= 1900:
        return True, f"dominio público por fecha ({anio})"
    return False, "revisar derechos: sin declaración clara"


# ---------------------------------------------------------------- etapas
def buscar(tema, desde, hasta, filas):
    q = (f'(subject:"{tema}" OR title:"{tema}") AND collection:biodiversity '
         f'AND mediatype:texts AND date:[{desde}-01-01 TO {hasta}-12-31]')
    params = [("q", q), ("rows", str(filas)), ("output", "json"), ("sort[]", "downloads desc")]
    for campo in ("identifier", "title", "creator", "year", "date", "downloads", "imagecount"):
        params.append(("fl[]", campo))
    return pedir_json(BUSCADOR + "?" + urllib.parse.urlencode(params))["response"]["docs"]


def prefiltrar(docs):
    buenos, descartados = [], []
    for d in docs:
        titulo = texto(d.get("title"))
        paginas = int(d.get("imagecount") or 0)
        if SIN_LAMINAS.search(titulo):
            descartados.append((d["identifier"], "catálogo/lista"))
        elif paginas and paginas < MIN_PAGINAS:
            descartados.append((d["identifier"], f"solo {paginas} páginas"))
        else:
            buenos.append(d)
    return buenos, descartados


def ficha_candidato(doc):
    """Lee la ficha completa y arma la entrada del CONTRATO 1."""
    ident = doc["identifier"]
    ficha = pedir_json(FICHA.format(id=ident))
    meta = ficha.get("metadata", {})
    archivos = ficha.get("files", [])
    jp2 = next((f for f in archivos if f.get("name", "").endswith("_jp2.zip")), None)
    anio_txt = texto(meta.get("year") or doc.get("year") or meta.get("date"))
    m = re.search(r"\d{4}", anio_txt)
    anio = int(m.group()) if m else None
    apto_der, nota = evaluar_derechos(meta, anio)
    entrada = {
        "id": ident,
        "fuente": "archive",
        "titulo": texto(meta.get("title")),
        "autor": texto(meta.get("creator")),
        "fecha": anio_txt[:20],
        "derechos": nota,
        "paginas": int(meta.get("imagecount") or doc.get("imagecount") or 0),
        "laminas_declaradas": laminas_declaradas(texto(meta.get("description")), texto(meta.get("volume"))),
        "jp2_archivo": jp2["name"] if jp2 else None,
        "jp2_mb": round(int(jp2.get("size", 0)) / 1e6, 1) if jp2 else None,
        "jp2_md5": jp2.get("md5") if jp2 else None,
        "descargas": int(doc.get("downloads") or 0),
        "url": DETALLE.format(id=ident),
    }
    entrada["apto"] = bool(apto_der and jp2)
    if not jp2:
        entrada["derechos"] += "; sin _jp2.zip"
    return entrada


def a_markdown(contrato):
    c = contrato["consulta"]
    filas = [f"# Candidatos: {c['tema']} ({c['desde']}–{c['hasta']})",
             f"Generado {c['fecha']}. Ordenado por descargas. ✅ = apto (dominio público y con _jp2.zip).", "",
             "| | Libro | Autor | Fecha | Págs. | Láminas | JP2 MB | Nota | ID |",
             "|---|---|---|---|---|---|---|---|---|"]
    for e in contrato["candidatos"]:
        filas.append("| {} | [{}]({}) | {} | {} | {} | {} | {} | {} | `{}` |".format(
            "✅" if e["apto"] else "⚠️", e["titulo"][:70].replace("|", "/"), e["url"],
            e["autor"][:30].replace("|", "/"), e["fecha"], e["paginas"],
            e["laminas_declaradas"] or "?", e["jp2_mb"] or "—", e["derechos"][:40], e["id"]))
    if contrato["descartados"]:
        filas += ["", "Descartados sin abrir: " + ", ".join(f"`{i}` ({m})" for i, m in contrato["descartados"])]
    return "\n".join(filas) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tema", help='p. ej. lepidoptera, birds, fungi, "botany"')
    ap.add_argument("--desde", type=int, default=1750)
    ap.add_argument("--hasta", type=int, default=1880)
    ap.add_argument("--max", type=int, default=15, help="cuántos candidatos revisar a fondo")
    ap.add_argument("--salida", type=Path, default=Path("candidatos"))
    args = ap.parse_args()

    print(f"Buscando '{args.tema}' {args.desde}–{args.hasta} en Archive.org…")
    docs = buscar(args.tema, args.desde, args.hasta, filas=args.max * 3)
    buenos, descartados = prefiltrar(docs)
    print(f"  {len(docs)} resultados, {len(descartados)} descartados por título/páginas")

    candidatos = []
    for i, d in enumerate(buenos[:args.max], 1):
        try:
            e = ficha_candidato(d)
            candidatos.append(e)
            print(f"  [{i}/{min(len(buenos), args.max)}] {'OK ' if e['apto'] else '-- '} {e['id']}")
        except RuntimeError as err:
            print(f"  [{i}] ERROR {d['identifier']}: {err}", file=sys.stderr)
        time.sleep(0.5)  # cortesía con Archive.org

    contrato = {
        "consulta": {"tema": args.tema, "desde": args.desde, "hasta": args.hasta,
                     "fecha": date.today().isoformat()},
        "candidatos": candidatos,
        "descartados": descartados,
    }
    args.salida.mkdir(parents=True, exist_ok=True)
    base = args.salida / f"{re.sub(r'[^a-z0-9]+', '_', args.tema.lower())}_{args.desde}-{args.hasta}"
    base.with_suffix(".json").write_text(json.dumps(contrato, ensure_ascii=False, indent=2), encoding="utf-8")
    base.with_suffix(".md").write_text(a_markdown(contrato), encoding="utf-8")
    aptos = sum(e["apto"] for e in candidatos)
    print(f"Listo: {aptos} aptos de {len(candidatos)} revisados → {base}.md / .json")


if __name__ == "__main__":
    main()
