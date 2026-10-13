"""
diseno.py — La apariencia de las imágenes del listing, en archivos que se editan sin tocar código.

  plantillas/diseno.json            el estilo base: fuentes, tamaños, colores, fondos, textos y
                                    la lista de mocos (qué imágenes se hacen y en qué orden).
  plantillas/estilos/<nombre>.json  variantes: solo lo que cambia respecto al base
                                    (p. ej. otra fuente y otra madera). Se mezclan encima.
  plantillas/fuentes/*.ttf|*.otf    las fuentes (Google Fonts, licencia OFL). Si una falta,
                                    se usa DejaVu Serif y el listing sale igual, solo con otra letra.

Cada libro puede tener su estilo (manifiesto → meta.estilo); /imagenes ID estilo lo cambia.

Tres papeles de letra, que usan tanto los mocos (Pillow) como las plantillas SVG (cairosvg):
  titulo   textos en negrita (títulos de cada imagen)
  texto    textos normales
  cursiva  textos en cursiva (obra, citas, notas)
En los SVG el papel se deduce solo: font-weight="bold" → titulo, font-style="italic" → cursiva,
lo demás → texto; o explícito con data-rol="titulo|texto|cursiva".

Uso suelto:  python3 diseno.py            → muestra el estilo base y las fuentes que encuentra
             python3 diseno.py vintage    → lo mismo con el estilo "vintage"
"""
import copy
import json
import os
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

AQUI = Path(__file__).parent
PLANTILLAS = AQUI / "plantillas"
FUENTES = PLANTILLAS / "fuentes"
ESTILOS = PLANTILLAS / "estilos"

# Lo mínimo para que todo funcione aunque diseno.json no exista o esté incompleto.
BASE = {
    "fuentes": {
        "titulo": {"archivo": "", "escala": 1.0},
        "texto": {"archivo": "", "escala": 1.0},
        "cursiva": {"archivo": "", "escala": 1.0},
    },
    "colores": {"tinta": "#2b1d12", "tinta_suave": "#3b2a1c", "banda": "#f4e8cd", "banda_opacidad": 240,
                "marco": "#faf5e8", "recuadro": "#b41e1e"},
    "fondos": {"madera": "madera.jpg", "papel": "papel.jpg"},
    "textos": {
        "detalle": "Every detail, at full resolution",
        "tamanos": "Print at home or at any print shop",
        "tamanos_nota": "300 DPI files · also great for larger frames at gallery resolution",
        "flatlay_n": "{n} printable plates · instant download",
        "flatlay_sin_n": "Printable plates · instant download",
    },
    "mocos": ["detalle", "detalle", "flatlay", "incluido", "tamanos", "pin"],
}

RESPALDO = {"titulo": "DejaVuSerif-Bold.ttf", "texto": "DejaVuSerif.ttf", "cursiva": "DejaVuSerif-Italic.ttf"}
SVG_PESO = {"titulo": ("bold", "normal"), "texto": ("normal", "normal"), "cursiva": ("normal", "italic")}

_activo = None  # el estilo en uso (dict ya mezclado)
_avisadas = set()  # fuentes faltantes ya avisadas (una vez cada una)


def _mezclar(base, encima):
    r = copy.deepcopy(base)
    for k, v in (encima or {}).items():
        if isinstance(v, dict) and isinstance(r.get(k), dict):
            r[k] = _mezclar(r[k], v)
        else:
            r[k] = copy.deepcopy(v)  # listas (mocos) se reemplazan completas
    return r


def _leer(ruta):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        raise SystemExit(f"{ruta.name} tiene un error de formato (línea {e.lineno}): {e.msg}")


def estilos_disponibles():
    return sorted(p.stem for p in ESTILOS.glob("*.json")) if ESTILOS.exists() else []


def cargar(estilo=None, extra=None):
    """Base + plantillas/diseno.json + estilos/<estilo>.json + `extra` (p. ej. mocos de un libro)."""
    d = _mezclar(BASE, _leer(PLANTILLAS / "diseno.json"))
    if estilo and estilo not in ("base", "default"):
        ruta = ESTILOS / f"{estilo}.json"
        if not ruta.exists():
            raise SystemExit(f"No existe el estilo «{estilo}». Hay: {', '.join(estilos_disponibles()) or 'ninguno'}")
        d = _mezclar(d, _leer(ruta))
        d["nombre"] = estilo
    d.setdefault("nombre", "base")
    return _mezclar(d, extra)


def usar(estilo=None, extra=None):
    """Activa un estilo para todo lo que se genere después en este proceso."""
    global _activo
    _activo = cargar(estilo, extra)
    fuente.cache_clear()
    return _activo


def actual():
    return _activo if _activo is not None else usar()


# ---------------------------------------------------------------- colores y fondos
def color(nombre, alfa=None):
    """Color del estilo como tupla RGB(A) para Pillow."""
    h = actual()["colores"].get(nombre, BASE["colores"].get(nombre, "#000000")).lstrip("#")
    rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return rgb + (alfa,) if alfa is not None else rgb


def hex_color(nombre):
    return actual()["colores"].get(nombre, BASE["colores"].get(nombre, "#000000"))


def ruta_fondo(nombre):
    """'madera' o 'papel' → archivo en plantillas/ (o en plantillas/fondos/)."""
    archivo = actual()["fondos"].get(nombre, f"{nombre}.jpg")
    for r in (PLANTILLAS / archivo, PLANTILLAS / "fondos" / archivo):
        if r.exists():
            return r
    return PLANTILLAS / f"{nombre}.jpg"


def texto(clave, **campos):
    t = actual()["textos"].get(clave, BASE["textos"].get(clave, ""))
    return t.format(**campos) if campos else t


def lista_mocos():
    return list(actual().get("mocos") or BASE["mocos"])


# ---------------------------------------------------------------- fuentes
def _archivo_fuente(rol):
    """Ruta del archivo de fuente de un papel (o None si no está; entonces va DejaVu)."""
    nombre = actual()["fuentes"].get(rol, {}).get("archivo") or ""
    if not nombre:
        return None
    for r in (FUENTES / nombre, PLANTILLAS / nombre, Path(nombre)):
        if r.exists():
            return r
    if nombre not in _avisadas:
        _avisadas.add(nombre)
        print(f"⚠ diseño: no encuentro la fuente {nombre} ({rol}); uso DejaVu Serif.")
    return None


def escala(rol):
    return float(actual()["fuentes"].get(rol, {}).get("escala", 1.0))


@lru_cache(maxsize=128)
def fuente(rol, tam):
    """Fuente de Pillow para un papel ('titulo', 'texto', 'cursiva') al tamaño base `tam`
    (ya multiplicado por la escala del estilo)."""
    tam = max(8, round(tam * escala(rol)))
    ruta = _archivo_fuente(rol)
    cfg = actual()["fuentes"].get(rol, {})
    if ruta:
        f = ImageFont.truetype(str(ruta), tam)
        if cfg.get("variacion"):  # fuentes variables: "Bold", "SemiBold Italic"…
            try:
                f.set_variation_by_name(cfg["variacion"])
            except (OSError, ValueError):
                print(f"⚠ diseño: {ruta.name} no tiene la variación «{cfg['variacion']}».")
        return f
    try:
        return ImageFont.truetype(RESPALDO[rol], tam)
    except OSError:
        return ImageFont.load_default(size=tam)


def familia_svg(rol):
    """(font-family, font-weight, font-style) para el SVG. La familia sale del propio archivo de fuente,
    así coincide con lo que fontconfig/cairo encuentran."""
    peso, estilo = SVG_PESO[rol]
    cfg = actual()["fuentes"].get(rol, {})
    peso = cfg.get("peso", peso)
    estilo = cfg.get("estilo", estilo)
    ruta = _archivo_fuente(rol)
    if ruta:
        nombre = ImageFont.truetype(str(ruta), 20).getname()[0]
        return f"'{nombre}', 'DejaVu Serif', serif", peso, estilo
    return "'DejaVu Serif', serif", peso, estilo


_fontconfig_listo = False


def preparar_fontconfig():
    """Hace que cairo (cairosvg) vea plantillas/fuentes/ sin instalar nada en el sistema:
    un fonts.conf temporal que incluye el del sistema + esa carpeta. Debe llamarse antes del primer render."""
    global _fontconfig_listo
    if _fontconfig_listo or not FUENTES.exists():
        return
    sistema = os.environ.get("FONTCONFIG_FILE") or "/etc/fonts/fonts.conf"
    cache = Path(tempfile.gettempdir()) / f"caligari_fontcache_{os.getuid()}"
    conf = Path(tempfile.gettempdir()) / f"caligari_fonts_{os.getuid()}.conf"
    conf.write_text(
        '<?xml version="1.0"?>\n<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n<fontconfig>\n'
        f'  <include ignore_missing="yes">{sistema}</include>\n'
        f'  <dir>{FUENTES.resolve()}</dir>\n'
        f'  <cachedir>{cache}</cachedir>\n</fontconfig>\n', encoding="utf-8")
    os.environ["FONTCONFIG_FILE"] = str(conf)
    _fontconfig_listo = True


def resumen():
    d = actual()
    lineas = [f"Estilo: {d['nombre']}"]
    for rol in ("titulo", "texto", "cursiva"):
        r = _archivo_fuente(rol)
        lineas.append(f"  {rol:8} {r.name if r else 'DejaVu Serif (respaldo)'} · escala {escala(rol)}")
    lineas.append(f"  fondos   madera={ruta_fondo('madera').name} papel={ruta_fondo('papel').name}")
    lineas.append(f"  mocos    {', '.join(lista_mocos())}")
    lineas.append(f"Estilos disponibles: {', '.join(estilos_disponibles()) or '(ninguno)'}")
    disp = sorted(p.name for p in FUENTES.glob("*") if p.suffix.lower() in (".ttf", ".otf")) if FUENTES.exists() else []
    lineas.append(f"Fuentes en plantillas/fuentes: {', '.join(disp) or '(ninguna)'}")
    return "\n".join(lineas)


if __name__ == "__main__":
    usar(sys.argv[1] if len(sys.argv) > 1 else None)
    print(resumen())
