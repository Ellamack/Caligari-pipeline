"""
responder.py — Ver y contestar las preguntas del pipeline (CONTRATO 3) desde la terminal.

Uso:
  python3 responder.py                       # lista las preguntas pendientes
  python3 responder.py LIBRO ETAPA "texto"   # contesta una

Ejemplos:
  python3 responder.py deuitlandschekap11779cram revision ok
  python3 responder.py deuitlandschekap11779cram revision "quitar 7,64"
  python3 responder.py deuitlandschekap11779cram enlace "https://drive.google.com/file/d/…"

Mañana Telegram escribirá exactamente el mismo archivo en inbox/; el pipeline no notará la diferencia.
"""
import json
import sys
from datetime import datetime

import manifiesto as mf


def pendientes():
    outbox = mf.BASE / "outbox"
    if not outbox.exists():
        return []
    res = []
    for q in sorted(outbox.glob("*.json")):
        d = json.loads(q.read_text(encoding="utf-8"))
        if not (mf.BASE / "inbox" / q.name).exists():
            res.append(d)
    return res


def main():
    if len(sys.argv) == 1:
        lista = pendientes()
        if not lista:
            print("No hay preguntas pendientes.")
            return
        for d in lista:
            print(f"\n[{d['libro']} · {d['etapa']}]")
            print(f"  {d['pregunta']}")
            for a in d.get("adjuntos", []):
                print(f"  ver: {a}")
            print(f"  responde así: {d['formato']}")
            if d.get("si_no_respondes") is not None:
                print(f"  si no respondes antes de {d['vence']}: se toma '{d['si_no_respondes']}'")
            else:
                print("  (espera tu respuesta: no avanza solo)")
            print(f"  → python3 responder.py {d['libro']} {d['etapa']} \"…\"")
        return
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    libro, etapa, texto = sys.argv[1], sys.argv[2], sys.argv[3]
    if not (mf.BASE / "outbox" / f"{libro}_{etapa}.json").exists():
        sys.exit(f"No hay ninguna pregunta '{etapa}' para {libro}. Corre responder.py sin argumentos para ver la lista.")
    destino = mf.BASE / "inbox" / f"{libro}_{etapa}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"respuesta": texto, "fecha": datetime.now().isoformat(timespec="minutes")},
                                  ensure_ascii=False), encoding="utf-8")
    print(f"Respuesta guardada: {libro} · {etapa} → {texto}")


if __name__ == "__main__":
    main()
