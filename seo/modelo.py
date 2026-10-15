"""
seo/modelo.py — Una sola llamada a un modelo de lenguaje, acotada y medida. Solo biblioteca estándar.

Principio de la casa: tarea acotada → llamada HTTP directa al modelo (no un agente con bucles). Así el gasto por
listing es pequeño y predecible. Cada llamada anota en seo/datos/gasto.jsonl los tokens usados y el costo estimado.

Configuración (solo root; nunca en el repo ni en el chat):
  /etc/caligari/llm.env
    LLM_PROVEEDOR=deepseek            (o anthropic)
    LLM_MODELO=deepseek-flash         (o claude-haiku-4-5-20251001). Ids válidos: GET /v1/models
    LLM_KEY=…
Guardar la llave:  sudo python3 -m seo.modelo --llave
Probar:            sudo python3 -m seo.modelo
"""
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV = Path(os.environ.get("CALIGARI_LLM_ENV", "/etc/caligari/llm.env"))
GASTO = Path(__file__).parent / "datos" / "gasto.jsonl"
# USD por millón de tokens (entrada, salida). Aproximados de oct 2026; solo para estimar el gasto.
PRECIOS = {"deepseek": (0.44, 1.32), "anthropic": (1.00, 5.00)}
DEFAULTS = {"deepseek": "deepseek-flash", "anthropic": "claude-haiku-4-5-20251001"}


def config():
    d = {}
    if ENV.exists():
        for linea in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                d[k.strip()] = v.strip()
    if not d.get("LLM_KEY"):
        raise SystemExit(f"Falta la llave del modelo en {ENV}: sudo python3 -m seo.modelo --llave")
    d.setdefault("LLM_PROVEEDOR", "deepseek")
    d.setdefault("LLM_MODELO", DEFAULTS[d["LLM_PROVEEDOR"]])
    return d


class Plazo(Exception):
    pass


def _post(url, cabeceras, cuerpo, timeout=120):
    """POST con límite TOTAL de `timeout` segundos. urlopen(timeout=) solo limita cada lectura: si el servidor
    manda líneas vacías para «mantener viva» la conexión (DeepSeek lo hace cuando está saturado), nunca vence.
    Por eso se usa además una alarma del sistema que corta la petición completa."""
    import signal

    def vencio(*_):
        raise Plazo()

    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **cabeceras})
    anterior = signal.signal(signal.SIGALRM, vencio)
    signal.alarm(timeout)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except Plazo:
        raise RuntimeError(f"El modelo no respondió en {timeout} s (servicio saturado o sin conexión). "
                           "Vuelve a intentar en unos minutos.") from None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"El modelo respondió {e.code}: {e.read().decode('utf-8', 'replace')[:400]}") from None
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, anterior)


def _llamar(prov, modelo, llave, url_base, sistema, usuario, max_salida, timeout):
    """Una llamada a un proveedor. Devuelve (texto, uso)."""
    if prov == "deepseek":
        # Igual que Minion (OpenClaw, api "openai-completions"): https://api.deepseek.com/v1, sin response_format
        # ni el parámetro thinking. El JSON se pide en el texto y se extrae después. Si vuelve content vacío,
        # se reintenta una vez con thinking desactivado.
        url = (url_base or "https://api.deepseek.com/v1") + "/chat/completions"
        cuerpo = {"model": modelo, "max_tokens": max_salida, "temperature": 0.4,
                  "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
        r = _post(url, {"Authorization": f"Bearer {llave}"}, cuerpo, timeout)
        if not (r["choices"][0]["message"].get("content") or "").strip():
            r = _post(url, {"Authorization": f"Bearer {llave}"}, {**cuerpo, "thinking": {"type": "disabled"}}, timeout)
        return (r["choices"][0]["message"]["content"] or "",
                {"entrada": r["usage"]["prompt_tokens"], "salida": r["usage"]["completion_tokens"]})
    if prov == "anthropic":
        r = _post((url_base or "https://api.anthropic.com") + "/v1/messages",
                  {"x-api-key": llave, "anthropic-version": "2023-06-01"}, {
                      "model": modelo, "max_tokens": max_salida, "temperature": 0.4, "system": sistema,
                      "messages": [{"role": "user", "content": usuario}]}, timeout)
        return ("".join(b.get("text", "") for b in r.get("content", [])),
                {"entrada": r["usage"]["input_tokens"], "salida": r["usage"]["output_tokens"]})
    raise SystemExit(f"Proveedor desconocido: {prov}")


def candidatos(c):
    """Cascada de modelos (principio de la arquitectura: redundancia en cascada).
    1) el principal (LLM_*); 2) el respaldo, si está configurado (LLM2_*: otro proveedor u otra cuenta);
    3) si el principal es DeepSeek, el otro modelo de DeepSeek con la misma llave (las caídas de DeepSeek suelen
       afectar a un modelo y no al otro: status.deepseek.com, 14 oct 2026, cayó V4.1 Flash y no V4 Pro)."""
    lista = [(c["LLM_PROVEEDOR"], c["LLM_MODELO"], c["LLM_KEY"], c.get("LLM_URL"))]
    if c.get("LLM2_KEY"):
        p2 = c.get("LLM2_PROVEEDOR", "anthropic")
        lista.append((p2, c.get("LLM2_MODELO", DEFAULTS[p2]), c["LLM2_KEY"], c.get("LLM2_URL")))
    if c["LLM_PROVEEDOR"] == "deepseek":
        otro = "deepseek-v4-pro" if c["LLM_MODELO"] != "deepseek-v4-pro" else "deepseek-flash"
        lista.append(("deepseek", otro, c["LLM_KEY"], c.get("LLM_URL")))
    vistos, unicos = set(), []
    for x in lista:
        if (x[0], x[1], x[2]) not in vistos:
            vistos.add((x[0], x[1], x[2]))
            unicos.append(x)
    return unicos


def pedir_json(sistema, usuario, max_salida=2500, etiqueta="", timeout=90):
    """Pide una respuesta JSON. Si un modelo no responde a tiempo o falla, prueba el siguiente de la cascada.
    Devuelve (dict, uso) donde uso = {"entrada", "salida", "usd", "proveedor", "modelo"}."""
    c = config()
    errores = []
    for prov, modelo, llave, url_base in candidatos(c):
        try:
            texto, uso = _llamar(prov, modelo, llave, url_base, sistema, usuario, max_salida, timeout)
        except RuntimeError as e:
            errores.append(f"{prov}/{modelo}: {e}")
            print(f"⚠ {prov}/{modelo} falló ({e}); pruebo el siguiente.", file=sys.stderr)
            continue
        pe, ps = PRECIOS.get(prov, (0, 0))
        uso.update({"usd": round(uso["entrada"] * pe / 1e6 + uso["salida"] * ps / 1e6, 5),
                    "proveedor": prov, "modelo": modelo})
        GASTO.parent.mkdir(exist_ok=True)
        with open(GASTO, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M"), "etiqueta": etiqueta, **uso}) + "\n")
        inicio, fin = texto.find("{"), texto.rfind("}")
        if inicio < 0:
            errores.append(f"{prov}/{modelo}: no devolvió JSON: {texto[:120]!r}")
            continue
        return json.loads(texto[inicio:fin + 1]), uso
    raise RuntimeError("Ningún modelo respondió:\n" + "\n".join(errores))


def gasto_total():
    if not GASTO.exists():
        return 0.0, 0
    filas = [json.loads(x) for x in GASTO.read_text(encoding="utf-8").splitlines() if x.strip()]
    return round(sum(f["usd"] for f in filas), 4), len(filas)


def guardar_llave(respaldo=False):
    """Principal (LLM_*) o respaldo (LLM2_*). El respaldo se agrega sin tocar el principal."""
    pref = "LLM2" if respaldo else "LLM"
    defecto = "anthropic" if respaldo else "deepseek"
    prov = (input(f"Proveedor [deepseek/anthropic] (Enter = {defecto}): ").strip() or defecto).lower()
    if prov not in DEFAULTS:
        sys.exit("Proveedor desconocido.")
    modelo = input(f"Modelo (Enter = {DEFAULTS[prov]}): ").strip() or DEFAULTS[prov]
    llave = getpass.getpass("Llave de la API (no se ve al escribir): ").strip()
    if not llave:
        sys.exit("No escribiste nada; no cambié nada.")
    ENV.parent.mkdir(parents=True, exist_ok=True)
    lineas = [x for x in (ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else [])
              if not x.startswith(f"{pref}_")]
    lineas += [f"{pref}_PROVEEDOR={prov}", f"{pref}_MODELO={modelo}", f"{pref}_KEY={llave}"]
    ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    os.chmod(ENV, 0o600)
    print(f"Guardada en {ENV} como {'respaldo' if respaldo else 'principal'} (solo root).")


if __name__ == "__main__":
    if "--llave" in sys.argv:
        guardar_llave(respaldo="--respaldo" in sys.argv)
    else:
        print("Cascada:", " → ".join(f"{p}/{m}" for p, m, _, _ in candidatos(config())))
        d, uso = pedir_json("Responde solo con JSON.", 'Devuelve {"ok": true, "modelo": "<tu nombre>"}',
                            max_salida=50, etiqueta="prueba", timeout=45)
        print(d, uso)
        print("Gasto acumulado: US$ %.4f en %d llamadas" % gasto_total())
