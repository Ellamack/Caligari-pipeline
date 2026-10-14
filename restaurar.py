"""
restaurar.py — Etapa de la línea B: de láminas aprobadas a figuras restauradas (PNG transparente + SVG).

Va entre la revisión de la hoja de contactos y empaquetar.py. Como todas las etapas: se puede volver a
correr cuando sea; retoma donde se quedó y se detiene en cada pregunta (llegan por Telegram).

  1. calibrar    umbral automático (distancia de cada píxel al color del papel + Otsu) sobre la lámina
                 más colorida, y una tira con 5 pruebas. Por defecto NO pregunta: la tira se adjunta a la
                 revisión de figuras, y ahí «umbral N» recorta todo de nuevo. (Con params.preguntar_fondo
                 = true vuelve la pregunta «fondo»: ok | umbral 18.)
  2. recortar    quitar_fondo.py en todas las láminas, una figura por ejemplar (--separar)
                 → hojas de revisión: cada figura numerada sobre gris oscuro (ahí se ven halos y huecos)
                 → pregunta «figuras»: ok | quitar 3, 7 | retocar 12, 40 | quitar 3 retocar 12
  3. retoque     (solo si pediste retocar) las figuras van a Drive → Caligari_Elandres_revision/<ID>_retoque/
                 Las retocas en GIMP y las subes a esa misma carpeta con el mismo nombre, eligiendo
                 «Reemplazar el archivo existente» → pregunta «retoque»: listo
  4. vectorizar  vectorizar.py en todas las figuras que quedan → SVG
  5. especies    (solo si pediste «sueltas 5, 18») nombre común y científico de cada una → pregunta «especies»
                 Esas figuras salen además como listings individuales (ver sueltas.py).
Al terminar: etapa «restaurar» hecha; empaquetar.py arma el producto B con PNG + SVG.

Uso (normalmente lo lanza caligari.py):  python3 restaurar.py ID
Carpetas:  libros/<ID>/figuras/   PNG transparentes (y *_vista.jpg)
           libros/<ID>/svg/       SVG
"""
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

import drive
import hoja_referencia as hr
import manifiesto as mf
import quitar_fondo as qf
import vectorizar as vz
from empaquetar import aplicar_revision

OK = re.compile(r"^(ok|s[ií]|va|vale|listo)[.!]*$", re.I)
POR_HOJA = 40          # figuras por hoja de revisión (que se lean bien en el teléfono)
PARAMS = {"difuminado": 2.0, "mancha": 150, "hueco": 0.5, "min_figura": 0.3, "colores": 34, "motas": 4,
          "preguntar_fondo": False}  # False: umbral automático; la tira de pruebas va junto a la revisión de figuras


def args_fondo(umbral, p):
    return SimpleNamespace(umbral=umbral, difuminado=p["difuminado"], mancha=p["mancha"], hueco=p["hueco"],
                           separar=True, min_figura=p["min_figura"], vista=True)


def laminas_aprobadas(m):
    d = mf.carpeta(m["id"]) / "laminas"
    return [d / x["salida"] for x in m["laminas"] if x.get("incluida") and x.get("salida")
            and (d / x["salida"]).exists()]


def numeros(texto, palabra):
    """'quitar 3, 7 retocar 12' → {3, 7} para 'quitar'."""
    t = re.search(rf"{palabra}\s*([\d\s,y]+)", texto, re.I)
    return {int(n) for n in re.findall(r"\d+", t.group(1))} if t else set()


# ---------------------------------------------------------------- 1. calibrar
def calibrar(m, etapa, p):
    ident = m["id"]
    r = mf.respuesta(ident, "fondo")
    if r is not None and etapa.get("umbral_sugerido") is not None:
        if OK.match(r):
            return float(etapa["umbral_sugerido"])
        n = re.search(r"\d+(?:[.,]\d+)?", r)
        if n:
            return float(n.group().replace(",", "."))
    sugerido, tira, valores = prueba_umbrales(m, p)
    mf.marcar(m, "restaurar", "esperando", paso="calibrar", umbral_sugerido=sugerido)
    mf.preguntar(ident, "fondo",
                 f"Quitar el papel: 5 pruebas sobre la lámina más colorida (umbrales {', '.join(map(str, valores))}).\n"
                 "Elige el panel donde la figura queda completa (antenas, patas) y sin halo de papel.\n"
                 f"«ok» = el del centro ({valores[2]}). Si es otro, escribe p. ej. «umbral {valores[1]}».",
                 formato=f"ok | umbral {valores[1]}", adjuntos=[tira], si_no_respondes=None, sugerido=sugerido)
    return None


def prueba_umbrales(m, p):
    """Umbral automático (Otsu sobre la distancia al papel) de la lámina más colorida + tira de 5 pruebas."""
    ident = m["id"]
    laminas = laminas_aprobadas(m)
    if not laminas:
        raise SystemExit(f"{ident}: no hay láminas aprobadas en libros/{ident}/laminas")
    muestra = hr.ranking_color(laminas)[0]
    img = cv2.imread(str(muestra), cv2.IMREAD_COLOR)
    de, _ = qf.distancia_papel(img)
    sugerido = round(float(qf.umbral_auto(de)), 1)
    salida = mf.carpeta(ident) / "bundle"
    salida.mkdir(parents=True, exist_ok=True)
    qf.probar(muestra, salida, args_fondo(sugerido, p))
    tira = salida / f"{muestra.stem}_prueba_umbrales.jpg"
    drive.copia_revision(tira, f"{ident}_prueba_umbrales.jpg")
    valores = [round(sugerido * f) for f in (0.6, 0.8, 1.0, 1.25, 1.5)]
    return sugerido, tira, valores


# ---------------------------------------------------------------- 2. recortar
def hojas_revision(pngs, destino_base, ancho=200, columnas=8):
    """Figuras numeradas sobre gris oscuro, en hojas de POR_HOJA (la numeración sigue entre hojas)."""
    hojas = []
    for h in range(0, len(pngs), POR_HOJA):
        celdas = []
        for k, ruta in enumerate(pngs[h:h + POR_HOJA], h + 1):
            rgba = cv2.imread(str(ruta), cv2.IMREAD_UNCHANGED)
            if rgba is None:
                continue
            if rgba.shape[2] == 3:
                rgba = np.dstack([rgba, np.full(rgba.shape[:2], 255, np.uint8)])
            a = rgba[..., 3:4].astype(np.float32) / 255
            vista = (rgba[..., :3].astype(np.float32) * a + 40 * (1 - a)).astype(np.uint8)
            esc = min((ancho - 10) / vista.shape[1], (ancho - 10) / vista.shape[0])
            mini = cv2.resize(vista, None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA)
            celda = np.full((ancho + 30, ancho, 3), 40, np.uint8)
            y, x = 30 + (ancho - mini.shape[0]) // 2, (ancho - mini.shape[1]) // 2
            celda[y:y + mini.shape[0], x:x + mini.shape[1]] = mini
            cv2.putText(celda, str(k), (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            celdas.append(celda)
        filas = []
        for i in range(0, len(celdas), columnas):
            fila = celdas[i:i + columnas] + [np.full_like(celdas[0], 40)] * (columnas - len(celdas[i:i + columnas]))
            filas.append(np.hstack(fila))
        destino = destino_base.with_name(f"{destino_base.stem}_{len(hojas) + 1}.jpg")
        cv2.imwrite(str(destino), np.vstack(filas), [cv2.IMWRITE_JPEG_QUALITY, 82])
        hojas.append(destino)
    return hojas


def recortar(m, umbral, p, tira=None, valores=None):
    ident = m["id"]
    figuras = mf.carpeta(ident) / "figuras"
    if figuras.exists():
        shutil.rmtree(figuras)  # con otro umbral no deben quedar figuras de la vez anterior
    figuras.mkdir(parents=True)
    laminas = laminas_aprobadas(m)
    for i, lam in enumerate(laminas, 1):
        print(f"[{i}/{len(laminas)}] {qf.procesar(lam, figuras, args_fondo(umbral, p))}")
    pngs = sorted(figuras.glob("*.png"))
    if not pngs:
        raise SystemExit(f"{ident}: con umbral {umbral} no salió ninguna figura. Prueba otro: responde a «fondo».")
    hojas = hojas_revision(pngs, mf.carpeta(ident) / "bundle" / "figuras_revision.jpg")
    for k, h in enumerate(hojas, 1):
        drive.copia_revision(h, f"{ident}_figuras_{k}.jpg")
    lista = [x.name for x in pngs]
    mf.marcar(m, "restaurar", "esperando", paso="figuras", umbral=umbral, figuras=lista)
    mf.preguntar(ident, "figuras",
                 f"{len(pngs)} figuras sacadas de {len(laminas)} láminas (umbral {umbral:g}), "
                 f"en {len(hojas)} hoja(s) numeradas.\n"
                 "· «ok» si todas sirven.\n"
                 "· «quitar 3, 7» para las que no van (textos del grabado, restos, figuras cortadas).\n"
                 "· «retocar 12, 40» para las que quieres arreglar a mano en GIMP.\n"
                 "· «sueltas 5, 18» para las que además se venderán solas (especies famosas: luna moth, morpho…).\n"
                 "· Se pueden juntar: «quitar 3 retocar 12 sueltas 5».\n"
                 "· Si se comió partes o dejó halos en muchas: «umbral N» y recorto todo de nuevo"
                 + (f" (la última foto son 5 pruebas: {', '.join(map(str, valores))})." if tira else "."),
                 formato="ok | quitar 3, 7 | retocar 12", adjuntos=hojas + ([tira] if tira else []),
                 si_no_respondes=None, n=len(pngs))
    return lista


def aplicar_figuras(m, etapa, r):
    """Respuesta a «figuras» → borra las que no van y devuelve los nombres a retocar."""
    lista = etapa["figuras"]
    quitar, retocar = numeros(r, "quitar"), numeros(r, "retocar")
    figuras = mf.carpeta(m["id"]) / "figuras"
    for k in sorted(quitar):
        if 1 <= k <= len(lista):
            for f in (figuras / lista[k - 1], figuras / lista[k - 1].replace(".png", "_vista.jpg")):
                f.unlink(missing_ok=True)
    quedan = [x for k, x in enumerate(lista, 1) if k not in quitar]
    a_retocar = [lista[k - 1] for k in sorted(retocar) if 1 <= k <= len(lista) and k not in quitar]
    sueltas = {str(k): lista[k - 1] for k in sorted(numeros(r, "sueltas?")) if 1 <= k <= len(lista) and k not in quitar}
    return quedan, a_retocar, sueltas


# ---------------------------------------------------------------- 3. retoque
def carpeta_retoque(ident):
    return f"{drive.REVISION}/{ident}_retoque"


def pedir_retoque(m, quedan, a_retocar):
    ident = m["id"]
    figuras = mf.carpeta(ident) / "figuras"
    subidas = []
    if drive.disponible():
        for nombre in a_retocar:
            try:
                drive.subir(figuras / nombre, carpeta_retoque(ident))
                subidas.append(nombre)
            except RuntimeError as e:
                print(e)
    mf.marcar(m, "restaurar", "esperando", paso="retoque", quedan=quedan, retocar=a_retocar,
              md5_antes={n: drive._md5(figuras / n) for n in a_retocar})
    donde = (f"En Drive → {carpeta_retoque(ident)}/ están las {len(subidas)} figuras."
             if subidas else f"No pude subirlas a Drive; están en el VPS: libros/{ident}/figuras/")
    mf.preguntar(ident, "retoque",
                 f"Retoque a mano: {', '.join(a_retocar)}.\n{donde}\n"
                 "Ábrelas en GIMP, arréglalas y exporta como PNG con el MISMO nombre. Súbelas a la misma "
                 "carpeta y elige «Reemplazar el archivo existente» (si eliges «conservar ambos», no las veo).\n"
                 "Cuando termines, escribe «listo».",
                 formato="listo", si_no_respondes=None)


def recoger_retoque(m, etapa):
    """Baja las figuras retocadas. Devuelve la lista de las que NO cambiaron (para avisar)."""
    ident = m["id"]
    figuras = mf.carpeta(ident) / "figuras"
    sin_cambio = []
    for nombre in etapa.get("retocar", []):
        tmp = figuras / f".{nombre}.nuevo"
        if drive.bajar(f"{carpeta_retoque(ident)}/{nombre}", tmp) and drive._md5(tmp) != etapa["md5_antes"].get(nombre):
            tmp.replace(figuras / nombre)
        else:
            tmp.unlink(missing_ok=True)
            sin_cambio.append(nombre)
    return sin_cambio


# ---------------------------------------------------------------- 4. vectorizar
def vectorizar(m, quedan, p):
    ident = m["id"]
    figuras, svg = mf.carpeta(ident) / "figuras", mf.carpeta(ident) / "svg"
    if svg.exists():
        shutil.rmtree(svg)
    svg.mkdir(parents=True)
    a = SimpleNamespace(colores=p["colores"], motas=p["motas"], suavizar=False, png=False)
    for i, nombre in enumerate(quedan, 1):
        print(f"[{i}/{len(quedan)}] {vz.procesar(figuras / nombre, svg, a)}")
    return [Path(n).with_suffix(".svg").name for n in quedan]


# ---------------------------------------------------------------- 5. piezas sueltas
def pedir_especies(m):
    """Las figuras elegidas para venderse también solas necesitan su nombre: es su búsqueda principal."""
    ident = m["id"]
    sueltas = m["etapas"]["restaurar"]["sueltas"]
    figuras = mf.carpeta(ident) / "figuras"
    hoja = hojas_revision([figuras / n for n in sueltas.values()], mf.carpeta(ident) / "bundle" / "sueltas_revision.jpg")
    # la hoja numera 1..n; se aclara qué número de la revisión corresponde a cada una
    equivalencia = ", ".join(f"{i}→{k}" for i, k in enumerate(sueltas, 1))
    ejemplo = next(iter(sueltas))
    mf.preguntar(ident, "especies",
                 f"Piezas sueltas: {', '.join(sueltas)} (en la foto aparecen como {equivalencia}).\n"
                 "Escribe una línea por figura, con el número de la revisión de figuras, el nombre común en inglés "
                 "y, si lo sabes, el científico:\n"
                 f"{ejemplo}: death's head hawkmoth | Acherontia atropos",
                 formato="3: nombre común | nombre científico", adjuntos=hoja, si_no_respondes=None)


def leer_especies(r, sueltas):
    """'3: death's head hawkmoth | Acherontia atropos' (una por línea) → {"3": {"comun": …, "cientifico": …}}."""
    nombres = {}
    for linea in r.splitlines():
        c = re.match(r"^\s*(\d+)\s*[:.)\-–]?\s*(.+?)\s*$", linea)
        if not c or c.group(1) not in sueltas:
            continue
        partes = [x.strip(" ()") for x in re.split(r"[|(]", c.group(2)) if x.strip(" ()")]
        nombres[c.group(1)] = {"comun": partes[0], "cientifico": partes[1] if len(partes) > 1 else ""}
    return nombres


# ---------------------------------------------------------------- flujo
def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    ident = sys.argv[1]
    m = mf.leer(ident)
    if m is None or not mf.hecho(m, "procesar"):
        sys.exit(f"{ident}: primero procesar_laminas.py --libro {ident}")
    if mf.hecho(m, "restaurar"):
        print(f"{ident}: ya restaurado.")
        return
    if not aplicar_revision(m):  # la hoja de contactos de láminas, igual que en la línea A
        return
    m = mf.leer(ident)
    etapa = m["etapas"].setdefault("restaurar", {"estado": "pendiente"})
    p = dict(PARAMS, **etapa.get("params", {}))
    paso = etapa.get("paso")

    if paso is None and not p["preguntar_fondo"]:
        # Sin pregunta: el umbral automático. Lo revisas al ver las figuras (y ahí puedes pedir otro).
        sugerido, tira, valores = prueba_umbrales(m, p)
        recortar(m, sugerido, p, tira, valores)
        print(f"Umbral automático {sugerido}. Esperando tu revisión de figuras («figuras»).")
        return

    if paso in (None, "calibrar"):
        umbral = calibrar(m, etapa, p)
        if umbral is None:
            print("Esperando tu elección de umbral («fondo»).")
            return
        recortar(m, umbral, p)
        print("Esperando tu revisión de figuras («figuras»).")
        return

    if paso == "figuras":
        r = mf.respuesta(ident, "figuras")
        if r is None:
            print("Esperando tu revisión de figuras («figuras»).")
            return
        otro = re.match(r"^\s*umbral\s*(\d+(?:[.,]\d+)?)\s*$", r, re.I)
        if otro:  # viendo las figuras quiso otro umbral: se recorta de nuevo y se vuelve a preguntar
            recortar(m, float(otro.group(1).replace(",", ".")), p)
            print("Recortado con el umbral nuevo. Esperando tu revisión de figuras («figuras»).")
            return
        quedan, a_retocar, sueltas = aplicar_figuras(m, etapa, r)
        mf.marcar(m, "restaurar", "esperando", sueltas=sueltas)
        if a_retocar:
            pedir_retoque(m, quedan, a_retocar)
            print("Esperando tus retoques («retoque»).")
            return
        mf.marcar(m, "restaurar", "en_curso", paso="vectorizar", quedan=quedan, retocar=[])
        etapa = m["etapas"]["restaurar"]
        paso = "vectorizar"

    if paso == "retoque":
        if mf.respuesta(ident, "retoque") is None:
            print("Esperando tus retoques («retoque»).")
            return
        sin_cambio = recoger_retoque(m, etapa)
        if sin_cambio:
            mf.preguntar(ident, "retoque",
                         f"No veo cambios en: {', '.join(sin_cambio)}.\n"
                         "¿Las subiste con «Reemplazar el archivo existente»? Si no las ibas a retocar, "
                         "escribe «listo» otra vez y sigo con la versión automática.",
                         formato="listo", si_no_respondes=None, intento=2)
            mf.marcar(m, "restaurar", "esperando", paso="retoque_2", retocar=sin_cambio)
            print("Esperando confirmación de retoques.")
            return
        paso = "vectorizar"

    if paso == "retoque_2":
        if mf.respuesta(ident, "retoque") is None:
            return
        recoger_retoque(m, etapa)  # lo que haya llegado; el resto se queda automático
        paso = "vectorizar"

    if paso == "vectorizar":
        m = mf.leer(ident)
        quedan = m["etapas"]["restaurar"]["quedan"]
        svgs = vectorizar(m, quedan, p)
        if m["etapas"]["restaurar"].get("sueltas"):
            pedir_especies(m)
            mf.marcar(m, "restaurar", "esperando", paso="especies", quedan=quedan, svg=svgs, params=p)
            print("Esperando los nombres de las piezas sueltas («especies»).")
            return
        mf.marcar(m, "restaurar", "hecho", paso="hecho", quedan=quedan, svg=svgs, params=p)
        print(f"Listo: {len(quedan)} figuras restauradas (PNG + SVG).")
        return

    if paso == "especies":
        r = mf.respuesta(ident, "especies")
        if r is None:
            print("Esperando los nombres de las piezas sueltas («especies»).")
            return
        nombres = leer_especies(r, etapa["sueltas"])
        faltan = [k for k in etapa["sueltas"] if k not in nombres]
        if faltan:
            mf.preguntar(ident, "especies", f"Me faltan los nombres de: {', '.join(faltan)}. "
                         "Escribe una línea por figura, p. ej.:\n3: death's head hawkmoth | Acherontia atropos",
                         formato="3: nombre común | nombre científico", si_no_respondes=None, faltan=faltan)
            return
        mf.marcar(m, "restaurar", "hecho", paso="hecho", especies=nombres)
        print(f"Listo: {len(etapa['quedan'])} figuras restauradas; {len(nombres)} saldrán también sueltas.")


if __name__ == "__main__":
    main()
