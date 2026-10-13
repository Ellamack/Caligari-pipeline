"""
etsy.py — Conexión con la API v3 de Etsy (app personal de The Caligari Cabinet). Solo biblioteca estándar.

Secretos (nunca en el repo ni en el chat; solo root puede leerlos):
  /etc/caligari/etsy.env         ETSY_KEYSTRING=…  ETSY_SECRET=…  ETSY_REDIRECT=http://localhost:3003/callback
  /etc/caligari/etsy_token.json  lo escribe etsy_autorizar.py (una sola vez) y este módulo lo renueva solo.

El access token dura 1 hora y el refresh token 90 días; cada uso renueva lo que haga falta. Si pasan más de
90 días sin usarlo, hay que volver a correr etsy_autorizar.py.

Uso desde otros scripts:
  import etsy
  yo = etsy.llamar("GET", "/users/me")                    # {"user_id": …, "shop_id": …}
  tienda = etsy.llamar("GET", f"/shops/{yo['shop_id']}")
Prueba rápida (terminal):  sudo python3 etsy.py
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.etsy.com/v3/application"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
AUTORIZAR_URL = "https://www.etsy.com/oauth/connect"
ENV = Path(os.environ.get("ETSY_ENV", "/etc/caligari/etsy.env"))
TOKEN = Path(os.environ.get("ETSY_TOKEN", "/etc/caligari/etsy_token.json"))
PERMISOS = "listings_r listings_w shops_r"  # leer y crear/editar listings (borradores), leer la tienda


class ErrorEtsy(Exception):
    pass


def config():
    datos = {}
    if ENV.exists():
        for linea in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                datos[k.strip()] = v.strip().strip('"').strip("'")
    falta = [k for k in ("ETSY_KEYSTRING", "ETSY_SECRET") if not datos.get(k)]
    if falta:
        raise ErrorEtsy(f"Falta {', '.join(falta)} en {ENV} (ver README: «API de Etsy»).")
    datos.setdefault("ETSY_REDIRECT", "http://localhost:3003/callback")
    return datos


def cabecera_llave(c=None):
    """Desde 2025 Etsy pide la llave como «keystring:shared_secret»."""
    c = c or config()
    return f"{c['ETSY_KEYSTRING']}:{c['ETSY_SECRET']}"


def _http(metodo, url, cabeceras=None, datos=None, json_cuerpo=None, timeout=60):
    cuerpo = None
    cab = dict(cabeceras or {})
    if datos is not None:
        cuerpo = urllib.parse.urlencode(datos).encode()
        cab["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_cuerpo is not None:
        cuerpo = json.dumps(json_cuerpo).encode()
        cab["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=cuerpo, headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            texto = r.read().decode("utf-8")
            return json.loads(texto) if texto else {}
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:500]
        raise ErrorEtsy(f"Etsy respondió {e.code} a {metodo} {url.split('?')[0]}: {detalle}") from None


def guardar_token(t):
    t = dict(t)
    t["vence"] = time.time() + int(t.get("expires_in", 3600)) - 120  # 2 min de margen
    t["refresh_vence"] = time.time() + 90 * 86400 - 3600
    TOKEN.parent.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN.with_suffix(".tmp")
    tmp.write_text(json.dumps(t), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(TOKEN)
    return t


def canjear_codigo(codigo, verificador):
    """Paso final de la autorización: el código que Etsy puso en la URL → tokens."""
    c = config()
    t = _http("POST", TOKEN_URL, {"x-api-key": cabecera_llave(c)}, datos={
        "grant_type": "authorization_code", "client_id": c["ETSY_KEYSTRING"],
        "redirect_uri": c["ETSY_REDIRECT"], "code": codigo, "code_verifier": verificador})
    return guardar_token(t)


def token_vigente():
    if not TOKEN.exists():
        raise ErrorEtsy("Todavía no hay autorización de la tienda: corre «sudo python3 etsy_autorizar.py».")
    t = json.loads(TOKEN.read_text(encoding="utf-8"))
    if time.time() < t.get("vence", 0):
        return t["access_token"]
    if time.time() > t.get("refresh_vence", 0):
        raise ErrorEtsy("La autorización de Etsy venció (90 días sin uso): corre «sudo python3 etsy_autorizar.py».")
    c = config()
    nuevo = _http("POST", TOKEN_URL, {"x-api-key": cabecera_llave(c)}, datos={
        "grant_type": "refresh_token", "client_id": c["ETSY_KEYSTRING"], "refresh_token": t["refresh_token"]})
    return guardar_token(nuevo)["access_token"]


def llamar(metodo, ruta, datos=None, json_cuerpo=None, params=None):
    """Llamada autenticada a la API. `ruta` relativa a /v3/application, p. ej. "/users/me"."""
    url = API + ruta + (("?" + urllib.parse.urlencode(params)) if params else "")
    cab = {"x-api-key": cabecera_llave(), "Authorization": f"Bearer {token_vigente()}"}
    return _http(metodo, url, cab, datos=datos, json_cuerpo=json_cuerpo)


def ping():
    """Sin autorización de tienda: ¿la llave de la app está activa?"""
    return _http("GET", API + "/openapi-ping", {"x-api-key": cabecera_llave()})


def resumen_tienda():
    yo = llamar("GET", "/users/me")
    tienda = llamar("GET", f"/shops/{yo['shop_id']}")
    return {"user_id": yo["user_id"], "shop_id": yo["shop_id"], "tienda": tienda.get("shop_name"),
            "activos": tienda.get("listing_active_count"), "moneda": tienda.get("currency_code")}


if __name__ == "__main__":
    print("Llave de la app:", ping())
    print("Tienda:", resumen_tienda())
