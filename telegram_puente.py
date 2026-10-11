"""
telegram_puente.py — El pipeline por Telegram (CONTRATO 3 por otro canal).

Corre siempre en el VPS (servicio systemd caligari-telegram). Hace tres cosas:
  1. Lleva a tu Telegram cada pregunta nueva de outbox/ (con la hoja de contactos como foto).
  2. Tus respuestas las escribe en inbox/ (el mismo archivo que escribe responder.py)
     y lanza caligari.py para que el libro siga solo hasta la próxima pregunta.
  3. Órdenes:
       /nuevo ID | Tema | Obra | Fecha   empieza un libro (tema, obra y fecha opcionales)
       /estado                            en qué va cada libro
       /pendientes                        vuelve a mandar las preguntas sin contestar
       /seguir ID                         reintenta un libro (p. ej. tras un error)
       /ayuda

Seguridad: solo obedece al chat de TELEGRAM_CHAT_ID; lo demás se ignora y se anota.
Secretos: el token se lee de /etc/caligari/telegram.env (solo root); nunca va en el repo.
Solo biblioteca estándar de Python.
"""
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

import manifiesto as mf

AQUI = Path(__file__).parent
ENV = Path("/etc/caligari/telegram.env")
ESTADO = mf.BASE / "telegram_estado.json"
ID_VALIDO = re.compile(r"^[A-Za-z0-9_.\-]{3,120}$")
MAX_FOTO = 10 * 1024 * 1024   # sendPhoto
MAX_DOC = 49 * 1024 * 1024    # sendDocument (límite de bots: 50 MB)
CADA_VENCIDAS = 600           # cada 10 min revisa preguntas cuyo plazo ya venció

# Qué respuestas acepta cada pregunta. Lo que no encaja se rechaza con una explicación y la pregunta
# sigue abierta (antes, «replay ok» se aceptaba y el libro se quedaba parado).
_OK = r"(ok|s[ií]|va|vale|listo)[.!]*"
VALIDA = {
    "procesar": re.compile(rf"^({_OK}|(umbral\s*)?\d+([.,]\d+)?)$", re.I),
    "revision": re.compile(rf"^({_OK}|quitar[\s,y]*\d[\d\s,y]*)$", re.I),
    "enlace": re.compile(r"^https?://\S+$", re.I),
    "datos": re.compile(rf"^({_OK}|((tema|obra|fecha)\s*[:=]?\s*\S.*\n?)+)$", re.I),
}


def valida(etapa, texto):
    patron = VALIDA.get(etapa)
    return True if patron is None else bool(patron.match(texto.strip()))


def opciones(formato):
    return " o ".join(f"«{o.strip()}»" for o in formato.split("|"))


# ---------------------------------------------------------------- configuración
def config():
    """Token y chat: del entorno (systemd) o, si se corre a mano, del archivo de /etc."""
    datos = {}
    if ENV.exists() and os.access(ENV, os.R_OK):
        for linea in ENV.read_text().splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                datos[k.strip()] = v.strip()
    token = os.environ.get("TELEGRAM_TOKEN") or datos.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID") or datos.get("TELEGRAM_CHAT_ID")
    return token, chat


# ---------------------------------------------------------------- API de Telegram
def _llamar(metodo, datos=None, archivos=None, timeout=70):
    token, _ = config()
    url = f"https://api.telegram.org/bot{token}/{metodo}"
    if archivos:
        limite = f"----caligari{uuid.uuid4().hex}"
        cuerpo = bytearray()
        for k, v in (datos or {}).items():
            cuerpo += f"--{limite}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        for campo, ruta in archivos.items():
            tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
            cuerpo += (f"--{limite}\r\nContent-Disposition: form-data; name=\"{campo}\"; "
                       f"filename=\"{ruta.name}\"\r\nContent-Type: {tipo}\r\n\r\n").encode()
            cuerpo += ruta.read_bytes() + b"\r\n"
        cuerpo += f"--{limite}--\r\n".encode()
        req = urllib.request.Request(url, data=bytes(cuerpo),
                                     headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
    else:
        req = urllib.request.Request(url, data=json.dumps(datos or {}).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        res = json.loads(r.read())
    if not res.get("ok"):
        raise RuntimeError(f"Telegram {metodo}: {res}")
    return res["result"]


def enviar(texto, responder_a=None):
    """Manda un mensaje al chat autorizado. Devuelve el message_id (o None si no hay config)."""
    token, chat = config()
    if not token or not chat:
        print(f"[sin Telegram] {texto}")
        return None
    datos = {"chat_id": chat, "text": texto[:4000], "disable_web_page_preview": True}
    if responder_a:
        datos["reply_to_message_id"] = responder_a
    return _llamar("sendMessage", datos)["message_id"]


def enviar_archivo(ruta, leyenda=""):
    """Foto si es imagen chica; documento si no; y si pesa demasiado, solo avisa dónde está."""
    token, chat = config()
    ruta = Path(ruta)
    if not token or not chat or not ruta.exists():
        return None
    tam = ruta.stat().st_size
    datos = {"chat_id": chat, "caption": leyenda[:1000]}
    if ruta.suffix.lower() in (".jpg", ".jpeg", ".png") and tam <= MAX_FOTO:
        return _llamar("sendPhoto", datos, {"photo": ruta})["message_id"]
    if tam <= MAX_DOC:
        return _llamar("sendDocument", datos, {"document": ruta})["message_id"]
    return enviar(f"{leyenda}\n(archivo de {tam // 1_000_000} MB, demasiado grande para Telegram: {ruta})")


def avisar(texto, imagen=None):
    """Para otros scripts (caligari.py): nunca rompe el pipeline si Telegram falla."""
    try:
        if imagen:
            enviar_archivo(imagen, texto)
        else:
            enviar(texto)
    except Exception as e:  # noqa: BLE001 — un aviso fallido no debe detener nada
        print(f"[aviso no enviado: {e}] {texto}")


# ---------------------------------------------------------------- estado del puente
def leer_estado():
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    return {"offset": 0, "enviadas": {}, "mensajes": {}, "vencidas": {}}


def guardar_estado(e):
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ESTADO)


def pendientes():
    """Preguntas de outbox/ sin respuesta en inbox/: [(archivo, datos)]."""
    outbox = mf.BASE / "outbox"
    res = []
    for q in sorted(outbox.glob("*.json")) if outbox.exists() else []:
        if not (mf.BASE / "inbox" / q.name).exists():
            res.append((q, json.loads(q.read_text(encoding="utf-8"))))
    return res


# ---------------------------------------------------------------- de outbox/ a Telegram
def texto_pregunta(d):
    t = f"❓ {d['libro']} · {d['etapa']}\n\n{d['pregunta']}\n\n✍ Escribe solo: {opciones(d['formato'])}"
    if d.get("si_no_respondes") is not None:
        t += f"\n(si no contestas antes de {d['vence'].replace('T', ' ')}, se toma «{d['si_no_respondes']}»)"
    return t


def mandar_preguntas(estado, todas=False):
    for q, d in pendientes():
        firma = str(q.stat().st_mtime)
        if not todas and estado["enviadas"].get(q.name) == firma:
            continue
        for a in d.get("adjuntos", []):
            if Path(a).suffix.lower() != ".zip":  # el ZIP completo no cabe en Telegram
                mid = enviar_archivo(a, f"{d['libro']} · {Path(a).name}")
                if mid:
                    estado["mensajes"][str(mid)] = q.stem
        mid = enviar(texto_pregunta(d))
        if mid:
            estado["mensajes"][str(mid)] = q.stem
        estado["enviadas"][q.name] = firma
    # que el registro de mensajes no crezca sin fin
    if len(estado["mensajes"]) > 500:
        estado["mensajes"] = dict(list(estado["mensajes"].items())[-300:])


# ---------------------------------------------------------------- de Telegram a inbox/
def lanzar(ident, *extra):
    """caligari.py en segundo plano: el puente sigue atendiendo mientras el libro avanza."""
    log = mf.carpeta(ident) / "registro.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as fh:
        subprocess.Popen([sys.executable, str(AQUI / "caligari.py"), ident, *extra], cwd=AQUI,
                         stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)


def contestar(estado, clave, texto, msg_id):
    ident, etapa = clave.rsplit("_", 1)
    if not valida(etapa, texto):
        q = mf.BASE / "outbox" / f"{clave}.json"
        formato = json.loads(q.read_text(encoding="utf-8"))["formato"] if q.exists() else ""
        enviar(f"No entendí «{texto}» para {ident} · {etapa}. La pregunta sigue abierta.\n"
               f"Escribe solo: {opciones(formato)}", responder_a=msg_id)
        return
    destino = mf.BASE / "inbox" / f"{clave}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"respuesta": texto, "fecha": datetime.now().isoformat(timespec="minutes"),
                                   "canal": "telegram"}, ensure_ascii=False), encoding="utf-8")
    enviar(f"✔ {ident} · {etapa} → «{texto}». Sigo.", responder_a=msg_id)
    lanzar(ident)


def resumen_estado():
    libros = sorted((mf.BASE / "libros").glob("*/manifiesto.json")) if (mf.BASE / "libros").exists() else []
    if not libros:
        return "No hay libros todavía."
    marcas = {"hecho": "✔", "esperando": "⏳", "en_curso": "…", "error": "✖", "pendiente": "·"}
    lineas = []
    for p in libros[-15:]:
        m = json.loads(p.read_text(encoding="utf-8"))
        etapas = " ".join(f"{marcas.get(v['estado'], '?')}{k[:4]}" for k, v in m["etapas"].items())
        lineas.append(f"{m['id']}\n   {etapas}")
    n = len(pendientes())
    return "\n".join(lineas) + (f"\n\nPreguntas sin contestar: {n} (/pendientes)" if n else "")


AYUDA = ("Dos tipos de mensaje:\n\n"
         "1) ÓRDENES (empiezan con /):\n"
         "/nuevo ID — empieza un libro. ej: /nuevo deuitlandschekap41782cram\n"
         "/estado — en qué va cada libro\n"
         "/pendientes — reenvía las preguntas sin contestar\n"
         "/seguir ID — retoma un libro (p. ej. tras un error)\n\n"
         "2) RESPUESTAS (sin /): cuando el bot pregunta algo, escribe solo la respuesta que te indica, "
         "p. ej. ok · quitar 67, 98 · umbral 25 · fecha 1779-1782.\n"
         "Si hay varias preguntas abiertas a la vez: mantén presionado el mensaje de la pregunta → Responder.")


def atender(estado, msg):
    _, chat = config()
    if str(msg.get("chat", {}).get("id")) != str(chat):
        print(f"Ignorado: mensaje de chat no autorizado {msg.get('chat', {}).get('id')}")
        return
    texto = (msg.get("text") or "").strip()
    mid = msg["message_id"]
    if not texto:
        return
    if texto.startswith("/"):
        orden, _, resto = texto.partition(" ")
        orden = orden.split("@")[0].lower()
        if orden in ("/start", "/ayuda", "/help"):
            enviar(AYUDA)
        elif orden == "/estado":
            enviar(resumen_estado())
        elif orden == "/pendientes":
            if pendientes():
                mandar_preguntas(estado, todas=True)
            else:
                enviar("No hay preguntas pendientes.")
        elif orden in ("/nuevo", "/seguir"):
            partes = [p.strip() for p in re.split(r"[|;]", resto)]
            ident = partes[0]
            if not ID_VALIDO.match(ident or ""):
                enviar(f"Ese identificador no parece válido: «{ident}». Ejemplo: /nuevo deuitlandschekap41782cram")
                return
            extra = []
            for bandera, valor in zip(("--tema", "--obra", "--fecha"), partes[1:4]):
                if valor:
                    extra += [bandera, valor]
            enviar(f"▶ {ident}: {'empiezo' if orden == '/nuevo' else 'retomo'}. Te aviso cuando necesite algo.",
                   responder_a=mid)
            lanzar(ident, *extra)
        else:
            enviar(f"No conozco «{orden}».\n\n{AYUDA}")
        return
    # una respuesta: ¿a qué pregunta?
    citado = msg.get("reply_to_message", {}).get("message_id")
    clave = estado["mensajes"].get(str(citado)) if citado else None
    abiertas = [q.stem for q, _ in pendientes()]
    if clave and clave not in abiertas:
        enviar("Esa pregunta ya estaba contestada. /pendientes para ver las abiertas.", responder_a=mid)
        return
    if not clave:
        # sin "Responder": si solo una pregunta acepta ese texto (p. ej. «quitar 67» solo cabe en la revisión), es esa
        candidatas = [c for c in abiertas if valida(c.rsplit("_", 1)[1], texto)]
        if len(abiertas) == 1:
            clave = abiertas[0]
        elif len(candidatas) == 1:
            clave = candidatas[0]
        elif not abiertas:
            enviar("No hay preguntas pendientes. /ayuda para ver las órdenes.", responder_a=mid)
            return
        elif not candidatas:
            enviar(f"No entendí «{texto}». Ninguna pregunta abierta acepta eso; /pendientes te las reenvía "
                   "con lo que puedes escribir en cada una.", responder_a=mid)
            return
        else:
            enviar(f"Hay {len(abiertas)} preguntas abiertas y «{texto}» sirve para varias. Mantén presionado el "
                   "mensaje de la pregunta que contestas → Responder, y escribe ahí. /pendientes las reenvía.",
                   responder_a=mid)
            return
    contestar(estado, clave, texto, mid)


def revisar_vencidas(estado):
    """Preguntas con valor por defecto cuyo plazo ya pasó: el libro sigue solo (una vez por pregunta)."""
    for q, d in pendientes():
        if d.get("si_no_respondes") is None or estado["vencidas"].get(q.name) == d.get("vence"):
            continue
        if datetime.now().isoformat() >= d["vence"]:
            estado["vencidas"][q.name] = d["vence"]
            enviar(f"⏱ {d['libro']} · {d['etapa']}: venció el plazo, sigo con «{d['si_no_respondes']}».")
            lanzar(d["libro"])


# ---------------------------------------------------------------- bucle
def main():
    token, chat = config()
    if not token or not chat:
        sys.exit("Falta TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en /etc/caligari/telegram.env")
    estado = leer_estado()
    print(f"Puente Telegram activo (chat {chat}).")
    ultimo_vencidas = 0.0
    while True:
        try:
            mandar_preguntas(estado)
            if time.time() - ultimo_vencidas > CADA_VENCIDAS:
                revisar_vencidas(estado)
                ultimo_vencidas = time.time()
            guardar_estado(estado)
            for u in _llamar("getUpdates", {"offset": estado["offset"], "timeout": 50,
                                            "allowed_updates": ["message"]}):
                estado["offset"] = u["update_id"] + 1
                if "message" in u:
                    atender(estado, u["message"])
                guardar_estado(estado)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"Red: {e}; reintento en 15 s")
            time.sleep(15)
        except Exception as e:  # noqa: BLE001 — el servicio no debe morir por un mensaje raro
            print(f"Error: {e!r}; reintento en 30 s")
            time.sleep(30)


if __name__ == "__main__":
    main()
