# Caligari pipeline

Del libro antiguo en Archive.org al bundle publicado en Etsy (The Caligari Cabinet).
Los formatos que se pasan las etapas están en [CONTRATOS.md](CONTRATOS.md).

## Línea A: bundle de láminas completas

| Etapa | Script | Te pregunta algo |
|---|---|---|
| 1. Buscar libros | `buscar_libros.py TEMA` | No (lees la tabla .md y escoges) |
| 2. Descargar | `descargar.py ID` | No |
| 3. Procesar láminas | `procesar_laminas.py --libro ID` | Solo si el conteo no cuadra con la ficha |
| 4. Revisión | (la deja la etapa 3) | Sí: hoja de contactos. Si no respondes en 12 h → "ok" |
| 5. Empaquetar | `empaquetar.py ID --tema "…" --obra "…" [--fecha "1775-1779"]` | Sí: enlace de Drive del ZIP (no avanza solo) |

Preguntas pendientes: `python3 responder.py` · Contestar: `python3 responder.py ID ETAPA "respuesta"`

## Por Telegram (forma normal de trabajar)

El bot del pipeline (`telegram_puente.py`, servicio `caligari-telegram`) lleva cada pregunta a tu Telegram
y tus respuestas al pipeline; `caligari.py` hace avanzar el libro solo hasta la siguiente pregunta.

- `/nuevo ID | Tema | Obra | Fecha` — p. ej. `/nuevo deuitlandschekap31782cram | Butterfly | De Uitlandsche Kapellen, Vol. III | 1779-1782`
- `/estado` · `/pendientes` · `/seguir ID` · `/imagenes ID [estilo]` · `/probar ID [estilo]` · `/estilos` · `/actualizar` · `/ayuda`
- Para contestar: *reply* al mensaje de la pregunta (si solo hay una abierta, basta escribir).
  Hoja de contactos → `ok` o `quitar 67, 98` (números de página). Umbral que no cuadra → `ok` (usa el sugerido) o `umbral 25`.

Drive (rclone, remoto `caligari`, permiso `drive.file`, cuenta automation.flow.env): `drive.py` sube el ZIP a
`Caligari_entregas_auto` y saca el enlace público solo; copia hojas de contactos y portadas a `Caligari_Elandres_revision`.
Si rclone falla, el bot pregunta el enlace a mano (cascada). Probar: `rclone lsf caligari:Caligari_entregas_auto`.

## Diseño de las imágenes del listing (sin tocar código)

- `plantillas/diseno.json` — estilo base: fuentes (papeles `titulo`, `texto`, `cursiva`), escala de cada una,
  colores, fondos (madera/papel), textos fijos en inglés y la lista `mocos` (qué imágenes y en qué orden:
  `detalle`, `flatlay`, `incluido`, `tamanos`, `pin`; se pueden repetir, quitar o reordenar).
- `plantillas/estilos/<nombre>.json` — variantes; solo lo que cambia. Ejemplos: `cormorant`, `victoriano`, `prueba_lora`.
- `plantillas/fuentes/` — archivos .ttf/.otf (Google Fonts, OFL; los de la carpeta `static/`). Si falta uno: DejaVu Serif.
- `plantillas/fondos/` — texturas extra (≥ 2400 px).
- Telegram: `/estilos` (qué hay) · `/probar ID estilo` (vista previa, no cambia nada) ·
  `/imagenes ID estilo` (aplica el estilo a ese libro y sube el kit a Drive; el enlace del comprador no cambia) ·
  `/imagenes ID base` (vuelve al base) · `/actualizar` (git pull + reinicio del bot).
- Un libro recuerda su estilo (`meta.estilo` del manifiesto). Para cambiar los mocos de uno o varios listings,
  se crea un estilo con otra lista `mocos` y se aplica con `/imagenes`.
- Terminal: `python3 diseno.py [estilo]` muestra qué fuentes encuentra.

Ver qué hace el bot: `journalctl -u caligari-telegram -f` · Registro de cada libro: `libros/<ID>/registro.log`

## Instalación en el VPS (una sola vez)

```bash
cd /home/minion && mkdir -p caligari && cd caligari
git clone https://github.com/Ellamack/Caligari-pipeline.git pipeline
python3 -m venv venv
source venv/bin/activate
pip install opencv-python-headless numpy pillow cairosvg fpdf2 qrcode
```

Bot de Telegram: token en `/etc/caligari/telegram.env` (solo root, nunca en el repo) con
`TELEGRAM_TOKEN=…` y `TELEGRAM_CHAT_ID=…`; luego
`cp servicio/caligari-telegram.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now caligari-telegram`

Cada vez que entres: `cd /home/minion/caligari/pipeline && source ../venv/bin/activate`
Para traer cambios del repo: `git pull`

## Primer bundle: Cramer, vol. 1

```bash
python3 descargar.py deuitlandschekap11779cram
python3 procesar_laminas.py --libro deuitlandschekap11779cram
python3 responder.py                       # ver la hoja de contactos y contestar
python3 responder.py deuitlandschekap11779cram revision ok
python3 empaquetar.py deuitlandschekap11779cram --tema "Butterfly" --obra "De Uitlandsche Kapellen, Vol. I" --fecha "1775-1779"
```

Bajar el ZIP a la PC (desde PowerShell en la PC, no en el VPS):
```powershell
scp root@IP_DEL_VPS:/home/minion/caligari/libros/deuitlandschekap11779cram/bundle/*_complete.zip .
```
Subirlo a Drive → `Caligari/entregas/`, compartir "cualquiera con el enlace", y:
```bash
python3 responder.py deuitlandschekap11779cram enlace "https://drive.google.com/…"
python3 empaquetar.py deuitlandschekap11779cram
```

Resultado en `/home/minion/caligari/libros/<ID>/bundle/`:
- `Download_Your_Collection.pdf` + `sample_pack.zip` → se suben a Etsy como archivos digitales
- `portada.jpg` + `*_reference_sheet.jpg` + `mocos/` (detalles, flat lay, incluido, tamaños) → imágenes del listing.
  Cada imagen usa láminas distintas.
- `mocos/pin_pinterest.jpg` → pin vertical 1000×1500 para Pinterest (Drive → `T&P/pinterest/`), no para Etsy
- `ficha.json` → título y datos del listing

Al publicar en Etsy: **agregar el listing a su oferta** (Marketing → Sales and discounts). Las ofertas que ya
corren no incluyen listings nuevos. Precios: política en el roadmap del proyecto.

## Reglas
- `--fecha`: obras publicadas por entregas (Cramer 1775-1779). Sin ella se usa el rango de la ficha si lo trae,
  si no, el año.

- Siempre `_jp2.zip`, nunca el PDF de Archive.org (la compresión del PDF degrada las láminas).
- `Caligari/entregas/` en Drive nunca se vacía: ahí viven los ZIP ya vendidos.
- Los intermedios (páginas crudas, láminas sueltas) se borran solos al terminar `empaquetar.py`.
- Si algo falla, el manifiesto (`libros/<ID>/manifiesto.json`) dice en qué etapa y por qué.
  Volver a correr el mismo comando retoma donde se quedó.

## Línea B: SVG premium (manual por ahora)

`quitar_fondo.py` → retoque en GIMP → `vectorizar.py`. Ver la ayuda de cada script con `--help`.

## API de Etsy (app personal, activa desde 12 oct 2026)

- `etsy.py`: conexión (llave `keystring:secret`, token que se renueva solo). `etsy_autorizar.py`: autorización, una vez.
- Una sola vez: en etsy.com/developers → app → Callback URL `http://localhost:3003/callback`; luego en el VPS
  `sudo python3 etsy_autorizar.py --llave` (guarda la llave en `/etc/caligari/etsy.env`, solo root) y
  `sudo python3 etsy_autorizar.py` (abres el enlace, «Allow access», pegas la dirección de localhost que sale).
- Comprobar: `sudo python3 etsy.py`. Si pasan > 90 días sin uso, repetir la autorización.

## Pinterest: demo para el acceso Standard

- Una sola vez: Redirect URI `http://localhost:8085/` en la app; `sudo python3 pinterest_demo.py --llave`.
- Grabar (Win+Alt+R): `sudo python3 pinterest_demo.py bundle/mocos/pin_pinterest.jpg "https://www.etsy.com/listing/…"`.
  Hace OAuth → lee cuenta y tableros → crea tablero si falta → publica un pin (Sandbox) → lo vuelve a leer.
- Subir el video en My apps → Upgrade. Pinterest también exige un enlace de política de privacidad en un dominio propio.

## Línea B por Telegram: restaurado + SVG (13 oct 2026)

`/nuevo ID b` → igual que la A hasta la hoja de contactos; luego `restaurar.py` (lo encadena caligari.py):
1. **fondo**: tira de 5 umbrales sobre la lámina más colorida → `ok` (el del centro) o `umbral 26`.
2. **figuras**: `quitar_fondo.py --separar` en todas las láminas; hojas con cada figura numerada sobre gris →
   `ok` · `quitar 3, 7` · `retocar 12` · `quitar 3 retocar 12` · `umbral 30` (recorta todo de nuevo).
3. **retoque** (si pediste): las figuras van a Drive → `Caligari_Elandres_revision/<ID>_retoque/`; se retocan en GIMP
   y se suben con el mismo nombre eligiendo «Reemplazar el archivo existente» → `listo`.
4. `vectorizar.py` → SVG.
5. Piezas sueltas: en la revisión de figuras, `sueltas 5, 18` → pregunta **especies** (`5: death's head hawkmoth | Acherontia atropos`,
   una línea por figura). `sueltas.py` arma `bundle/sueltas/<n>_<nombre>/` con SVG + PNG (se suben directo a Etsy),
   portada (figura sola, sin texto), detalle, ficha de lo que incluye y pin. Después: datos del listing → `empaquetar.py` arma ZIP con `SVG/`, `PNG/`, README B y
   Reference Sheet; portada, mocos y pin usan cada figura sobre papel claro (`vistas_b`).
Requiere en el venv: `pip install vtracer opencv-python-headless`.

## Caligari (SEO) — carpeta `seo/`
- `/seo` en Telegram: foto del catálogo por API + auditoría (solo lee; no usa modelo, costo cero).
- `sudo python3 -m seo.modelo --llave`: guarda proveedor (deepseek/anthropic), modelo y llave en `/etc/caligari/llm.env`.
- `sudo python3 -m seo.generar --listing ID` o `--libro ID`: propuesta de título, 13 tags y descripción,
  validada (hasta 3 intentos). Se guarda en `seo/datos/propuestas/`; no toca Etsy. Gasto en `seo/datos/gasto.jsonl`.
- `/mercado [término]` o `sudo python3 -m seo.mercado`: por término (de `seo/terminos.txt`), competencia (listings activos)
  y señales de demanda de la primera página (vistas/día, favoritos/día, % digital, precio). API pública; sin modelo.
