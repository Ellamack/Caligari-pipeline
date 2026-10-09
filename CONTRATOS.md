# Contratos de datos — Caligari pipeline

Un contrato es el formato acordado que una etapa entrega a la siguiente.
Regla: ninguna etapa lee nada que no esté aquí; si un campo cambia, se cambia primero aquí.

Estados válidos de cualquier etapa: `pendiente | en_curso | hecho | esperando | error`

## Estructura en el VPS

```
/home/minion/caligari/
├── candidatos/          contrato 1
├── libros/<id>/
│   ├── manifiesto.json  contrato 2
│   ├── crudo/           JP2 descargados (se borran tras procesar)
│   ├── laminas/         JPG procesados (se borran tras empaquetar)
│   └── bundle/          ZIP + collage + ficha (contrato 4) → Drive
├── outbox/              preguntas para Elandrés (contrato 3)
└── inbox/               respuestas de Elandrés (contrato 3)
```

---

## Contrato 1 — Candidatos
**Escribe:** `buscar_libros.py` · **Lee:** Elandrés (el .md) y `descargar.py` (el .json)
**Archivo:** `candidatos/<tema>_<desde>-<hasta>.json`

```json
{
  "consulta": {"tema": "lepidoptera", "desde": 1750, "hasta": 1880, "fecha": "2026-10-09"},
  "candidatos": [{
    "id": "deuitlandschekap11779cram",
    "fuente": "archive",
    "titulo": "De uitlandsche kapellen…",
    "autor": "Cramer, Pieter, -1780; Stoll, Caspar",
    "fecha": "1779",
    "derechos": "dominio público",
    "paginas": 420,
    "laminas_declaradas": 96,
    "jp2_archivo": "deuitlandschekap11779cram_jp2.zip",
    "jp2_mb": 138.9,
    "jp2_md5": "…",
    "descargas": 4521,
    "url": "https://archive.org/details/deuitlandschekap11779cram",
    "apto": true
  }],
  "descartados": [["listofspecimenso35brit", "catálogo/lista"]]
}
```
- `laminas_declaradas`: número o `null` si la ficha no lo dice.
- `apto`: `true` solo si es dominio público **y** existe `_jp2.zip`.

---

## Contrato 2 — Manifiesto del libro
**Crea:** `descargar.py` · **Leen y actualizan:** todas las etapas siguientes
**Archivo:** `libros/<id>/manifiesto.json`

```json
{
  "id": "deuitlandschekap11779cram",
  "linea": "A",
  "meta": {"titulo": "…", "autor": "…", "fecha": "1779", "derechos": "dominio público",
           "laminas_declaradas": 96, "url": "…"},
  "etapas": {
    "descarga":   {"estado": "hecho", "archivo": "…_jp2.zip", "md5_ok": true},
    "procesar":   {"estado": "hecho", "params": {"solo_color": 23, "min_papel": 50},
                   "origen_umbral": "auto", "paginas": 420, "laminas": 98},
    "revision":   {"estado": "esperando", "excluir": []},
    "empaquetar": {"estado": "pendiente"},
    "ficha":      {"estado": "pendiente"}
  },
  "laminas": [{"pagina": 71, "archivo": "…_0071.jpg", "color": 53.7, "papel": 71, "incluida": true}]
}
```
- Cada etapa: lee el manifiesto → si su estado es `hecho`, no hace nada → si no, trabaja y lo marca.
- `linea`: `"A"` (bundle de láminas completas) o `"B"` (SVG premium).
- `origen_umbral`: `"auto"` o `"manual"`; los params quedan para reutilizar en otros tomos.

---

## Contrato 3 — Pregunta y respuesta (independiente del canal)
**Escribe la pregunta:** cualquier etapa · **Escribe la respuesta:** `responder.py` hoy, Telegram después

`outbox/<id>_<etapa>.json`
```json
{
  "libro": "deuitlandschekap11779cram",
  "etapa": "revision",
  "pregunta": "98 láminas seleccionadas. ¿Quitar alguna?",
  "adjuntos": ["libros/deuitlandschekap11779cram/bundle/hoja_contactos.jpg"],
  "formato": "ok | quitar 7,64",
  "si_no_respondes": "ok",
  "vence": "2026-10-10T08:00"
}
```
`inbox/<id>_<etapa>.json`
```json
{"respuesta": "quitar 7,64", "fecha": "2026-10-09T21:15"}
```
- **Interno** (revisión, umbrales): `si_no_respondes` tiene un valor → al vencer, sigue solo.
- **Público** (ficha, publicar): `si_no_respondes: null` → espera siempre tu aprobación.

---

## Contrato 4 — Ficha del listing
**Escribe:** `empaquetar.py` (+ llamada directa al modelo para los textos) · **Lee:** Elandrés hoy, API de Etsy después
**Archivo:** `libros/<id>/bundle/ficha.json`

```json
{
  "titulo": "…(máx. 140)…",
  "descripcion": "…",
  "tags": ["…13 tags, máx. 20 caracteres c/u…"],
  "precio_usd": 0,
  "archivos_etsy": ["LEEME_descarga.pdf", "muestra.zip"],
  "descarga_completa": {"zip": "deuitlandschekap11779cram_completo.zip", "mb": 198,
                        "enlace": "https://drive.google.com/…", "md5": "…"},
  "imagenes": ["collage_1.jpg", "hoja_contactos.jpg"],
  "cita": "Cramer, P. (1779). De uitlandsche kapellen, vol. 1. Internet Archive."
}
```
- Entrega por enlace (decidido 9 oct 2026): el bundle completo NO va en Etsy (límite 5 × 20 MB).
  En Etsy van `LEEME_descarga.pdf` (enlace + QR + instrucciones) y `muestra.zip` (≤ 20 MB, unas láminas
  a resolución completa), para que la compra nunca se sienta vacía.
- La descripción del listing debe decir claramente: "Recibes un PDF con enlace de descarga (ZIP, ~N MB)".
- El ZIP completo vive en una carpeta de entregas que NO se vacía (distinta de la carpeta de tránsito).
- Nombres de especie: solo los del pie de lámina del libro; si hay duda, `cf.`
