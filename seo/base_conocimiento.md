# Caligari — base de conocimiento SEO (v0.3 · 13 oct 2026)

Este documento es la formación del agente **Caligari**, especialista en el SEO de The Caligari Cabinet en Etsy.
Caligari lo lee completo antes de cada tarea. Si algo aquí cambia (Etsy cambia sus reglas, los datos de la tienda
contradicen una hipótesis), se actualiza este documento con fecha y fuente: el conocimiento vive aquí, no en el código.

Niveles de confianza que se usan abajo:
- **[Etsy]** dicho por Etsy en documentación oficial, Seller Handbook o su blog de ingeniería.
- **[Fundamento]** principio general de recuperación de información; vale para cualquier buscador.
- **[Terceros]** afirmado por herramientas o blogs de SEO; tratarlo como hipótesis hasta que nuestros datos lo confirmen.
- **[Tienda]** decisión o hallazgo propio de The Caligari Cabinet.

---

## Capa 1 — Fundamentos: qué es y cómo funciona un buscador

### 1.1 Dos problemas distintos: recuperar y ordenar  [Fundamento]
Todo buscador resuelve dos problemas en secuencia:
1. **Recuperación (matching):** de millones de documentos, ¿cuáles *pueden* responder a esta consulta? Es un filtro:
   si un listing no pasa este filtro, no existe para esa búsqueda, sin importar lo bueno que sea.
2. **Ordenamiento (ranking):** entre los recuperados, ¿en qué orden se muestran? Aquí entran relevancia, calidad y
   comportamiento de los usuarios.

Consecuencia: el SEO tiene dos trabajos separados. **Ser elegible** (que nuestras palabras coincidan con las
consultas reales) y **merecer subir** (calidad del listing y señales de que los compradores lo eligen).

### 1.2 Cómo se decide qué coincide  [Fundamento]
- El texto se parte en **tokens** (palabras) y se normaliza: minúsculas, y casi siempre se reduce a la raíz
  (plural ↔ singular). Por eso repetir variantes de una misma palabra rara vez aporta.
- Un **índice invertido** guarda, para cada token, qué documentos lo contienen. Coincidir = compartir tokens.
- Los buscadores modernos añaden **coincidencia semántica**: modelos que entienden que "moth print" y
  "lepidoptera wall art" hablan de cosas cercanas aunque no compartan palabras. La coincidencia léxica no desaparece;
  se le suma una capa de significado.
- Implicación: escribir para **ser entendido** (qué es el producto, de qué trata, para qué sirve) ya no es opuesto
  a escribir para el buscador; es lo mismo.

### 1.3 Cómo se ordena  [Fundamento]
- **Relevancia:** qué tan bien responde el documento a toda la consulta (no solo a una palabra de ella).
- **Calidad:** propiedades del documento que no dependen de la consulta (fotos, datos completos, reputación).
- **Comportamiento:** impresiones → clics → compras. Un sistema que aprende de clics y compras ("learning to rank")
  premia lo que la gente elige. Esto crea un **bucle**: lo que se vende sube, lo que sube se ve más.
- **Exploración:** para no quedarse atrapado en ese bucle, el buscador muestra a prueba cosas nuevas (un impulso
  temporal a listings recientes). Es la ventana en la que un listing nuevo puede demostrar que convierte.

### 1.4 Intención  [Fundamento]
Cada consulta expresa una intención. En un marketplace hay dos grandes tipos:
- **Específica** ("pieter cramer butterfly print"): el comprador sabe lo que quiere. Pocos resultados, alta conversión.
- **Exploratoria** ("vintage wall art"): está viendo opciones. Muchísimos resultados, conversión baja.
Etsy distingue ambas midiendo qué tan dispersos quedan los resultados entre categorías **[Etsy, 2015]**.

### 1.5 Economía de las palabras: la cola larga  [Fundamento]
- Las consultas siguen una distribución de **cola larga**: unas pocas palabras genéricas concentran mucho volumen,
  y una enorme cantidad de consultas específicas tiene poco volumen cada una, pero en conjunto suman más.
- Lo que importa no es el volumen bruto sino **volumen × probabilidad de ganar**. Una consulta genérica con 50 000
  listings compitiendo da casi cero; una específica donde somos de los pocos realmente relevantes da ventas.
- Para una tienda pequeña y de nicho, la estrategia racional es **ganar muchas consultas específicas** donde el
  producto es exactamente lo que se busca.

### 1.6 Cartera de consultas y canibalización  [Fundamento]
- Cada listing "compra" un conjunto de consultas. La tienda es una **cartera**: conviene cubrir muchas consultas
  distintas, no que 30 listings compitan por las mismas.
- **Canibalización:** cuando dos listings propios apuntan a la misma consulta, se reparten impresiones y señales;
  ninguno acumula suficiente historial para subir. Peor aún si el buscador limita cuántas veces muestra la misma
  tienda arriba (ver 2.8).

### 1.7 Medir antes de opinar  [Fundamento]
El embudo es: **impresiones → clics (CTR) → compras (conversión)**. Cada etapa falla por razones distintas:
| Síntoma | Causa probable | Qué se toca |
|---|---|---|
| Pocas impresiones | No coincide con lo que se busca, o compite donde no puede ganar | Palabras: título, tags, atributos, categoría |
| Impresiones sin clics | La miniatura o el título no convencen | Primera foto, título |
| Clics sin compras | La página no convence: precio, descripción, imágenes | Precio, descripción, fotos 2–10 |
Reglas de experimento: cambiar **una** cosa a la vez, esperar 2–4 semanas, comparar contra el mismo periodo, y
recordar la estacionalidad (Halloween, Navidad, fin de cursos) antes de atribuir un cambio a nuestro ajuste.

---

## Capa 2 — Cómo funciona la búsqueda de Etsy

### 2.1 Qué usa Etsy  [Etsy, Seller Handbook, ago 2025]
- "Etsy search takes a holistic view of your listing, including **title, tags, attributes, descriptions, first photo,
  reviews**."
- La descripción pesa en la **segunda fase** (ordenamiento).
- Tener **políticas de tienda** tiene efecto positivo en la posición.
- Un listing nuevo puede aparecer sin reseñas si no tiene problemas de calidad del listing o de la tienda.

### 2.2 Relevancia semántica con modelos de lenguaje  [Etsy, Code as Craft, ene 2026]
- Etsy etiqueta pares consulta–listing como **relevante / parcialmente relevante / irrelevante** y entrena modelos
  que juzgan relevancia a escala (millones de pares por día).
- Para juzgar consideran **título, imágenes, descripción, atributos, variaciones y entidades extraídas**.
  El artículo **no menciona los tags**.
- "Relevante" = cubre **todas** las partes de la consulta, incluidos nombres propios.
- Implicación [inferencia]: un listing que describe con precisión lo que es (con imágenes y atributos coherentes)
  gana; un tag que no corresponde al producto puede traer impresiones que el modelo juzga irrelevantes.

### 2.3 Calidad del listing (página Search Visibility)  [Etsy, Help Center]
En Shop Manager → Search visibility, Etsy revisa y recomienda:
- Al menos una imagen; **primera foto de alta resolución, idealmente 2000 px o más** de ancho y alto.
- La primera foto debe mostrar **un solo producto terminado, sin collages ni imágenes unidas**, clara y bien iluminada.
  El Handbook añade: evitar **texto superpuesto, collages o colecciones** en la primera miniatura.
- **Categoría lo más específica posible.**
- **Política de devoluciones** presente, aunque sea "No returns".
- Tienda con **logo**.
- Etsy integra la calidad del listing en el ordenamiento desde 2024 (Nick Daniel, CPO, sep 2024).

### 2.4 Títulos  [Etsy, Seller Handbook, ago 2025]
- Nombrar el objeto con claridad y poner primero los rasgos clave: el comprador solo ve las primeras palabras.
- **Menos de 15 palabras.**
- Palabras subjetivas ("perfect", "beautiful") van a la descripción.
- Sin precio, envío ni ofertas (Etsy ya los muestra).
- Evitar repetir palabras ("unisex adult poncho, unisex cotton poncho").
- Lo que se quite del título se mueve a tags, atributos o descripción; no se borra.
- Etsy dice que no castiga títulos de estilo antiguo [vía eRank]. El cambio es recomendado, no obligatorio.

### 2.5 Tags  [Etsy, Seller Handbook, ago 2025]
- **Usar los 13 tags** en todos los listings. Cada tag tiene un máximo de 20 caracteres [límite de la plataforma].
- Frases de varias palabras, naturales.
- Prueba: "If you can't imagine someone typing a phrase into Google, it shouldn't be in your tags."
- Variar: qué es, cómo está hecho, para quién es.
- **No duplicar en tags lo que ya está en atributos.**

### 2.6 Atributos y categoría  [Etsy, Seller Handbook, ago 2025]
- Los atributos funcionan como tags y ayudan a coincidir con búsquedas.
- Una categoría más específica desbloquea atributos más específicos.
- Si la opción exacta no existe, elegir la más cercana.
- Etsy rellena atributos con modelos de lenguaje cuando faltan [Etsy vía RankHero]: mejor dárselos nosotros, correctos.

### 2.7 Descripción  [Etsy, Seller Handbook, ago 2025]
- Datos esenciales arriba (qué incluye, tamaños, formato).
- Palabras clave relevantes en las primeras frases, **sin copiar el título palabra por palabra**.
- Párrafos cortos o viñetas.

### 2.8 No existe "la posición"  [Etsy, vía RankHero]
- Resultados personalizados según el comprador; cada persona ve un orden distinto.
- Impulso temporal a listings nuevos o renovados. Renovar *solo* para el impulso no funciona.
- Límite de frecuencia: Etsy evita mostrar demasiado la misma tienda o listing arriba para un mismo usuario.
  Esto refuerza 1.6: tener 4 listings casi iguales no multiplica la visibilidad.
- Reseñas: las recientes pesan más.
- Etsy no publica los pesos de cada factor.

### 2.9 Datos propios que Etsy da gratis  [Etsy]
- **Search visibility** (Shop Manager): qué listings tienen problemas de calidad, y herramienta de sugerencia de títulos.
- **Stats / Search analytics**: consultas con las que los compradores encontraron la tienda, con impresiones, clics y
  ventas. Es la única fuente de **datos reales** de búsqueda. Pendiente: confirmar en Shop Manager qué métricas exactas
  muestra hoy.

### 2.10 Lo que dicen terceros (hipótesis, no reglas)  [Terceros]
- Coincidencia **exacta** (palabras en el orden de la consulta) pesa un poco más que la amplia (eRank).
- Etsy maneja plurales y errores de escritura; no hace falta incluirlos (ListingView).
- Repetir una palabra en varios tags no suma (ListingView).
- Los **sinónimos y variantes regionales sí** hay que cubrirlos: "moth" ≠ "lepidoptera"; "colour" ≠ "color" (ListingView).
- La posición se estabiliza en 7–14 días tras un cambio (reportes de vendedores).

---

## Capa 3 — Herramientas de pago: cuándo compensan

**Criterio:** pagar solo por lo que las capas 1–2 y los datos propios no dan. Lo único que nos falta es una
estimación de **volumen y competencia por palabra** antes de tener historial propio.

| Herramienta | Precio (2026, aprox.) | Qué da | Ojo |
|---|---|---|---|
| eRank | Gratis; Pro ~£6/mes | Volumen estimado, competencia, tendencias por país, auditoría de listings | Volúmenes **estimados por terceros**, no de Etsy |
| Marmalead | ~£14/mes, sin plan gratis | Una puntuación propia de "engagement" | Métrica cerrada, no verificable |
| EverBee | Gratis limitado; Growth $29.99/mes | Investigación de producto (ventas estimadas) + tags | Más orientada a buscar productos que a SEO |

**Recomendación actual:** no pagar todavía.
1. Usar **Search visibility** y **Stats** (gratis, datos reales) durante 30 días con los listings actuales.
2. Usar **eRank gratis** para sondear volumen de las palabras candidatas.
3. Reconsiderar **eRank Pro** (el más barato y transparente) solo si el plan gratuito limita el trabajo de Caligari.

Ninguna herramienta tiene los conteos reales de Etsy: sus números son direccionales.

---

## Capa 4 — Cómo trabaja Caligari en esta tienda

### 4.1 Reglas de la tienda (no negociables)  [Tienda]
1. Cada listing tiene una **búsqueda principal** propia, declarada explícitamente.
2. Con sus hermanos (mismo tema/obra), comparte **menos del 50%** de tags.
3. **Línea A nunca dice "restored"**: "taken from a high-resolution scan of the original book, then straightened,
   cropped and given a gentle colour enhancement for printing". "Restored" solo para línea B (SVG).
4. Nada que el producto no sea. Si no es un archivo de corte, no lleva tags de corte (ver 4.3).
5. Bilingüe: título, tags y descripción en inglés (mercado principal) y español.
6. Título de menos de 15 palabras; 13 tags de máximo 20 caracteres; sin repetir lo que ya va en atributos.

### 4.2 Dónde puede ganar esta tienda  [Fundamento aplicado]
Productos de nicho, con historia verificable. Las consultas donde somos **de verdad** la respuesta más relevante:
- **Obra / autor / año:** "cramer butterfly prints", "merrem bird illustration", "redoute roses print".
  Poca competencia y relevancia total (nombres propios: ver 2.2).
- **Especie o grupo:** "hawk moth print", "antique beetle art", "trogon illustration".
- **Uso:** "junk journal printables", "printable wall art", "botanical clipart".
- **Estética:** "dark academia decor", "cabinet of curiosities", "cottagecore wall art".
- **Formato:** "png clipart transparent", "svg bundle" (solo línea B).
Las consultas genéricas ("butterfly print", "vintage art") se pueden incluir como apoyo, no como apuesta principal.

### 4.3 Hallazgos de la auditoría inicial (11 oct 2026)  [Tienda]
1. **Primera foto de los bundles: representar el conjunto, sin parecer collage con texto.** El producto de un bundle
   *es* el conjunto (97 láminas): una sola lámina en la miniatura sería engañosa (corrección de Elandrés, 12 oct 2026;
   la guía de Etsy está pensada para productos únicos). Lo que sí aplica de 2.3: Etsy marca como problema de calidad la
   primera foto con **collage en cuadrícula** y con **texto superpuesto**. Opciones, de menor a mayor riesgo:
   (a) escena tipo flatlay: varias láminas apiladas sobre madera, que se lee como foto de un objeto real;
   (b) cuadrícula sin texto (la información va en el título); (c) portada actual con cuadrícula y texto.
   **Decidido con datos (12 oct 2026):** la página Search visibility de la tienda marca **un solo factor de riesgo:
   títulos (12 listings con sugerencia de título)**. Nada sobre fotos, aunque los Cramer 1–2 usan portada con cuadrícula
   y texto. **Se mantiene la portada actual.** Tienda y atención al cliente: "on track". Volver a revisar si aparece
   un aviso de fotos.
   Para listings de una sola ilustración (SVG individuales), la primera foto sí es esa ilustración sola.
2. **`cricut_svg` y `laser_cut_file` están en 30 de 31 listings.** **Decidido 13 oct 2026: se quitan.**
   Razón de fondo [Fundamento]: una cortadora (Cricut, Silhouette, láser en modo corte) sigue el **contorno de cada
   trazo** del SVG. Nuestros SVG son trazado multicolor apilado (~34 colores, cientos de trazos por figura): la
   cortadora los vería como cientos de capas y piezas diminutas. Quien busca "cricut svg" espera diseños de pocas capas
   pensados para cortar; recibir lo nuestro es una búsqueda irrelevante para el modelo de Etsy (2.2) y un comprador
   decepcionado. Lo que sí es cierto y puede ir en tags: PNG transparente para **"print then cut"** (la cortadora imprime
   la imagen y corta solo el contorno exterior), stickers, sublimación, grabado láser a partir del PNG.
   Idea de producto para después: una versión "silueta" de cada figura (un solo contorno, sacado del canal de
   transparencia) sí sería un archivo de corte real.
3. Títulos: promedio 14.3 palabras; 4 de 31 pasan de 15. Revisar esos 4 con la regla 2.4.
4. Todos los listings usan los 13 tags (bien).
5. Search visibility revisada (12 oct): solo títulos (12 listings). Falta **Stats** (consultas reales).

### 4.4 Entradas, salida y control  [Tienda]
**Entradas por listing:** manifiesto del libro (obra, autor, fecha, tomo, número de láminas, línea A/B), la ficha de
Archive.org, el catálogo actual (título y tags de todos los listings), y cuando existan, los datos de Stats.

**Salida (contrato JSON):**
```json
{
  "busqueda_principal": "cramer butterfly prints",
  "titulo_en": "...", "titulo_es": "...",
  "tags_en": ["...13..."], "tags_es": ["...13..."],
  "descripcion_en": "...", "descripcion_es": "...",
  "categoria": "...", "atributos": {"...": "..."},
  "primera_foto": "lamina_mas_vistosa",
  "justificacion": "por qué estas palabras: intención, competencia, relación con los hermanos"
}
```

**Validador mecánico (código, no modelo).** Rechaza y pide corrección si:
- el título tiene 15 palabras o más;
- hay algún tag de más de 20 caracteres, o no son exactamente 13;
- comparte 50% o más de tags con un hermano;
- un listing de línea A contiene "restor";
- hay tags repetidos o duplicados con los atributos.

**Revisión humana:** Elandrés aprueba el borrador en Etsy. Nada se publica sin él.

**Ciclo mensual:** leer Stats → por listing, diagnosticar con la tabla de 1.7 → proponer **un** cambio por listing →
registrar fecha y cambio → evaluar a las 4 semanas.

---

## Pendiente / por verificar
- Confirmar las métricas exactas de Stats / Search analytics en Shop Manager (la página de ayuda pide sesión).
- Revisar la página Search visibility de la tienda y anotar lo que marca.
- Revisar las 12 sugerencias de título de Etsy (Search visibility → Update titles) contra las reglas 4.1 antes de aceptarlas.
- Leer el artículo de Etsy "New Guidance for Listing Titles, and a Tool to Help" directamente (aquí se cita vía eRank).

## Fuentes
- Etsy Seller Handbook — "The Anatomy of a Well-Crafted Etsy Listing" (26 ago 2025): https://www.etsy.com/seller-handbook/article/1347574487014
- Etsy Help — "How to Use the Etsy Search Visibility Page": https://help.etsy.com/hc/articles/25869947521175
- Etsy Engineering — "How Etsy Uses LLMs to Improve Search Relevance" (16 ene 2026): https://www.etsy.com/codeascraft/how-etsy-uses-llms-to-improve-search-relevance
- Etsy Engineering — "Targeting Broad Queries in Search" (29 jul 2015): https://www.etsy.com/codeascraft/targeting-broad-queries-in-search/
- PYMNTS — entrevista a Nick Daniel, CPO de Etsy (6 sep 2024): https://www.pymnts.com/commerce/ecommerce/2024/etsys-new-search-tools-aim-to-elevate-quality-listings-and-enhance-seller-success/
- eRank — "Etsy Title Update 2025": https://help.erank.com/blog/seo/etsy-title-update-2025-how-to-write-better-etsy-listing-titles/
- eRank — "Etsy SEO Basics": https://help.erank.com/blog/etsy-seo-basics/
- RankHero — "The State of Etsy SEO in 2026": https://www.rankhero.com/blog/the-state-of-etsy-seo-in-2026-how-etsy-search-really-works
- ListingView — "Etsy Tags Best Practices in 2026": https://listingview.io/blogs/etsy-tags-best-practices-in-2026-the-full-playbook
- ListifyAI — "eRank vs Marmalead 2026": https://www.listifyai.net/blog/erank-vs-marmalead-2026
- RevenueGeeks — "EverBee pricing": https://revenuegeeks.com/everbee-pricing/
