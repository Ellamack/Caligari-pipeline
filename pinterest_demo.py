"""
pinterest_demo.py — Demostración para pedir el acceso Standard de la API de Pinterest (el video que piden).

Muestra en una sola toma lo que Pinterest exige ver:
  1. El flujo OAuth: el usuario autoriza la app en pinterest.com (sin pedir contraseña ni cookies).
  2. Una integración en vivo: lee la cuenta y los tableros, crea un tablero si hace falta y publica un pin
     con una imagen del pipeline, enlazado al listing de Etsy.
Con acceso Trial todo corre en el Sandbox de Pinterest: el pin solo lo ves tú en tu perfil. Es lo esperado.

Antes, una sola vez:
  1. developers.pinterest.com → My apps → tu app → Redirect URIs: agrega  http://localhost:8085/
  2. En el VPS, guarda la llave (no se ve al escribir; nunca la pegues en el chat):
       sudo python3 pinterest_demo.py --llave
Grabación (Win+Alt+R en tu PC, con el navegador y la terminal SSH a la vista):
  sudo python3 pinterest_demo.py IMAGEN.jpg "https://www.etsy.com/listing/4592286111"
Desde el 14 oct 2026 (acceso Standard): por defecto usa producción (pines públicos). Opciones:
  --solo-token   autoriza y guarda el token de producción en /etc/caligari/pinterest_token.json, sin publicar
  --sandbox      todo en el Sandbox, como en la demostración
"""
import base64
import getpass
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV = Path("/etc/caligari/pinterest.env")
# Acceso Standard aprobado el 14 oct 2026: por defecto, producción (pines públicos de verdad).
# --sandbox vuelve al Sandbox (pines que solo ve el creador), útil para probar sin publicar.
SANDBOX = "--sandbox" in sys.argv
TOKEN = Path("/etc/caligari/pinterest_sandbox_token.json" if SANDBOX else "/etc/caligari/pinterest_token.json")
REDIRECT = "http://localhost:8085/"
AUTORIZAR = "https://www.pinterest.com/oauth/"
API = "https://api-sandbox.pinterest.com/v5" if SANDBOX else "https://api.pinterest.com/v5"
PERMISOS = "user_accounts:read,boards:read,boards:write,pins:read,pins:write"


def paso(n, texto):
    print(f"\n{'=' * 70}\n  PASO {n}: {texto}\n{'=' * 70}")


def config():
    d = {}
    if ENV.exists():
        for linea in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                d[k.strip()] = v.strip()
    if not d.get("PINTEREST_APP_ID") or not d.get("PINTEREST_SECRET"):
        sys.exit(f"Falta la llave en {ENV}: corre «sudo python3 pinterest_demo.py --llave».")
    return d


def http(metodo, url, token=None, datos=None, json_cuerpo=None, basic=None):
    cab = {}
    cuerpo = None
    if token:
        cab["Authorization"] = f"Bearer {token}"
    if basic:
        cab["Authorization"] = "Basic " + base64.b64encode(basic.encode()).decode()
    if datos is not None:
        cuerpo = urllib.parse.urlencode(datos).encode()
        cab["Content-Type"] = "application/x-www-form-urlencoded"
    elif json_cuerpo is not None:
        cuerpo = json.dumps(json_cuerpo).encode()
        cab["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=cuerpo, headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"✖ Pinterest respondió {e.code} a {metodo} {url.split('?')[0]}:\n{e.read().decode('utf-8', 'replace')[:600]}")


def guardar_llave():
    app = input("App ID (se ve; es el identificador público): ").strip()
    sec = getpass.getpass("App secret (no se ve al escribir): ").strip()
    if not app or not sec:
        sys.exit("No escribiste nada; no cambié nada.")
    ENV.parent.mkdir(parents=True, exist_ok=True)
    ENV.write_text(f"PINTEREST_APP_ID={app}\nPINTEREST_SECRET={sec}\n", encoding="utf-8")
    os.chmod(ENV, 0o600)
    print(f"Guardada en {ENV} (solo root).")


def autorizar(c):
    estado = secrets.token_urlsafe(16)
    url = AUTORIZAR + "?" + urllib.parse.urlencode({
        "client_id": c["PINTEREST_APP_ID"], "redirect_uri": REDIRECT, "response_type": "code",
        "scope": PERMISOS, "state": estado})
    paso(1, "Autorización OAuth en pinterest.com")
    print("Abre este enlace en el navegador, revisa los permisos y presiona «Give access»:\n")
    print(url)
    print("\nEl navegador irá a localhost y dirá que no puede abrir la página: es normal.")
    pegado = input("Copia la dirección COMPLETA de la barra y pégala aquí: ").strip()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(pegado).query)
    if q.get("state", [""])[0] != estado:
        sys.exit("Esa dirección no corresponde a este intento (state distinto). Vuelve a empezar.")
    codigo = q.get("code", [""])[0] or sys.exit("No encuentro «code=» en lo que pegaste.")

    paso(2, "Canje del código por un token (servidor a servidor; el secreto nunca sale del VPS)")
    t = http("POST", API + "/oauth/token", basic=f"{c['PINTEREST_APP_ID']}:{c['PINTEREST_SECRET']}",
             datos={"grant_type": "authorization_code", "code": codigo, "redirect_uri": REDIRECT})
    t["vence"] = time.time() + int(t.get("expires_in", 0))
    TOKEN.write_text(json.dumps(t), encoding="utf-8")
    os.chmod(TOKEN, 0o600)
    print(f"✔ Token recibido (permisos: {t.get('scope')}). Guardado en {TOKEN} (solo root).")
    return t["access_token"]


def tableros(token):
    todos, marca = [], None
    for _ in range(10):  # en Sandbox la lista puede venir vacía con «bookmark»: hay que seguir pidiendo
        params = {"page_size": 250, **({"bookmark": marca} if marca else {})}
        r = http("GET", API + "/boards?" + urllib.parse.urlencode(params), token)
        todos += r.get("items", [])
        marca = r.get("bookmark")
        if todos or not marca:
            break
    return todos


def main():
    if os.geteuid() != 0:
        sys.exit("Córrelo con sudo: la llave vive en /etc/caligari (solo root).")
    if "--llave" in sys.argv:
        guardar_llave()
        return
    if "--solo-token" in sys.argv:  # autoriza y guarda el token, sin publicar nada (para Pinner)
        autorizar(config())
        return
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit(__doc__)
    imagen, enlace = Path(args[0]), args[1]
    if not imagen.exists():
        sys.exit(f"No encuentro la imagen {imagen}")
    c = config()
    token = autorizar(c)

    paso(3, "Lectura de la cuenta que autorizó")
    cuenta = http("GET", API + "/user_account", token)
    print(f"Cuenta: {cuenta.get('username')} · tipo: {cuenta.get('account_type')}")

    paso(4, "Tableros de la cuenta")
    lista = tableros(token)
    for b in lista[:10]:
        print(f"  · {b['name']}  (id {b['id']})")
    tablero = next((b for b in lista if b["name"] == "Antique Natural History Prints"), None)
    if not tablero:
        print("Creo el tablero «Antique Natural History Prints»…")
        tablero = http("POST", API + "/boards", token, json_cuerpo={
            "name": "Antique Natural History Prints",
            "description": "Printable antique natural history plates from The Caligari Cabinet."})
    print(f"Tablero elegido: {tablero['name']} (id {tablero['id']})")

    paso(5, "Publicación de un pin con imagen del pipeline, enlazado al listing de Etsy")
    pin = http("POST", API + "/pins", token, json_cuerpo={
        "board_id": tablero["id"], "link": enlace,
        "title": "Antique Butterfly Plates — " + time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "description": "Antique natural history plates, restored from the original book. Instant download.",
        "alt_text": "Fan of antique hand-coloured butterfly plates on a wooden table",
        "media_source": {"source_type": "image_base64", "content_type": "image/jpeg",
                         "data": base64.b64encode(imagen.read_bytes()).decode()}})
    print(f"✔ Pin creado: id {pin['id']}")
    print(f"  Verlo (solo tú, mientras la app sea Trial): https://www.pinterest.com/pin/{pin['id']}/")

    paso(6, "Comprobación: leer el pin recién creado desde la API")
    leido = http("GET", API + f"/pins/{pin['id']}", token)
    print(f"✔ {leido.get('title')} · tablero {leido.get('board_id')} · enlace {leido.get('link')}")
    print(f"\nFin de la demostración. Abre este enlace para ver el pin recién creado: https://www.pinterest.com/pin/{pin['id']}/")


if __name__ == "__main__":
    main()
