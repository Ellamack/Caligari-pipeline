"""
seo/auditar.py — Auditoría de la tienda: foto del catálogo + validador + comparación con la foto anterior.

Escribe seo/datos/auditoria_<fecha>.md y, si se pide, manda el resumen por Telegram (/seo en el bot).
No cambia nada en Etsy: solo lee.

Uso:  sudo python3 -m seo.auditar [--telegram]
"""
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from seo import inventario  # noqa: E402
from seo.validar import auditar, norm_tag  # noqa: E402


def cambios(actual, anterior):
    """Vistas y favoritos ganados por listing desde la foto anterior."""
    if not anterior:
        return {}
    antes = {x["id"]: x for x in anterior["listings"]}
    return {x["id"]: ((x["vistas"] or 0) - (antes[x["id"]]["vistas"] or 0),
                      (x["favoritos"] or 0) - (antes[x["id"]]["favoritos"] or 0))
            for x in actual if x["id"] in antes}


def informe(catalogo, anterior=None):
    por_listing, parejas = auditar(catalogo)
    delta = cambios(catalogo, anterior)
    hoy = date.today().isoformat()
    lineas = [f"# Auditoría SEO — {hoy}", "",
              f"{len(catalogo)} listings activos. Vistas totales: {sum(x['vistas'] or 0 for x in catalogo)} · "
              f"favoritos: {sum(x['favoritos'] or 0 for x in catalogo)}."]
    if anterior:
        lineas.append(f"Desde la foto del {anterior['fecha']}: +{sum(v for v, _ in delta.values())} vistas, "
                      f"+{sum(f for _, f in delta.values())} favoritos.")
    tags = Counter(norm_tag(t) for x in catalogo for t in x["tags"])
    lineas += ["", "## Tags más repetidos en la tienda (candidatos a canibalización)", ""]
    lineas += [f"- {t}: {n} listings" for t, n in tags.most_common(12) if n > 2]
    con_problemas = [(x, por_listing[x["id"]]) for x in catalogo if por_listing[x["id"]]]
    lineas += ["", f"## Listings con problemas ({len(con_problemas)})", ""]
    for x, probs in con_problemas:
        lineas.append(f"- **{x['titulo'][:80]}** ({x['id']})")
        lineas += [f"  - {texto}" for _, texto in probs]
    lineas += ["", f"## Parejas que comparten 50% o más de tags ({len(parejas)})", ""]
    lineas += [f"- {s:.0%}: «{a['titulo'][:50]}» ↔ «{b['titulo'][:50]}»" for s, a, b in parejas[:40]]
    lineas += ["", "## Por listing: vistas y favoritos", ""]
    for x in sorted(catalogo, key=lambda x: -(x["vistas"] or 0)):
        d = delta.get(x["id"])
        lineas.append(f"- {x['vistas']} vistas · {x['favoritos']} fav"
                      + (f" (+{d[0]} / +{d[1]})" if d else "") + f" — {x['titulo'][:70]}")
    resumen = (f"🔎 Auditoría SEO {hoy}: {len(catalogo)} listings · {len(con_problemas)} con problemas · "
               f"{len(parejas)} parejas que se canibalizan.\nTags más repetidos: "
               + ", ".join(f"{t} ({n})" for t, n in tags.most_common(5)))
    return "\n".join(lineas) + "\n", resumen


def main():
    anterior = inventario.ultima_foto(antes_de=date.today().isoformat())
    ruta, catalogo = inventario.tomar_foto()
    texto, resumen = informe(catalogo, anterior)
    destino = inventario.DATOS / f"auditoria_{date.today().isoformat()}.md"
    destino.write_text(texto, encoding="utf-8")
    print(resumen)
    print(f"Informe completo: {destino}")
    if "--telegram" in sys.argv:
        from telegram_puente import avisar, enviar_archivo
        avisar(resumen)
        try:
            enviar_archivo(destino, "Informe completo")
        except Exception as e:  # noqa: BLE001
            print(f"(no se mandó el archivo: {e})")


if __name__ == "__main__":
    main()
