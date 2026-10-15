"""
seo/demanda.py — Qué se busca de verdad: junta las dos fuentes de demanda para el generador y el validador.

  · seo/insights_etsy.csv   (Etsy → Marketplace Insights, a mano: ~10 términos por semana)
        búsquedas en 30 días, resultados y conversión de Etsy. Es el dato de demanda real.
  · seo/datos/mercado_*.csv  (/mercado, automático) competencia y tráfico de la primera página.

Regla de decisión (decidida 14 oct 2026):
  · Un tag CON datos de conversión «Low» o «Very low», o con 0 búsquedas, no se propone (el validador lo rechaza).
    Excepción: la lista «tags_permitidos_pese_a_conversion» de reglas.json.
  · Los tags preferidos son los de conversión «High/Very high/Typical» con más búsquedas por cada 1,000 resultados.
Nada aquí inventa números: lo que no está medido se trata como desconocido, no como malo.
"""
import csv
import re
from pathlib import Path

AQUI = Path(__file__).parent
INSIGHTS = AQUI / "insights_etsy.csv"
DATOS = AQUI / "datos"
BUENAS = {"very high": 3, "high": 2, "typical": 1}
MALAS = {"low", "very low"}


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def insights():
    """{termino: {busquedas, resultados, conversion, por_mil}} desde el CSV de Etsy Insights."""
    if not INSIGHTS.exists():
        return {}
    r = {}
    for x in csv.DictReader(INSIGHTS.open(encoding="utf-8")):
        t = x["termino"].strip().lower()
        b, res = _num(x.get("busquedas_30d")), _num(x.get("resultados"))
        r[t] = {"busquedas": b, "resultados": res, "conversion": (x.get("conversion") or "").strip(),
                "por_mil": round(b / res * 1000, 1) if b is not None and res else None}
    return r


def mercado():
    """{termino: fila} del CSV de /mercado más reciente (competencia, vistas/día p1, % digital)."""
    archivos = sorted(DATOS.glob("mercado_*.csv"))
    if not archivos:
        return {}
    return {x["termino"].strip().lower(): x for x in csv.DictReader(archivos[-1].open(encoding="utf-8"))}


def veredicto(tag, datos=None):
    """None si no hay datos o el tag está bien; texto si los datos dicen que no conviene."""
    datos = insights() if datos is None else datos
    d = datos.get(tag.strip().lower())
    if not d:
        return None
    if d["busquedas"] == 0:
        return "0 búsquedas en Etsy en 30 días"
    if d["conversion"].lower() in MALAS:
        return f"conversión {d['conversion'].lower()} en Etsy ({int(d['busquedas'] or 0)} búsquedas/mes): atrae curiosos, no compradores"
    return None


def palabras(texto):
    return set(re.findall(r"[a-z]+", texto.lower())) - {"vintage", "antique", "svg", "png", "clipart", "and", "the"}


def _reglas():
    import json
    return json.loads((AQUI / "reglas.json").read_text(encoding="utf-8"))


def temporada_vigente(tag, titulo, reglas=None, hoy=None):
    """True/False si el tag es de temporada (¿vale hoy para este título?); None si no es de temporada."""
    from datetime import date
    t = (reglas or _reglas()).get("temporada", {}).get(tag.strip().lower())
    if not t:
        return None
    hoy = hoy or date.today().isoformat()
    return hoy <= t["hasta"] and any(w in titulo.lower() for w in t["solo_si"])


def recomendados(producto, n=22):
    """Términos medidos con buena conversión, primero los que tocan el tema del producto."""
    datos, reglas = insights(), _reglas()
    evitar = [k for k in reglas.get("no_recomendar_si_contiene", {}) if not k.startswith("_")]
    minimo = reglas.get("min_busquedas_por_mil_resultados", 0)
    tema = palabras(producto.get("titulo", "") + " " + " ".join(producto.get("tags", [])))
    filas = []
    for t, d in datos.items():
        conv = d["conversion"].lower()
        if conv not in BUENAS or not d["busquedas"] or len(t) > 20 or any(e in t for e in evitar):
            continue
        if (d["por_mil"] or 0) < minimo:
            continue
        vigente = temporada_vigente(t, producto.get("titulo", ""), reglas)
        if vigente is False:
            continue
        relevante = bool(palabras(t) & tema) or not palabras(t)  # sin palabras de tema = término general
        filas.append((relevante, BUENAS[conv], d["por_mil"] or 0, t, d))
    filas.sort(key=lambda f: (f[0], f[1], f[2]), reverse=True)
    return [(t, d) for _, _, _, t, d in filas[:n]]


def tabla_prompt(producto):
    """Texto compacto para el modelo: lo medido, para que elija tags con datos y no a ojo."""
    rec = recomendados(producto)
    lineas = ["MEASURED ETSY SEARCH DEMAND (Etsy Marketplace Insights, last 30 days). Prefer these as tags when they",
              "truly describe the product. searches/month | results | conversion:"]
    lineas += [f"- {t}: {int(d['busquedas'])} | {int(d['resultados'] or 0)} | {d['conversion']}" for t, d in rec]
    malos = sorted(t for t, d in insights().items() if veredicto(t) and len(t) <= 20)
    if malos:
        lineas.append("MEASURED AND REJECTED (low conversion or no searches; never use as tags): " + ", ".join(malos))
    lineas.append("Pattern in the data: '<species> svg' and '<subject> svg/clipart' convert high; decor, wall art,"
                  " 'art' and aesthetic terms (witchy, gothic, cottagecore decor) convert very low for file products."
                  " 'fussy cuts' alone also brings quilters: pair it with junk journal / ephemera words.")
    return "\n".join(lineas)


if __name__ == "__main__":
    import json
    ejemplo = {"titulo": "Eyed Hawk Moth SVG PNG, Smerinthus ocellatus, Antique Insect Clipart", "tags": ["moth svg"]}
    print(tabla_prompt(ejemplo))
    print(json.dumps({t: veredicto(t) for t in ["witchy decor", "moth svg", "hawk moth svg", "fussy cuts"]}, indent=1))
