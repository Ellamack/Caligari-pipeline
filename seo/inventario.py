"""
seo/inventario.py — Foto del catálogo de la tienda desde la API de Etsy.

Guarda seo/datos/inventario_<fecha>.json con, por listing: id, título, tags, descripción, vistas, favoritos,
precio, estado y fecha de última modificación. Cada foto queda guardada: comparar dos fotos dice qué pasó
con las vistas y favoritos de un listing después de cambiarle el título o los tags (base de conocimiento 1.7).

Uso:  sudo python3 -m seo.inventario          (desde la carpeta del pipeline)
"""
import html
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import etsy  # noqa: E402

DATOS = Path(__file__).parent / "datos"


def listings(shop_id, estado="active"):
    todos, offset = [], 0
    while True:
        r = etsy.llamar("GET", f"/shops/{shop_id}/listings", params={"state": estado, "limit": 100, "offset": offset})
        todos += r.get("results", [])
        offset += 100
        if offset >= r.get("count", 0) or not r.get("results"):
            return todos


def resumir(x):
    precio = x.get("price") or {}
    return {
        "id": x["listing_id"],
        "titulo": html.unescape(x.get("title", "")),
        "tags": [html.unescape(t) for t in x.get("tags", [])],
        "descripcion": html.unescape(x.get("description", "")),
        "vistas": x.get("views"),
        "favoritos": x.get("num_favorers"),
        "precio": round(precio["amount"] / precio["divisor"], 2) if precio.get("divisor") else None,
        "moneda": precio.get("currency_code"),
        "estado": x.get("state"),
        "url": x.get("url"),
        "modificado": x.get("updated_timestamp") or x.get("last_modified_timestamp"),
        "taxonomy_id": x.get("taxonomy_id"),
    }


def tomar_foto():
    yo = etsy.llamar("GET", "/users/me")
    catalogo = [resumir(x) for x in listings(yo["shop_id"])]
    DATOS.mkdir(exist_ok=True)
    destino = DATOS / f"inventario_{date.today().isoformat()}.json"
    destino.write_text(json.dumps({"fecha": date.today().isoformat(), "shop_id": yo["shop_id"],
                                   "listings": catalogo}, ensure_ascii=False, indent=1), encoding="utf-8")
    return destino, catalogo


def ultima_foto(antes_de=None):
    fotos = sorted(DATOS.glob("inventario_*.json"))
    if antes_de:
        fotos = [f for f in fotos if f.stem.split("_")[1] < antes_de]
    return json.loads(fotos[-1].read_text(encoding="utf-8")) if fotos else None


if __name__ == "__main__":
    ruta, cat = tomar_foto()
    print(f"{len(cat)} listings activos → {ruta}")
