"""
seo/modelo.py — Una sola llamada a un modelo de lenguaje, acotada y medida. Solo biblioteca estándar.

Principio de la casa: tarea acotada → llamada HTTP directa al modelo (no un agente con bucles). Así el gasto por
listing es pequeño y predecible. Cada llamada anota en seo/datos/gasto.jsonl los tokens usados y el costo estimado.

Configuración (solo root; nunca en el repo ni en el chat):
  /etc/caligari/llm.env
    LLM_PROVEEDOR=deepseek            (o anthropic)
    LLM_MODELO=deepseek-v4-flash      (o claude-haiku-4-5-20251001)
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
DEFAULTS = {"deepseek": "deepseek-v4-flash", "anthropic": "claude-haiku-4-5-20251001"}


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


def _post(url, cabeceras, cuerpo, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **cabeceras})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"El modelo respondió {e.code}: {e.read().decode('utf-8', 'replace')[:400]}") from None


def pedir_json(sistema, usuario, max_salida=2500, etiqueta=""):
    """Pide una respuesta JSON. Devuelve (dict, uso) donde uso = {"entrada": n, "salida": n, "usd": x}."""
    c = config()
    prov, modelo = c["LLM_PROVEEDOR"], c["LLM_MODELO"]
    if prov == "deepseek":
        r = _post("https://api.deepseek.com/chat/completions", {"Authorization": f"Bearer {c['LLM_KEY']}"}, {
            "model": modelo, "max_tokens": max_salida, "temperature": 0.4,
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},  # con el razonamiento activo, DeepSeek puede devolver content vacío
            "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]})
        texto = r["choices"][0]["message"]["content"] or ""
        uso = {"entrada": r["usage"]["prompt_tokens"], "salida": r["usage"]["completion_tokens"]}
    elif prov == "anthropic":
        r = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": c["LLM_KEY"], "anthropic-version": "2023-06-01"}, {
                      "model": modelo, "max_tokens": max_salida, "temperature": 0.4, "system": sistema,
                      "messages": [{"role": "user", "content": usuario}]})
        texto = "".join(b.get("text", "") for b in r.get("content", []))
        uso = {"entrada": r["usage"]["input_tokens"], "salida": r["usage"]["output_tokens"]}
    else:
        raise SystemExit(f"Proveedor desconocido: {prov}")
    pe, ps = PRECIOS.get(prov, (0, 0))
    uso["usd"] = round(uso["entrada"] * pe / 1e6 + uso["salida"] * ps / 1e6, 5)
    GASTO.parent.mkdir(exist_ok=True)
    with open(GASTO, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M"), "proveedor": prov, "modelo": modelo,
                             "etiqueta": etiqueta, **uso}) + "\n")
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio < 0:
        raise RuntimeError(f"El modelo no devolvió JSON: {texto[:200]!r}")
    return json.loads(texto[inicio:fin + 1]), uso


def gasto_total():
    if not GASTO.exists():
        return 0.0, 0
    filas = [json.loads(x) for x in GASTO.read_text(encoding="utf-8").splitlines() if x.strip()]
    return round(sum(f["usd"] for f in filas), 4), len(filas)


def guardar_llave():
    prov = (input("Proveedor [deepseek/anthropic] (Enter = deepseek): ").strip() or "deepseek").lower()
    if prov not in DEFAULTS:
        sys.exit("Proveedor desconocido.")
    modelo = input(f"Modelo (Enter = {DEFAULTS[prov]}): ").strip() or DEFAULTS[prov]
    llave = getpass.getpass("Llave de la API (no se ve al escribir): ").strip()
    if not llave:
        sys.exit("No escribiste nada; no cambié nada.")
    ENV.parent.mkdir(parents=True, exist_ok=True)
    ENV.write_text(f"LLM_PROVEEDOR={prov}\nLLM_MODELO={modelo}\nLLM_KEY={llave}\n", encoding="utf-8")
    os.chmod(ENV, 0o600)
    print(f"Guardada en {ENV} (solo root).")


if __name__ == "__main__":
    if "--llave" in sys.argv:
        guardar_llave()
    else:
        d, uso = pedir_json("Responde solo con JSON.", 'Devuelve {"ok": true, "modelo": "<tu nombre>"}',
                            max_salida=50, etiqueta="prueba")
        print(d, uso)
        print("Gasto acumulado: US$ %.4f en %d llamadas" % gasto_total())
