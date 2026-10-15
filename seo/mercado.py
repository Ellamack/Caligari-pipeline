"""
seo/mercado.py — Estudio de mercado con la API pública de Etsy: oferta y señales de demanda por término.

Lo que la API de Etsy SÍ da (findAllListingsActive): para un término, cuántos listings activos coinciden
(= competencia) y, de los primeros 100 por relevancia, sus vistas, favoritos, precio, fecha de creación y si
son digitales. Lo que NO da: volumen de búsquedas ni el autocompletado. Por eso medimos demanda indirectamente:
  · vistas/día de los listings que Etsy pone arriba para ese término (tráfico que ese término reparte)
  · favoritos/día (interés que se convierte en acción)
  · % digitales (si el término lo buscan para productos físicos o para descargas)
Es una aproximación, pero son datos reales de Etsy, no estimaciones de terceros.

Uso (en el VPS; no necesita la autorización de la tienda, solo la llave de la app):
  sudo python3 -m seo.mercado                       los términos de seo/terminos.txt (uno por línea)
  sudo python3 -m seo.mercado "butterfly wall art" "butterfly clipart"
  sudo python3 -m seo.mercado --telegram            además manda la tabla por Telegram
Resultado: seo/datos/mercado_<fecha>.csv y .md
"""
import csv
import html
import json
import re
from collections import Counter
import statistics as st
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import etsy  # noqa: E402
from seo import inventario  # noqa: E402

TERMINOS = Path(__file__).parent / "terminos.txt"
MUESTRA = 100  # los primeros 100 por relevancia: lo que de verdad ve quien busca


def buscar(termino):
    params = {"keywords": termino, "limit": MUESTRA, "sort_on": "score"}
    url = etsy.API + "/listings/active?" + urllib.parse.urlencode(params)
    return etsy._http("GET", url, {"x-api-key": etsy.cabecera_llave()})


REGLAS = json.loads((Path(__file__).parent / "reglas.json").read_text(encoding="utf-8"))
USD = {k: v for k, v in REGLAS.get("usd_por_moneda", {}).items() if not k.startswith("_")}
# "220 PNG", "5 Fish Clipart", "40 SVG files": cuántas piezas declara el título (para el precio por pieza)
PIEZAS = re.compile(r"\b(\d{1,4})\s*(?:x\s*)?(?:[a-z]+\s+){0,2}?(?:png|svg|jpe?g|clip ?arts?|images|illustrations|"
                    r"graphics|designs|elements|pieces|files|stickers|ephemera|plates|prints)\b")
TAGS_GUARDADOS = 25  # tags más usados por la competencia que se guardan por término


def piezas(titulo):
    nums = [int(n) for n in PIEZAS.findall(titulo.lower()) if 1 < int(n) <= 2000]
    return max(nums) if nums else None


def cuantil(v, q):
    if not v:
        return None
    v = sorted(v)
    return round(v[min(len(v) - 1, int(q * len(v)))], 2)


def medir(termino):
    r = buscar(termino)
    ahora = time.time()
    filas, tags = [], Counter()
    for x in r.get("results", []):
        creado = x.get("original_creation_timestamp") or x.get("creation_timestamp") or ahora
        dias = max(1.0, (ahora - creado) / 86400)
        precio = x.get("price") or {}
        monto = precio["amount"] / precio["divisor"] if precio.get("divisor") else None
        usd = round(monto * USD[precio.get("currency_code")], 2) if monto and precio.get("currency_code") in USD else None
        titulo = html.unescape(x.get("title") or "")
        n = piezas(titulo)
        digital = x.get("listing_type") == "download" or bool(x.get("is_digital"))
        filas.append({"vistas_dia": (x.get("views") or 0) / dias, "fav_dia": (x.get("num_favorers") or 0) / dias,
                      "digital": digital, "usd": usd, "n": n,
                      "usd_pieza": round(usd / n, 3) if usd and n else None})
        tags.update({html.unescape(t).lower().strip() for t in (x.get("tags") or [])})
    med = lambda v: round(st.median(v), 2) if v else None  # noqa: E731
    top = filas[:48]  # primera página
    precios_dig = [f["usd"] for f in filas if f["digital"] and f["usd"]]
    return {
        "termino": termino,
        "competencia": r.get("count", 0),
        "vistas_dia_mediana_p1": med([f["vistas_dia"] for f in top]),
        "vistas_dia_suma_p1": round(sum(f["vistas_dia"] for f in top), 1),
        "fav_dia_mediana_p1": med([f["fav_dia"] for f in top]),
        "pct_digital": round(100 * sum(f["digital"] for f in filas) / len(filas)) if filas else None,
        # Precios convertidos a USD (tipos de cambio aproximados de reglas.json), solo listings digitales.
        "usd_p25": cuantil(precios_dig, 0.25),
        "usd_mediana": med(precios_dig),
        "usd_p75": cuantil(precios_dig, 0.75),
        "usd_por_pieza_mediana": med([f["usd_pieza"] for f in filas if f["digital"] and f["usd_pieza"]]),
        "n_con_piezas": sum(1 for f in filas if f["digital"] and f["usd_pieza"]),
        # tags de la competencia: en cuántos de los 100 primeros listings aparece cada tag
        "tags_competencia": "; ".join(f"{t} ({c})" for t, c in tags.most_common(TAGS_GUARDADOS)),
    }


def leer_terminos():
    """terminos.txt → (cuadricula {(tema, uso): termino}, grupos {nombre: [terminos]}, todos [terminos])."""
    temas, usos, grupos, grupo = [], [], {}, "otros"
    for linea in TERMINOS.read_text(encoding="utf-8").splitlines():
        t = linea.strip()
        if t.startswith("## "):
            grupo = t[3:].split(":")[0].strip()
        elif not t or t.startswith("#"):
            continue
        elif t.startswith("temas:"):
            temas = [x.strip() for x in t[6:].split(",") if x.strip()]
        elif t.startswith("usos:"):
            usos = [x.strip() for x in t[5:].split(",") if x.strip()]
        else:
            grupos.setdefault(grupo, []).append(t)
    cuadricula = {(tm, u): f"vintage {tm} {u}" for tm in temas for u in usos}
    todos = list(dict.fromkeys(list(cuadricula.values()) + [t for g in grupos.values() for t in g]))
    return cuadricula, grupos, todos


def tabla_cuadricula(cuadricula, por_termino, campo, titulo):
    temas = list(dict.fromkeys(t for t, _ in cuadricula))
    usos = list(dict.fromkeys(u for _, u in cuadricula))
    filas = [f"### {titulo}", "", "| tema | " + " | ".join(usos) + " |", "|---|" + "---|" * len(usos)]
    for tm in temas:
        celdas = []
        for u in usos:
            r = por_termino.get(cuadricula[(tm, u)])
            celdas.append(f"{r[campo]:,}" if r and isinstance(r[campo], int) else (str(r[campo]) if r else "—"))
        filas.append(f"| {tm} | " + " | ".join(celdas) + " |")
    return filas


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cuadricula, grupos, todos = ({}, {}, args) if args else leer_terminos()
    terminos = todos
    resultados = []
    for i, t in enumerate(terminos, 1):
        try:
            resultados.append(medir(t))
            print(f"[{i}/{len(terminos)}] {t}: {resultados[-1]['competencia']} listings")
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(terminos)}] {t}: error {e}")
        time.sleep(0.4)  # muy por debajo del límite de 5 consultas por segundo
    # tráfico que reparte la primera página por cada 1,000 competidores: alto = demanda con poca oferta
    for r in resultados:
        r["oportunidad"] = round(r["vistas_dia_suma_p1"] / max(r["competencia"], 1) * 1000, 2)
    resultados.sort(key=lambda r: -r["oportunidad"])
    inventario.DATOS.mkdir(exist_ok=True)
    base = inventario.DATOS / f"mercado_{date.today().isoformat()}"
    with open(base.with_suffix(".csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(resultados[0].keys()))
        w.writeheader()
        w.writerows(resultados)
    lineas = [f"# Mercado Etsy — {date.today().isoformat()}", "",
              "| término | competencia | vistas/día (mediana p1) | vistas/día (suma p1) | fav/día | % digital | USD p25–p50–p75 | USD/pieza | oportunidad |",
              "|---|---|---|---|---|---|---|---|---|"]
    lineas += [f"| {r['termino']} | {r['competencia']:,} | {r['vistas_dia_mediana_p1']} | {r['vistas_dia_suma_p1']} | "
               f"{r['fav_dia_mediana_p1']} | {r['pct_digital']}% | {r['usd_p25']}–{r['usd_mediana']}–{r['usd_p75']} | "
               f"{r['usd_por_pieza_mediana'] if r['usd_por_pieza_mediana'] is not None else '—'} (n={r['n_con_piezas']}) | {r['oportunidad']} |"
               for r in resultados]
    por_termino = {r["termino"]: r for r in resultados}
    if cuadricula:
        lineas += ["", "## Cuadrícula tema × uso (\"vintage <tema> <uso>\")", ""]
        lineas += tabla_cuadricula(cuadricula, por_termino, "vistas_dia_suma_p1", "Tráfico: vistas/día de la primera página")
        lineas += [""] + tabla_cuadricula(cuadricula, por_termino, "competencia", "Competencia: listings activos")
        lineas += [""] + tabla_cuadricula(cuadricula, por_termino, "oportunidad", "Oportunidad (tráfico por 1,000 competidores)")
    for g, ts in grupos.items():
        lineas += ["", f"## {g}", "", "| término | competencia | vistas/día p1 | % digital | oportunidad |", "|---|---|---|---|---|"]
        lineas += [f"| {t} | {por_termino[t]['competencia']:,} | {por_termino[t]['vistas_dia_suma_p1']} | "
                   f"{por_termino[t]['pct_digital']}% | {por_termino[t]['oportunidad']} |" for t in ts if t in por_termino]
    total = Counter()
    for r in resultados:
        for par in filter(None, r["tags_competencia"].split("; ")):
            t, _, c = par.rpartition(" (")
            total[t] += int(c.rstrip(")"))
    lineas += ["", "## Tags más usados por la competencia (suma en todos los términos)", "",
               "Ideas de tags: los que se repiten aquí y no hemos medido se llevan a Etsy Insights (seo/insights_etsy.csv).", ""]
    lineas += [f"- {t}: {c}" for t, c in total.most_common(60)]
    lineas += ["", "Oportunidad = vistas/día que reparte la primera página por cada 1,000 listings competidores.",
               "USD = precio convertido con tipos de cambio aproximados (reglas.json), solo listings digitales.",
               "USD/pieza = precio ÷ número de piezas que declara el título («220 PNG»); n = cuántos lo declaran.",
               "Vistas/día = vistas totales ÷ días desde que se creó el listing (promedio de toda su vida)."]
    base.with_suffix(".md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    print(f"\nInforme: {base.with_suffix('.md')}")
    if "--telegram" in sys.argv:
        from telegram_puente import avisar, enviar_archivo
        avisar("📊 Mercado Etsy (más oportunidad arriba):\n" + "\n".join(
            f"{r['termino']}: comp {r['competencia']:,} · {r['vistas_dia_suma_p1']} vistas/día p1 · "
            f"{r['pct_digital']}% digital · op {r['oportunidad']}" for r in resultados[:15]))
        enviar_archivo(base.with_suffix(".md"), "Informe completo (cuadrícula y grupos)")


if __name__ == "__main__":
    main()
