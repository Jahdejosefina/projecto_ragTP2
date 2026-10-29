# Corpus Card — RAG Jurídico Argentino

## 1. Descripción

Corpus de documentos normativos argentinos preparado para un sistema
de Retrieval-Augmented Generation (RAG).

## 2. Procedencia

- Repositorio: https://github.com/legalize-dev/legalize-ar
- Commit solicitado: 3d2450b5c09a
- Formato de origen: Markdown con metadatos YAML.
- Idioma: español.
- Documentos seleccionados: 170.

## 3. Criterio de selección

Se seleccionaron los archivos Markdown que contienen al menos una de
las siguientes expresiones, sin distinguir mayúsculas y minúsculas:

`defensa del consumidor`, `24.240`, `ley 24240`

La búsqueda se realizó sobre el archivo completo, incluido su YAML.

## 4. Normalización

Se aplicaron las siguientes reglas:

- Normalización Unicode NFC.
- Sustitución de caracteres de control identificados.
- Normalización de espacios y saltos de línea.
- Extracción de metadatos YAML, conservando el cuerpo normativo.

Documentos modificados por regla: {'Caracteres_Control': 9, 'Espacios_Saltos': 170}

Variación neta de caracteres por regla: {'Caracteres_Control': 0, 'Espacios_Saltos': 1008}

Las variaciones corresponden a diferencias de longitud;
no necesariamente representan contenido jurídico eliminado.

## 5. Metadatos

Cada documento incluye identificador, título, texto, secciones y metadatos.

- Fecha de publicación disponible: 170/170.
- Versiones verificadas: 0.
- Vigencia verificada: no.

El estado normalizado se establece como `unknown`.
El estado declarado por la fuente se conserva por separado en
`source_status`, sin asumir que acredita la vigencia jurídica actual.

## 6. Segmentación estructural

Se identifican encabezados de artículos y anexos mediante expresiones
regulares. El texto anterior al primer encabezado se conserva como
introducción.

- Documentos: 170.
- Secciones: 7070.
- Errores de cobertura, continuidad o unicidad detectados: 0.
- Secciones superiores a 30.000 caracteres: 44.

Los identificadores de sección incorporan el contexto del anexo
cuando este puede reconocerse mediante encabezados.

Cuando una numeración se repite dentro del mismo contexto, se
utiliza una huella SHA-256 del contenido para distinguir secciones.

Se identificaron 887 secciones con numeración ambigua.

Este procedimiento mejora la trazabilidad y garantiza identificadores
únicos en el corpus procesado, pero no asegura estabilidad absoluta
ante modificaciones del contenido ni reconstruye toda la jerarquía
jurídica interna.

## 7. Duplicados y casi-duplicados

- Método para duplicados exactos: SHA-256 del texto normalizado.
- Método de similitud: Jaccard de conjuntos de secuencias de 5 palabras.
- Pares comparados: 14365.
- Grupos de duplicados exactos: 0.
- Umbral para candidatos: 0,80.
- Candidatos encontrados: 2.

- `DNU-805-2025` / `LEY-26221`: 0.8967
- `DEC-493-2025` / `DNU-805-2025`: 0.8413

**Política:** se conservan los 170 documentos. Ningún documento se
elimina por similitud textual sin revisión jurídica.

## 8. Limitaciones

- Algunas normas contienen artículos de otras normas o numeraciones repetidas.
- La jerarquía de identificadores es parcial: identifica anexos,
  pero no todos los capítulos, subanexos o normas incorporadas.
- Los identificadores basados en hashes pueden cambiar cuando
  cambia el contenido o los límites de una sección.
- La pertenencia al último anexo detectado es una aproximación
  estructural que no implica atribución jurídica verificada.
- Los anexos pueden incluir contenido visual indicado como `[IMG]`,
  cuyo contenido no fue extraído.
- Algunas secciones son extensas y necesitarán subdivisión durante
  la etapa de chunking.
- La limpieza de espacios puede modificar el formato Markdown;
  las diferencias quedan registradas en `cleaning_examples.md`.
- No se verificó la vigencia normativa contra fuentes oficiales.
- Una similitud textual elevada no demuestra equivalencia jurídica.

## 9. Artefactos

- `documents.jsonl`: documentos normalizados y secciones.
- `manifest.json`: procedencia, selección y hashes de archivos.
- `cleaning_examples.md`: diez comparaciones antes/después.
- `dedup_report.json`: duplicados y candidatos a casi-duplicados.
- `corpus_card.md`: esta documentación.

## 10. Integridad

Hash del corpus procesado: `519330293d3b792c42325b784acc17b0495319994dcacaf90021b5f08a435a59`.
