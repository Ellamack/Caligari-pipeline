"""
etsy_autorizar.py — Conecta el pipeline con la tienda en Etsy. Se corre UNA vez (y otra solo si pasan
más de 90 días sin usar la API). Pide permiso para leer la tienda y crear/editar listings (borradores).

Antes, una sola vez:
  1. En etsy.com/developers → tu app → agrega como Callback URL:  http://localhost:3003/callback
  2. En el VPS, guarda la llave (no se ve al escribir; nunca la pegues en el chat):
       sudo python3 etsy_autorizar.py --llave

Luego:
  sudo python3 etsy_autorizar.py
  → te da un enlace: ábrelo en el navegador de tu PC, inicia sesión en Etsy y presiona «Allow access».
  → el navegador irá a http://localhost:3003/callback?code=… y dirá que no puede abrir la página: es normal.
    Copia la dirección COMPLETA de la barra del navegador y pégala en la terminal.
"""
import base64
import getpass
import hashlib
import os
import secrets
import sys
import urllib.parse

import etsy


def guardar_llave():
    ks = input("Keystring de la app (se ve; es el identificador público): ").strip()
    sec = getpass.getpass("Shared Secret (no se ve al escribir): ").strip()
    if not ks or not sec:
        sys.exit("No escribiste nada; no cambié nada.")
    etsy.ENV.parent.mkdir(parents=True, exist_ok=True)
    tmp = etsy.ENV.with_suffix(".tmp")
    tmp.write_text(f"ETSY_KEYSTRING={ks}\nETSY_SECRET={sec}\nETSY_REDIRECT=http://localhost:3003/callback\n",
                   encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(etsy.ENV)
    print(f"Guardada en {etsy.ENV} (solo root). Probando la llave…")
    print("  ", etsy.ping())


def main():
    if os.geteuid() != 0:
        sys.exit("Córrelo con sudo: los secretos viven en /etc/caligari (solo root).")
    if "--llave" in sys.argv:
        guardar_llave()
        return
    c = etsy.config()
    print("Llave de la app:", etsy.ping())

    verificador = secrets.token_urlsafe(64)[:96]  # PKCE: prueba de que quien canjea el código es quien lo pidió
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    estado = secrets.token_urlsafe(16)
    url = etsy.AUTORIZAR_URL + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": c["ETSY_KEYSTRING"], "redirect_uri": c["ETSY_REDIRECT"],
        "scope": etsy.PERMISOS, "state": estado, "code_challenge": reto, "code_challenge_method": "S256"})
    print("\n1) Abre este enlace en el navegador de tu PC y presiona «Allow access»:\n")
    print(url)
    print("\n2) El navegador dirá que no puede abrir localhost: es normal.")
    pegado = input("   Copia la dirección COMPLETA de la barra y pégala aquí: ").strip()

    q = urllib.parse.parse_qs(urllib.parse.urlparse(pegado).query)
    if q.get("error"):
        sys.exit(f"Etsy no dio permiso: {q.get('error_description', q['error'])[0]}")
    if q.get("state", [""])[0] != estado:
        sys.exit("Esa dirección no corresponde a este intento (state distinto). Vuelve a correr el script.")
    codigo = q.get("code", [""])[0]
    if not codigo:
        sys.exit("No encuentro «code=» en lo que pegaste. ¿Copiaste la dirección completa?")

    etsy.canjear_codigo(codigo, verificador)
    r = etsy.resumen_tienda()
    print(f"\n✔ Conectado a la tienda «{r['tienda']}» (shop_id {r['shop_id']}): "
          f"{r['activos']} listings activos, moneda {r['moneda']}.")
    print(f"  Autorización guardada en {etsy.TOKEN} (solo root). Se renueva sola mientras se use.")


if __name__ == "__main__":
    try:
        main()
    except etsy.ErrorEtsy as e:
        sys.exit(f"✖ {e}")
