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

## Instalación en el VPS (una sola vez)

```bash
cd /home/minion && mkdir -p caligari && cd caligari
git clone https://github.com/Ellamack/Caligari-pipeline.git pipeline
python3 -m venv venv
source venv/bin/activate
pip install opencv-python-headless numpy pillow cairosvg fpdf2 qrcode
```

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
- `LEEME_descarga.pdf` + `sample_pack.zip` → se suben a Etsy como archivos digitales
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
