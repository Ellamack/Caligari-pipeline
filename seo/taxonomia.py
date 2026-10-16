"""
seo/taxonomia.py — Qué categorías de Etsy existen y qué atributos desbloquea cada una (API, solo lectura).

Por qué (15 oct 2026): los listings están en «Digital → Digital files», la categoría más genérica; por eso Etsy
solo ofrece atributos de cuadro (marco, paspartú, habitación). Una categoría más específica desbloquea atributos
que funcionan como tags extra (base de conocimiento 2.6). Antes de cambiar nada, se mira el árbol completo aquí.

Uso:
  python3 -m seo.taxonomia clip art             categorías cuyo nombre contiene esas palabras (con su ruta e id)
  python3 -m seo.taxonomia --id 1234            atributos de esa categoría y sus valores posibles
  Opción: --telegram (manda el resultado)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import etsy  # noqa: E402


def nodos():
    """Árbol completo de categorías de vendedor, aplanado: [(id, ruta)]."""
    plano = []

    def recorrer(lista, ruta):
        for n in lista:
            r = ruta + [n["name"]]
            plano.append((n["id"], " → ".join(r)))
            recorrer(n.get("children") or [], r)
    recorrer(etsy.llamar("GET", "/seller-taxonomy/nodes").get("results", []), [])
    return plano


def buscar(palabras):
    p = [w.lower() for w in palabras]
    return [(i, r) for i, r in nodos() if all(w in r.lower() for w in p)]


def atributos(taxonomy_id):
    props = etsy.llamar("GET", f"/seller-taxonomy/nodes/{taxonomy_id}/properties").get("results", [])
    lineas = []
    for x in props:
        valores = [v.get("name") for v in x.get("possible_values") or []]
        muestra = ", ".join(valores[:12]) + (f" … (+{len(valores) - 12})" if len(valores) > 12 else "")
        lineas.append(f"· {x.get('display_name') or x.get('name')}"
                      + (f" (hasta {x['max_values_count']})" if x.get("max_values_count") else "")
                      + (f": {muestra}" if muestra else " (texto/número libre)"))
    return lineas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("palabras", nargs="*")
    ap.add_argument("--id", type=int)
    ap.add_argument("--telegram", action="store_true")
    a = ap.parse_args()
    if a.id:
        texto = f"Atributos de la categoría {a.id}:\n" + "\n".join(atributos(a.id) or ["(ninguno)"])
    else:
        encontrados = buscar(a.palabras or ["clip"])
        texto = (f"Categorías con «{' '.join(a.palabras)}» ({len(encontrados)}):\n"
                 + "\n".join(f"{i} · {r}" for i, r in encontrados[:40])
                 + "\n\nPara ver sus atributos: /categorias id NÚMERO")
    print(texto)
    if a.telegram:
        from telegram_puente import avisar
        avisar(texto)


if __name__ == "__main__":
    main()
