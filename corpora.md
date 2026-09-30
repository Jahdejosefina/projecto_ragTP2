# El menú de corpus

<!-- ---------------------------------------------------------------------------
     POR INSTANCIA: cada versión fijada de abajo (commits, hashes de archivos,
     fechas de dumps, versiones de DOI, URLs) envejece. Volvé a verificar cada
     una al reutilizar esto en otro cuatrimestre.
     Última verificación: 2026-09-27.
     --------------------------------------------------------------------- -->

Elegí **uno** de los cinco corpus de abajo, o traé el tuyo. Cada uno está acá porque plantea un
problema de recuperación *distinto* -- y cada uno esconde al menos un defecto que un loader
ingenuo deja pasar sin ningún error. Encontrarlo es parte de la Etapa 1.

No son igual de difíciles, y no se pretende que lo sean. Lo que se evalúa es la calidad de tus
decisiones y de tu lectura de los resultados sobre el corpus que elegiste -- nunca una métrica
absoluta comparada entre corpus. La tabla de abajo es nuestra mejor estimación de adónde se va
el esfuerzo; contá en tu registro de decisiones adónde se fue en realidad.

| | Corpus | Esfuerzo de limpieza | Tamaño a manejar | Escribir un conjunto de evaluación | El generador ya lo conoce |
|---|---|---|---|---|---|
| R1 | Informes de precios al consumidor del INDEC | **alto** (tablas en PDF) | chico | **fácil** (los CSV oficiales responden la mayoría de las preguntas) | bajo |
| R2 | python-docs-es | medio (dos rutas, las dos sucias) | medio | medio (se puede derivar automáticamente, se filtra con facilidad) | **alto** |
| R3 | Legislación nacional argentina | medio (metadatos que mienten) | lo elegís vos | medio | medio |
| R4 | es.stackoverflow | medio (XML + HTML + código) | **grande** (subconjunto por tag) | **fácil** (links de duplicados de los moderadores) | **alto** |
| R5 | Versiones taquigráficas del Senado argentino | bajo (ya parseado) | **grande** (subconjunto por debate) | **difícil** (sin ninguna etiqueta) | bajo |

"El generador ya lo conoce" importa porque un modelo que leyó tu corpus durante el entrenamiento
responde muchas preguntas *sin* recuperación: tu fila a libro cerrado (Etapa 4) va a ser alta, y
lo que te compra RAG es la versión correcta, una cita y un "no está documentado" honesto --
medí eso, no solo si la respuesta es correcta.

Para todos los corpus: **fijá la versión que usás** (un commit, una fecha de dump, una versión de
DOI, o una fecha de descarga más el sha256), **respetá la licencia** y su atribución, y **nunca
commitees los datos crudos** a tu repo -- `corpora/` está en el gitignore por eso.

---

## R1 · Informes mensuales de precios al consumidor del INDEC (IPC)

**Qué es.** El instituto de estadística argentino publica todos los meses un informe del índice
de precios al consumidor ("Índice de precios al consumidor", IPC) como un PDF de 10-20 páginas y
15-25 tablas (la plantilla fue creciendo con los años) -- por región, por división de gasto,
mensual e interanual -- más las series principales como archivos CSV.

- **Acceso.** Informes: PDFs bajo `https://www.indec.gob.ar/uploads/informesdeprensa/`. Desde
  mediados de 2019 los nombres de archivo llevan un hash (`ipc_09_26A1BE2DC4CD.pdf` es el informe
  de *agosto* de 2026: el mes del nombre es el mes de publicación); los anteriores no
  (`ipc_07_17.pdf`). Así que tenés que *armar la lista de URLs*: el sitio actual enlaza solo el
  último informe y carga el resto con JavaScript; el sitio anterior
  (`https://sitioanterior.indec.gob.ar/informesdeprensa_anteriores.asp?id_tema_1=3&id_tema_2=5&id_tema_3=31`,
  congelado en julio de 2019) lista los informes hasta junio de 2019 como links estáticos. Series:
  `https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv` y
  `serie_ipc_aperturas.csv` -- separador `;`, coma decimal, `NA` para valores faltantes,
  codificación Latin-1 con fines de línea CRLF (`pd.read_csv(url, sep=";", decimal=",",
  encoding="latin-1")`), períodos como `YYYYMM` desde 201612; `aperturas` tiene las seis regiones
  pero no el total nacional.
- **Subconjunto sugerido.** Los informes de cobertura nacional, desde el informe de junio de 2017
  (`ipc_07_17.pdf`) hasta el último: unos 110 documentos. Los informes anteriores cubren solo el
  Gran Buenos Aires, con la clasificación vieja, así que las filas regionales del CSV de 2016-12 a
  2017-05 no tienen informe correspondiente. Versión fijada: la lista de URLs más un sha256 por
  archivo.
- **La tarea de datos sucios.** Tablas. La extracción de texto corre las columnas (las columnas
  regionales salen desalineadas) y aplana los gráficos en tiras de números. Decidí por tabla:
  mantenerla, linealizarla en oraciones "encabezado: valor", o reemplazarla por la fila del CSV de
  la que salió. Los títulos de las tablas dan el mes del informe *sin el año* ("Variaciones de
  agosto con respecto al mes anterior"), y varios llevan en cambio el año *anterior* ("con
  respecto a diciembre de 2025"): el año del propio informe tiene que viajar en cada chunk, o
  marzo de 2023 y marzo de 2024 son el mismo pasaje -- y un extractor de fechas ingenuo etiqueta
  las tablas de este año como del año pasado.
- **Identificadores y claves de respuesta.** La mayoría de los números de un informe también
  están en los CSV -- niveles del índice y variaciones mensuales e interanuales por región,
  división y las aperturas principales -- así que preguntas como "¿cuánto aumentó alimentos y
  bebidas en el NEA en marzo de 2024?" se pueden generar y corregir *exactamente*, en cantidad
  (normalizá primero las comas decimales). Tres tipos no están en los CSV: las incidencias
  (contribuciones en puntos porcentuales), las variaciones acumuladas en el año (calculalas a
  partir del índice) y los precios promedio de productos seleccionados (una planilla aparte).
- **Qué pone mejor a prueba.** Documentos casi idénticos (cien meses de una plantilla que crece
  con el tiempo -- los números de tabla se corren, así que usá el título como clave, no "Cuadro
  N"), números dentro de tablas, y el tiempo ("¿y el mes anterior?").
- **Gancho de memoria.** Una preferencia *procedimental*: "compará siempre con el mismo mes del
  año anterior" es una regla sobre cómo responder, no un hecho sobre el usuario.
- **Licencia.** El material del sitio del INDEC es CC BY-SA 4.0 (enlazado desde el pie de
  indec.gob.ar), y cada informe dice "Se permite su reproducción con atribución de la fuente".
  Citá al INDEC, el informe y el período, y aclará tus cambios (por ejemplo, tablas linealizadas).
- **Bibliotecas.** `requirements-corpora.txt` (PyMuPDF y/o pdfplumber).

## R2 · python-docs-es (la documentación de Python en español)

**Qué es.** La traducción comunitaria de la documentación oficial de Python. **Este es el corpus
de la Etapa 0 resuelta** (`00_corpus_audit`): si lo elegís, esa auditoría es donde tu Etapa 0
*empieza*, no donde termina -- esperamos que vayas más allá.

- **Acceso.** Dos rutas, y elegir entre ellas es una decisión que se evalúa:
  - *los archivos de traducción*: `git clone -b 3.13 https://github.com/python/python-docs-es`
    (una rama por versión, 3.7-3.14; 3.14 es la rama por defecto y la única que se sigue
    traduciendo; 3.13 se detuvo en `507e3375` el 2026-02-25, el commit que fija la auditoría;
    3.12 se detuvo en noviembre de 2024). Un archivo `.po` por página: pares *(original en
    inglés, traducción al español)*.
  - *la documentación compilada*: `https://docs.python.org/es/<version>/archives/python-<version>-docs-html.zip`.
    Se recompila en el mismo lugar, a menudo a diario -- dos descargas con minutos de diferencia
    pueden diferir: fijá el sha256 y la fecha de descarga.
- **Subconjunto sugerido.** `library/`, `builtins/`, `tutorial/`, `howto/`, `reference/`, `faq/`
  de una o dos versiones. Medido en la auditoría: ~7,6 M caracteres, ~2 M tokens del generador
  solo para 3.13 -- unas 240 ventanas de 8.192.
- **La tarea de datos sucios.**
  - El proyecto marca las traducciones fuzzy como posiblemente desactualizadas -- y algunas
    directamente están mal (la muestra smoke de la auditoría muestra un ejemplo de código
    traducido para `batched` que en realidad es una llamada a `islice`; la corrida completa
    muestra otros parecidos). La compilación oficial muestra el inglés para esas entradas; un
    loader de `.po` ingenuo las indexa.
  - Los archivos `.po` **no tienen firmas de la API ni números de versión** (esos viven en las
    fuentes `.rst` en inglés); el HTML tiene los dos.
  - Las páginas compiladas están **parcialmente en inglés** en cada párrafo sin traducir o
    fuzzy -- y algunas páginas enteras nunca se tradujeron: la columna "unmarked" de la
    auditoría muestra cuáles, y comparar versiones muestra por qué. Las notas de versión vienen
    en los dos idiomas ("Added in version 3.13" al lado de "Distinto en la versión 3.12").
  - Algunas páginas son stubs de redirección sin contenido; el repo de traducción todavía
    tiene archivos traducidos al 100% de páginas que Python ya no publica (`distutils/`,
    `install/`).
- **Identificadores y claves de respuesta.** Las anclas de la API (`pathlib.Path.resolve`) y las
  notas de versión permiten derivar automáticamente preguntas de identificador y de "¿desde qué
  versión existe…?" -- y hacen muy fácil escribir preguntas que copian el pasaje (la trampa de la
  Etapa 2). "¿Puedo usar X en 3.12?" es una pregunta de sí/no: las dos respuestas citan la
  versión, así que necesita un `expected_verdict`, no solo una clave.
- **Qué pone mejor a prueba.** Identificadores literales (la recuperación densa sola no los
  encuentra) y versiones: las versiones consecutivas son mayormente idénticas palabra por
  palabra (el 85% de los párrafos de 3.13 aparece textual en 3.12), así que la respuesta
  correcta muchas veces depende de por qué versión se pregunta.
- **Gancho de memoria.** "Estoy en Python 3.12" -- un hecho del usuario que debería convertirse
  en un filtro de recuperación (o al menos en una anotación), y que después cambia ("migramos a
  3.13").
- **Licencia.** La documentación de Python está bajo la licencia de la PSF (los ejemplos de
  código, además, bajo 0BSD); las traducciones aportadas a python-docs-es son CC0. Atribuí la
  página de origen.
- **Advertencia.** Es casi seguro que el generador leyó la documentación de Python. Tu fila a
  libro cerrado va a ser alta; evaluá la fundamentación (la versión correcta, una cita
  verificable, abstenerse ante lo que no está -- por ejemplo, una API que solo existe en una
  versión posterior).

## R3 · Legislación nacional argentina (legalize-ar + InfoLEG)

**Qué es.** Normas nacionales argentinas (leyes, decretos) en Markdown con front matter YAML, un
archivo por norma, en `legalize-ar`, cuyo historial de git intenta reproducir cada reforma como
un commit fechado en su publicación; más las tablas de metadatos de InfoLEG del Ministerio de
Justicia (qué normas modifican a cuáles).

- **Acceso.** `git clone https://github.com/legalize-dev/legalize-ar` (fijá un commit).
  Metadatos de InfoLEG: el dataset "Base Infoleg de Normativa Nacional" en `datos.jus.gob.ar`
  (`/dataset/base-de-datos-legislativos-infoleg`): CSV en UTF-8 comprimidos en ZIP, que incluyen
  las tablas de "normas modificadas" y "normas modificatorias". Cubre las normas publicadas en el
  Boletín Oficial desde mayo de 1997 más las normas que estas referencian, así que pueden faltar
  modificaciones más viejas. Los textos actualizados en InfoLEG
  (`servicios.infoleg.gob.ar/.../texact.htm`) si necesitás verificar una muestra -- scrapeá con
  cortesía.
- **Subconjunto sugerido.** Curá 50-300 normas alrededor de un tema: el Código Civil y
  Comercial, la Constitución, la ley de contrato de trabajo, defensa del consumidor, la ley de
  sociedades, y las normas que las modificaron.
- **La tarea de datos sucios.** **Los metadatos mienten, y nada te avisa.** Ejemplos
  verificados: `LEY-340` (el Código Civil viejo) figura con `status: in_force` mientras su propio
  campo `observaciones` dice que fue derogada por la ley 26.994, y su cuerpo es un índice de
  links en lugar de artículos; el `last_updated` de la Constitución es `1900-01-01`. El
  historial de reformas es tan bueno como el pipeline que lo reconstruyó (un campo
  `reform_quality` dice clean / partial / bootstrap-only, y a algunos archivos les falta): la ley
  de defensa del consumidor, modificada cientos de veces, tiene dos commits. Los encabezados de
  artículo varían entre archivos -- `**ARTICULO 1º** —`, `**Artículo 1º**.-`,
  `###### ARTICULO 1º —`, `ARTICULO 1° —` a secas, con `º` y `°` los dos en uso: escribí un
  patrón tolerante y probalo en todos los archivos. Derivá la vigencia de las tablas de modificaciones de InfoLEG y de las
  notas "(Artículo sustituido por…)" en lugar de confiar en `status`.
- **Identificadores y claves de respuesta.** Números de norma y números de artículo ("artículo
  14 bis"). "¿Qué decía el artículo X antes de la reforma de …?" se puede responder con
  `git log -p` solo para las normas cuyo historial fue reconstruido -- contá primero los commits
  por archivo; si no, compará el texto original de InfoLEG (`norma.htm`) con el actualizado
  (`texact.htm`).
- **Qué pone mejor a prueba.** Estructura jerárquica (libro / título / capítulo / artículo),
  vigencia en el tiempo y actualizaciones de conocimiento -- una ley cambia y el texto viejo no
  tiene que ganar.
- **Gancho de memoria.** Una fecha de referencia ("pregunto por un contrato firmado en 2019") que
  debería seleccionar la versión vigente en esa fecha.
- **Licencia.** CC BY 4.0 (atribución a la fuente: SAIJ / Ministerio de Justicia).
- **Nota.** Estructuralmente es el más parecido al corpus sobre el que construimos RAG; lo que
  agrega es el tiempo -- versiones y vigencia.

## R4 · es.stackoverflow (Stack Overflow en español)

**Qué es.** Cada pregunta, respuesta y comentario del Stack Overflow en español, con puntajes,
respuestas aceptadas, tags, historial de ediciones y los links entre posts (links que pegan los
usuarios, y cierres por duplicado).

- **Acceso.** El dump de datos de Stack Exchange tal como lo republicó la comunidad en
  archive.org (un reemplazo no oficial de la publicación oficial discontinuada):
  `https://archive.org/download/stackexchange_20251231/stackexchange_20251231/es.stackoverflow.com.7z`
  (~522 MiB; XML: `Posts`, `PostLinks`, `Comments`, `Tags`, ...). Fijamos el dump del
  **2025-12-31**: quien lo subió aclara que a partir del dump del 2025-06-30 Stack Exchange agregó
  marcas de agua ("data poisoning"), que "does not appear to apply" al del 2025-12-31. Hay dumps
  más nuevos; si usás uno, verificá primero que no tenga marcas de agua.
- **Subconjunto sugerido.** Unos pocos tags (evitá solo Python si otro grupo toma R2): unos
  pocos miles de hilos de preguntas.
- **La tarea de datos sucios.** Parsear en streaming un archivo XML grande; los cuerpos de los
  posts son HTML con bloques `<pre><code>` que tienen que sobrevivir como código; decidir qué es
  un *documento* (¿una pregunta con su respuesta aceptada? ¿con todas las respuestas? ¿con los
  comentarios?); respuestas viejas (la respuesta aceptada de 2016 puede estar mal hoy).
- **Identificadores y claves de respuesta.** **Etiquetas de relevancia listas para usar**: la
  comunidad (usuarios con privilegio de voto de cierre, o moderadores) cierra una pregunta como
  duplicada de otra (`PostLinks` con `LinkTypeId = 3`; `PostId` es el duplicado, `RelatedPostId`
  el original). Cada duplicado es una consulta real de un usuario cuyo destino correcto es el
  original -- un gold set que no tuviste que escribir.
- **Qué pone mejor a prueba.** La forma real en que escriben los usuarios (errores de tipeo,
  títulos vagos, errores pegados) que no coincide con la redacción de la respuesta; ordenar por
  calidad, no solo por similitud.
- **Gancho de memoria.** La versión de la biblioteca o del framework del usuario, que decide si
  una respuesta vieja todavía aplica.
- **Licencia.** CC BY-SA, con la versión según la fecha del aporte: 3.0 para el contenido hasta el
  2018-05-01 (el sitio abrió en 2015), 4.0 después (ver `LICENSE.txt` en el dump). **La
  atribución es obligatoria**: cada cita debería nombrar el post (link y autor).

## R5 · Versiones taquigráficas de las sesiones del Senado argentino (ar_congress)

**Qué es.** Todas las sesiones del Senado 1998-2026 (completas desde 2002), ya parseadas en
bloques de discurso atribuidos a un orador, con el bloque político del orador *en esa fecha*, la
provincia, la fecha de la sesión y el turno.

- **Acceso.** Registro de Zenodo `10.5281/zenodo.22959187`, versión **0.5.8**
  (`ar_congress_senado_0.5.8.tar.gz`, ~95 MB, un parquet por sesión). Fijá el DOI de la versión:
  se publican versiones nuevas seguido. Código y diccionario de datos:
  `github.com/jpripamonti/ar_congress`.
- **Subconjunto sugerido.** Uno o dos debates emblemáticos -- los debates de la ley de
  interrupción voluntaria del embarazo (IVE) de 2018 y 2020, o la "Ley Bases" de 2024 -- unos
  pocos miles de bloques de discurso.
- **La tarea de datos sucios.** Liviana, y distinta: discursos muy largos que necesitan
  sub-chunking con un encabezado del orador; filas de eventos taquigráficos (aplausos,
  votaciones, interrupciones) para conservar o descartar; nombres de oradores escritos de varias
  formas; pertenencia a bloques que cambia con el tiempo y hay que resolver *a la fecha de la
  sesión*.
- **Identificadores y claves de respuesta.** Ninguna lista: armá el conjunto de evaluación a
  partir de los metadatos ("¿quién fue el miembro informante…?") más preguntas escritas a mano --
  y, si un modelo redacta algunas, verificá cada una.
- **Qué pone mejor a prueba.** Conversación cargada de entidades y de correferencias: "¿qué dijo
  la senadora X sobre …?" → "¿y su bloque cómo votó?" → "¿y en 2020?". Filtrar por orador y fecha
  junto con la búsqueda semántica.
- **Gancho de memoria.** El bloque, la provincia o el senador que sigue el usuario.
- **Licencia.** Estructura y anotaciones CC BY 4.0 (código MIT); los discursos en sí son registro
  parlamentario público -- está bien para un trabajo del curso, citá la sesión.

---

## Traé el tuyo

Cualquier corpus es bienvenido si podés argumentarlo frente a las mismas **siete propiedades**
(la respuesta está ahí · texto limpio · estructura interna · identificadores estables ·
metadatos · cambia o tiene versiones · se puede armar un conjunto de evaluación) más el octavo
hecho (**cuán parecidos son los documentos entre sí**), en la Etapa 0, con números. En español o
en inglés. Tiene que poder usarse legalmente para un trabajo del curso, poder descargarse sin
scrapear un sitio que lo prohíba, y ser lo bastante grande como para **no** entrar en una
ventana de contexto. Consultanos antes de dedicarle una semana.
