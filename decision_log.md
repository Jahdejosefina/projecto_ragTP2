# Decision log — Proyecto RAG jurídico

Registro de decisiones técnicas, problemas encontrados, alternativas descartadas y limitaciones aceptadas. Los resultados y análisis detallados se desarrollan en el informe; este archivo documenta principalmente **qué se decidió y por qué**.


## Etapa 0 — Selección y auditoría del corpus jurídico

### 1. Elección del corpus y alcance

**Decisión:** utilizar el corpus R3 de legislación nacional argentina, obtenido del repositorio `legalize-ar` y fijado en el commit `3d2450b5c09a`. Seleccionar un subconjunto de 170 documentos relacionados con defensa del consumidor mediante las palabras clave «defensa del consumidor», «24.240» y «ley 24240».

**Justificación:** trabajar con documentos jurídicos en español, con identificadores normativos y estructura aprovechable, manteniendo un volumen compatible con las restricciones de cómputo de una GPU T4.

**Limitación:** la selección por palabras clave incluye normas de relevancia temática indirecta y no representa la totalidad de la legislación argentina.

### 2. Tamaño del corpus y necesidad de recuperación

**Resultado:** los 170 documentos contienen aproximadamente 3,12 millones de tokens, con una mediana de 6.378,5 tokens por documento y un máximo de 341.824 tokens.

**Decisión:** implementar recuperación de fragmentos relevantes en lugar de proporcionar documentos completos al generador.

**Justificación:** con Qwen3:8b y `num_ctx=8192`, el corpus equivale aproximadamente a 380 ventanas de contexto. Incluso algunos documentos individuales superan ampliamente el límite disponible.

### 3. Calidad de metadatos y estructura jurídica

**Problema:** la auditoría identificó encabezados heterogéneos, artículos citados dentro de otras normas, anexos, tablas y metadatos temporales poco confiables.

Aunque los 170 documentos presentaban campos principales completos, 159 tenían `last_updated=1900-01-01` y todos declaraban `status=in_force` sin verificación individual de vigencia.

**Decisión:** conservar estos hallazgos como restricciones de diseño para la Etapa 1. No considerar las fechas de actualización ni los estados de vigencia como evidencia jurídica confiable sin validación adicional.

**Justificación:** evitar pérdidas de estructura, identificación incorrecta de artículos y respuestas que confundan información histórica con normativa vigente.

### 4. Similitud documental y revisión manual

**Decisión:** realizar una inspección preliminar de casi-duplicados y revisar manualmente diez documentos antes de definir el procesamiento del corpus.

**Resultado:** en una muestra reproducible de 40 documentos se compararon 780 pares mediante Jaccard de 5-gramas. La similitud máxima fue 0,482 y ningún par alcanzó el umbral de 0,80.

La revisión manual detectó diferencias de formato, modificaciones y derogaciones parciales, artículos citados y tablas cuya estructura debía preservarse.

**Limitación:** la ausencia de casi-duplicados en la muestra no garantiza su ausencia en el corpus completo. Por eso se realizó una evaluación más amplia en la Etapa 1.

### 5. Conocimiento previo del modelo

**Decisión:** ejecutar cinco preguntas a libro cerrado con Qwen3:8b antes de implementar recuperación.

**Resultado:** el modelo mostró conocimientos jurídicos generales, pero también produjo respuestas incompletas e incorrectas con aparente seguridad.

**Justificación:** establecer un diagnóstico preliminar de conocimiento paramétrico y motivar la posterior comparación entre generación sin evidencia y generación fundamentada mediante RAG.

**Limitación:** cinco preguntas no permiten estimar cuánto conocimiento del corpus fue incorporado durante el preentrenamiento.

**Conclusión:** se consideró adecuado utilizar el subconjunto seleccionado para el proyecto, siempre que las etapas posteriores abordaran sus problemas de estructura, metadatos, vigencia y recuperación. La auditoría inicial fundamentó las decisiones de normalización de la Etapa 1 y el diseño de las evaluaciones posteriores.




## Etapa 1 — Preparación y estructuración del corpus jurídico

### 1. Fuente y reproducibilidad

**Decisión:** utilizar un subconjunto de normas argentinas relacionadas con defensa del consumidor del repositorio `legalize-ar`, fijando el commit `3d2450b5c09a`. Identificar cada documento mediante el campo `identifier` de origen.

**Justificación:** evitar que cambios en la fuente o en el orden de descarga alteren silenciosamente los documentos y las referencias utilizadas en etapas posteriores.

**Resultado:** 170 documentos procesados, con versión de fuente y hashes registrados en el manifiesto.

### 2. Reparación de YAML y limpieza conservadora

**Problema:** nueve encabezados YAML contenían caracteres de control. El manejo inicial de errores descartaba metadatos silenciosamente, dejando fecha de publicación en solo 161 documentos.

**Decisión:** reparar caracteres de control antes de parsear YAML y reemplazar las fallas silenciosas por excepciones explícitas. Aplicar una limpieza conservadora de espacios, saltos de línea y Unicode.

**Resultado:** 170 documentos con fecha. La regla `Espacios_Saltos` afectó los 170 documentos (reducción neta de 1.008 caracteres); `Caracteres_Control` corrigió nueve y `NFC_Acentos` no produjo cambios. Se conservaron ejemplos antes/después.

**Justificación:** preservar el contenido jurídico sin aceptar pérdida de metadatos inadvertida.

### 3. Segmentación jurídica e identificadores de sección

**Problema:** los artículos y anexos tenían formatos heterogéneos; algunos encabezados no se detectaban y había colisiones de `section_id` entre artículos del texto principal y anexos.

**Decisión:** ampliar las reglas de detección de encabezados y generar IDs con contexto estructural, por ejemplo `LEY-26994#ART-1` y `LEY-26994#ANEXO-I/ART-1`. Para colisiones persistentes dentro del mismo contexto, usar una huella SHA-256 del contenido en lugar de sufijos secuenciales.

**Resultado:** 7.070 secciones, cero errores estructurales y resolución de 887 casos con numeración ambigua. Se revisaron documentos problemáticos como `LEY-26522`, `DEC-660-1996` y `DEC-50-2019`.

**Limitación:** la jerarquía reconocida es parcial y los IDs basados en contenido pueden cambiar si cambia el texto.

### 4. Secciones extensas y casi-duplicados

**Decisión:** no dividir arbitrariamente durante la ingesta las 44 secciones de más de 30.000 caracteres; dejar el fraccionamiento para el *chunking* de la Etapa 3, conservando el vínculo con la sección original.

Se buscaron duplicados exactos por SHA-256 y casi-duplicados por Jaccard de 5-gramas (umbral 0,80) en 14.365 pares. No hubo duplicados exactos y aparecieron dos pares candidatos: `DNU-805-2025`/`LEY-26221` (0,8967) y `DEC-493-2025`/`DNU-805-2025` (0,8413).

**Decisión:** conservar esos documentos: similitud textual no implica equivalencia jurídica. Sus solapamientos deben considerarse al construir y evaluar las referencias *gold*.

### 5. Vigencia, validación y congelamiento

**Decisión:** mantener el estado normativo como `unknown`, porque no se verificó oficialmente la vigencia individual de las normas. No utilizar este dato como filtro confiable de recuperación.

**Resultado:** `documents.jsonl` superó la validación estructural (170 documentos; 7.070 secciones; cero errores). Se fijó como corpus de las etapas siguientes y se conservaron `manifest.json`, `corpus_card.md`, `cleaning_examples.md` y `dedup_report.json`.

**Limitaciones aceptadas:** estructura parcial de anexos, imágenes no extraídas (`[IMG]`), secciones largas, casi-duplicados y vigencia no verificada.

---

## Etapa 2 — Construcción, revisión y congelamiento del conjunto de evaluación

### 1. Revisión de preguntas y referencias *gold*

**Decisión:** revisar los 30 ítems individuales contra el corpus, mejorando redacciones ambiguas, claves alternativas y diversidad de preguntas de metadatos e identificadores.

**Corrección relevante:** en `q004` se eliminó la referencia amplia `LEY-26994#ANEXO-II/ART-285`, conservando `LEY-24240#ART-8`. Se verificó que las referencias *gold* existieran y que los identificadores ficticios de los tres casos `out_of_corpus` no aparecieran en el corpus.

### 2. Diálogos y escenarios de memoria

**Decisión:** revisar 32 turnos conversacionales y 27 sondas de memoria, incluyendo reescrituras autónomas, dependencias entre turnos y consistencia de las respuestas esperadas.

En `d008:t2` se retiró la misma referencia amplia descartada en `q004`. Se rediseñó `m003` para comprobar actualizaciones entre sesiones: precio inicial de $64.000, corrección a $69.000, envío de $2.500 y total de $71.500.

### 3. Congelamiento del benchmark

**Decisión:** congelar el conjunto mediante `eval/FROZEN.json` el **26/10/2026**, después de la revisión documentada por Alexander Melnikov.

**Justificación:** impedir cambios oportunistas de preguntas, claves y referencias motivados por los resultados de los experimentos posteriores. El diagnóstico preliminar con BM25 se utilizó para detectar ítems dudosos, no para ajustar el conjunto a un recuperador.

### 4. Verificación complementaria y advertencia de auditoría

**Problema:** durante la Etapa 3, el notebook advirtió que las 23 preguntas de `test` mantenían anotaciones internas de revisión humana pendiente, aunque existía documentación de auditoría previa al congelamiento.

**Decisión:** el **29/10/2026** se realizó una comprobación complementaria de los 30 ítems individuales, con apoyo de IA para organizar el contraste y validación humana de los resultados. No se identificaron errores de contenido que justificaran cambiar el benchmark; se registraron observaciones menores sobre expresiones numéricas en `q002` y `q008`.

Se conservaron sin modificaciones `single_turn.jsonl`, `dialogues.jsonl`, `scenarios.jsonl` y `FROZEN.json`, explicando la discrepancia de anotaciones en el notebook.

### 5. Evidencia y limitaciones

La revisión quedó documentada en `eval/auditoria_preguntas.md`, `eval/auditoria_dialogos.md`, `eval/auditoria_escenarios.md` y `eval/revision_manual.csv`.

**Limitaciones aceptadas:** algunos diálogos reutilizan hechos de preguntas individuales, `m001` y `m002` tienen estructuras similares, y la consistencia de las respuestas con el corpus no equivale a verificar la vigencia jurídica oficial. La validación automática no sustituye la revisión humana.

---

## Etapa 3 — Recuperación sobre el corpus jurídico

### 1. Alcance y construcción del índice

**Decisión:** comparar tres brazos bien definidos —BM25 léxico, BGE-M3 denso e híbrido RRF— en lugar de ampliar el experimento con más técnicas y comprometer el tiempo de las etapas posteriores.

Se utilizaron los 170 documentos y sus 7.070 secciones; el *chunking* generó **13.630 fragmentos**, conservando vínculos con `doc_id` y `section_id`. Se fijó un presupuesto común de **2.500 tokens entregados al generador** y se documentaron los parámetros en manifiestos.

### 2. Métricas y criterio de selección

**Decisión:** evaluar no solo `doc_hit@5`, sino también `section_hit@5`, entrega efectiva de la sección y presencia de la respuesta en el contexto; registrar latencia, tokens y comparaciones pareadas con incertidumbre estadística.

**Justificación:** encontrar una norma correcta no asegura entregar el artículo que responde la pregunta. La elección del recuperador debía realizarse exclusivamente en `dev`, no mirando `test`.

### 3. Elección de BM25 en dev

En `dev` hubo siete preguntas (seis respondibles). Los tres brazos lograron 100 % en documento, sección y respuesta entregada para las respondibles.

Una regla inicial favorecía a BGE-M3 por una diferencia mínima de latencia: BM25 ≈0,620 s, BGE-M3 ≈0,619 s y RRF ≈0,661 s.

**Decisión:** priorizar la entrega de sección y, ante empate, elegir el recuperador más simple. Se seleccionó **BM25**, evitando el costo de embeddings por consulta sin una mejora demostrada. La selección quedó registrada en `stage3_selected_retriever.json`.

**Limitación:** seis preguntas respondibles no alcanzan para demostrar equivalencia general entre recuperadores.

### 4. Resultados de test sin cambiar la selección

La evaluación final utilizó 23 preguntas, 21 respondibles. BM25 obtuvo `doc_hit@5` de 95,2 %, `section_hit@5` de 85,7 % y `answer_delivered` de 95,2 %. BGE-M3 y RRF alcanzaron 100 %, 90,5 % y 95,2 %, respectivamente.

**Decisión:** conservar BM25. Las diferencias de documento y sección no aportaron evidencia estadística concluyente de mejora, y la tasa de respuesta entregada fue igual en los tres brazos. No se reoptimizó a partir de `test`.

### 5. Problemas, exclusiones y límites

Se registró una advertencia del tokenizer sobre una sección original de 14.990 tokens frente a un máximo de 512; el índice final, sin embargo, tenía fragmentos con máximo registrado de 320 tokens. La representación densa incorporó contexto adicional respecto de BM25, por lo que la comparación no aísla únicamente el tipo de algoritmo.

**Decisión:** no incorporar reranking, expansión a padre, filtros por metadatos ni HyDE como brazos adicionales. Un diagnóstico de longitud para una ventana de 512 tokens no se interpretó como evaluación de un reranker.

**Justificación:** controlar alcance y cómputo; además, filtrar por vigencia sin metadatos verificados podría eliminar evidencia relevante.

**Limitaciones aceptadas:** muestra pequeña, intervalos amplios, diferencias de representación y advertencia de revisión humana ya explicada en la Etapa 2.

---

## Etapa 4 — Generación de respuestas fundamentadas

### 1. Brazos de evaluación y recuperación seleccionada

**Decisión:** comparar libro cerrado, BM25 + LLM y oráculo + LLM sobre las mismas preguntas. Se reutilizó el BM25 elegido en `dev` durante la Etapa 3, sin cambiarlo por resultados de `test`.

**Justificación:** medir el valor de aportar evidencia jurídica y separar fallas de recuperación de fallas de generación.

### 2. Prompt, salida estructurada y presupuesto

**Decisión:** ensamblar instrucciones, pasajes marcados `[doc_id · section_id]` y pregunta al final. Los pasajes respetan un máximo de 2.500 tokens; si uno no entra, se prueba el siguiente. Se utilizó Qwen3:8b, `num_ctx=8192`, `num_predict=700`, temperatura 0, semilla fija y margen de 64 tokens.

Se adoptó una salida Pydantic con `analysis`, `answer`, `can_answer`, `citations` y `verdict`. La abstención se mide mediante `can_answer` y las citas se contrastan contra los pasajes realmente entregados.

**Justificación:** disponer de respuestas evaluables y evitar exceder la ventana efectiva del prompt (7.428 tokens). Una prueba de desbordamiento confirmó que, sin control, Ollama puede truncar el contexto silenciosamente.

### 3. Ajustes al corrector durante dev

**Problema:** la primera versión de la corrección automática marcaba respuestas válidas como incorrectas por variaciones como «de»/«del», o por contradicciones entre el texto de sí/no y el campo `verdict`.

**Decisión:** normalizar esas variantes y tomar el veredicto sí/no de la primera palabra de la respuesta. Los cambios se definieron en `dev`, sin alterar las preguntas ni referencias congeladas; la comprobación posterior mostró métricas idénticas en `test`.

**Limitación:** la coincidencia de claves puede seguir subestimando algunas paráfrasis válidas.

### 4. Integración con Etapa 3 y fidelidad del contexto

**Problema:** la ejecución inicialmente buscaba el split `dev` aunque la corrida disponible era `test`, y luego no encontraba el índice porque sus archivos pesados estaban en Drive y no en el directorio temporal de Colab.

**Decisión:** usar los resultados de `test` ya generados y copiar el índice correspondiente desde Drive, sin reconstruir embeddings.

**Limitación:** la Etapa 4 reconstruyó pasajes con marcadores más compactos. Aunque conservó BM25 y los 2.500 tokens de presupuesto, los contextos no fueron idénticos a los de la Etapa 3.

### 5. Errores observados y decisiones de evaluación

En `test` (23 preguntas), libro cerrado obtuvo 2/23 respuestas correctas, BM25 + LLM 21/23 y oráculo + LLM 23/23. Las dos preguntas fuera del corpus recibieron abstenciones correctas en los tres brazos.

**q022:** la sección adecuada llegó al prompt, pero el modelo confundió la Ley 21.526 con la Ley 25.093 (error de generación y posible ambigüedad del ítem). **q023:** llegó el documento correcto, pero no el artículo con la respuesta (problema de entrega de evidencia). No se modificó el benchmark congelado.

También se detectó una cita a un pasaje no entregado y un acierto sustentado en evidencia alternativa no incluida en el *gold* exacto.

**Decisión:** analizar por separado exactitud, evidencia entregada y fidelidad de citas, sin atribuir automáticamente todos los errores al generador.

### 6. Alcance y limitaciones aceptadas

**Decisión:** no ejecutar un experimento específico de posición de pasajes (*Lost in the Middle*) y priorizar las comparaciones principales y las pruebas de presupuesto. Tres repeticiones con temperatura cero no produjeron texto idéntico, pero sí conservaron la clasificación correcta/incorrecta.

**Limitaciones:** solo 23 preguntas de `test`; incertidumbre para diferencias pequeñas, sensibilidad de la corrección a paráfrasis, posibles referencias *gold* incompletas, diferencias en el ensamblado respecto de Etapa 3 y variabilidad textual del modelo.

**Conclusión:** recuperar evidencia mejora sustancialmente la exactitud, pero ni la presencia del documento correcto ni la entrega de la sección *gold* garantizan una respuesta y una cita correctas.



## Etapa 5 — Recuperación conversacional y presupuesto de historial

### 1. Estrategias de consulta y reutilización del recuperador

**Decisión:** comparar `last`, `full_history`, `llm_rewrite` y `oracle`, reutilizando BM25 de la Etapa 3 y los diálogos y respuestas guionadas congelados en la Etapa 2.

**Justificación:** aislar el efecto de la formulación de la consulta sin introducir diferencias en la conversación previa ni cambiar el recuperador a partir de resultados de `test`.

### 2. Elección del prompt de reescritura en dev

**Problema:** las primeras versiones del reescritor no siempre resolvían referencias dependientes del historial, conservando expresiones como «me lo reparan» o «volviendo a la publicidad educativa».

**Alternativas:** se evaluaron tres versiones del prompt: v1 como implementación inicial, v2 con mejoras para resolver referencias ambiguas y v3 con instrucciones explícitas para sustituir anáforas y elipsis, producir consultas autónomas y evitar respuestas o detalles inventados.

**Evidencia:** en `dev` (7 turnos respondibles), se obtuvieron los siguientes resultados:

| Métrica | v1 | v2 | v3 |
|---|---:|---:|---:|
| `doc_hit@5` | 57,1 % | 85,7 % | 71,4 % |
| `section_hit@5` | 57,1 % | 71,4 % | 71,4 % |

**Decisión:** seleccionar el prompt **v3**. Aunque v2 obtuvo el mejor resultado de recuperación de documentos, v3 mantuvo su rendimiento a nivel de sección y produjo consultas más autónomas en la revisión cualitativa. Se priorizó la resolución de referencias conversacionales sin atribuirle una mejora cuantitativa inexistente. La muestra reducida de `dev` limita la interpretación de las diferencias.

**Resultado final:** en `test` (23 turnos respondibles), v3 alcanzó `doc_hit@5=95,7 %` y `section_hit@5=95,7 %`, igualando las métricas agregadas del oráculo. `last` obtuvo 73,9 % en ambas métricas y `full_history` alcanzó 91,3 % en documento y 73,9 % en sección. No se modificó el prompt después de evaluar `test`.

### 3. Políticas de historial y presupuesto compartido

**Decisión:** comparar `full`, `recent` (hasta cuatro mensajes) y `summary` (resumen acumulativo más mensajes recientes), con un presupuesto compartido de **500 tokens** para pasajes e historial: 80/20, 50/50 y 30/70. Se mantuvo Qwen3:8b con `num_ctx=8192` y la consulta reescrita mediante v3.

**Justificación:** los diálogos cortos requieren un límite explícito para hacer observable el conflicto entre evidencia documental y contexto conversacional. Los 500 tokens no representan la ventana total del modelo.

**Evidencia en test:** con 80/20, `recent` y `summary` lograron 19/24 respuestas correctas (**79,2 %**); `full` obtuvo 12/17 (**70,6 %** entre turnos viables), con siete turnos inviables por presupuesto. Con 50/50, las tres políticas obtuvieron 16/24; con 30/70, `full` y `summary` lograron 4/24 y `recent` 3/24. Se calcularon intervalos mediante bootstrap agrupado por diálogo.

**Limitación:** la exactitud de `full` con 80/20 excluye los turnos inviables y, por lo tanto, no es directamente comparable con la de las políticas que completaron los 24 turnos.

### 4. Recuerdo temprano, auditorías y elección interpretativa

**Decisión:** complementar la exactitud jurídica con sondas diagnósticas de recuerdo temprano y revisión de reescrituras y resúmenes, sin modificar el benchmark congelado.

**Resultado:** en seis sondas de `test`, `summary` recordó 6/6 detalles en los tres repartos, mientras que `recent` recordó 1/6. La política `full` recordó 6/6 con 50/50 y 30/70, pero fue inviable con 80/20.

Se inspeccionaron veinte reescrituras (ocho de `dev` y doce de `test`): las consultas revisadas fueron autónomas y no contenían respuestas explícitas. En los ejemplos de resúmenes inspeccionados no se detectaron contradicciones manifiestas, aunque no se realizó una auditoría exhaustiva hecho por hecho.

**Decisión:** destacar `summary` con reparto **80/20** como compromiso

---

## Etapa 6 — Memoria entre sesiones

### 1. Alcance, loop y brazos

**Decisión:** reutilizar el loop de la Etapa 5 (BM25 de la Etapa 3 → ensamblador de `grounded_stage4` → `GroundedAnswer`) y agregar un espacio de memoria en el prompt. Se compararon seis brazos sobre las mismas sondas de `eval/scenarios.jsonl`:

- sin memoria (piso);
- reproducción completa de las sesiones anteriores (línea de base);
- almacén de memoria;
- almacén + filtro por metadatos tomados de la memoria;
- reproducción con el 50 % y el 25 % del historial.

La consulta al corpus fue la pregunta de la sonda, sin reescritura y la misma en todos los brazos.

**Justificación:** cada sonda ocurre en una sesión nueva, sin historial conversacional que reescribir. Mantener igual la consulta aísla el efecto de la memoria o del historial. No se modificaron `grounded_stage4.py`, el índice de la Etapa 3 ni el benchmark congelado.

### 2. Presupuestos y régimen

**Decisión:**

- **Generación:** Qwen3:8b, `num_ctx=8192`, `num_predict=700`, temperatura 0 y margen de 64 tokens (tope del prompt: 7.428 tokens), como en las Etapas 4 y 5.
- **Presupuestos:** 1.500 tokens de pasajes en todos los brazos; espacio de memoria de hasta 600 tokens con un máximo de 6 recuerdos; historial de reproducción de hasta 3.000 tokens.
- **Embedder:** BGE-M3, el mismo de la Etapa 3, con la revisión fijada en `stage3_selected_retriever.json`.

**Régimen declarado:** el historial más largo ocupa 460 tokens; la reproducción completa dejaría de entrar a partir de unas 21 sesiones de este tamaño. Todas las comparaciones con la reproducción completa son, por lo tanto, en el régimen en que el historial **entra**.

**Decisión complementaria:** para observar qué ocurre cuando no entra, se agregaron brazos con presupuesto fijo igual al 50 % y al 25 % del historial completo de cada escenario. Se descartan las sesiones más antiguas, completas.

### 3. Camino de escritura y lectura

**Decisión:**

- **Escritura:** una extracción de hechos por sesión con schema (`Extraction`), seguida de una decisión ADD / UPDATE / NOOP / INVALIDATE con otro schema (`WriteDecision`). El modelo decide solo cuando existe un recuerdo vigente parecido (mismo atributo o similitud ≥ 0,55); si no lo hay, el hecho se agrega sin llamada al LLM.
- **Invalidar, no borrar:** un UPDATE cierra el registro anterior con `valid_to` y crea uno nuevo con `supersedes`. Del modelo se guarda solo el texto de cada hecho, nunca su campo `analysis`, que queda únicamente en el log de operaciones.
- **Lectura:** suma de relevancia (BGE-M3), recencia (0,995 por hora sobre fechas simuladas, con la sonda 24 h después de la sesión indicada) e importancia, normalizadas con min-max. Los registros invalidados pueden recuperarse, marcados como «YA NO VIGENTE» con su intervalo de validez.

**Justificación:** permitir preguntas temporales («¿qué había dicho antes?»), evitar guardar hipótesis como hechos y no usar el reloj real, que en una reproducción guionada es casi constante.

### 4. Ajustes del camino de escritura durante dev

**Problema:**

- **Con `qwen3:1.7b` (smoke):** el extractor mezcló varios datos en un solo registro, hizo un UPDATE donde correspondía un ADD (el envío reemplazó al precio) y omitió el canal de contacto inicial.
- **Con Qwen3:8b en dev:** el extractor sí extrajo la academia de la compra, pero el decisor la marcó NOOP contra el precio recién guardado en la misma sesión, y el dato se perdió. Lo mismo ocurrió con la preferencia de formato.

**Decisión:** antes de evaluar `test`, y sin tocar el benchmark:

1. comparar los hechos de una misma extracción solo con recuerdos de sesiones anteriores o del mismo atributo;
2. permitir NOOP solo si el recuerdo guardado dice exactamente lo mismo;
3. agregar al extractor dos reglas generales: no omitir nombres, importes, fechas ni identificadores, y guardar un hecho por atributo.

También se corrigió la auditoría automática, que contaba como filtración un `analysis` que solo citaba el hecho evaluado.

**Resultado:** en `dev`, el brazo de almacén pasó de 7/9 a 8/9 y la escritura bajó de 10 a 6 llamadas al LLM. La única sonda que siguió fallando recibió los dos recuerdos correctos (120.000 y 3.000) y respondió «150.000»: es un error de generación, no de memoria.

### 5. Resultados de test

**Resultado:** en `test` (escenarios `m002` y `m003`, 18 sondas):

- Reproducción completa, almacén y almacén + filtro: **18/18**, con los dos pares de control p8+p9 correctos.
- Sin memoria: **4/18**. Las dos abstenciones y las dos sondas que se responden con el corpus; en algunos casos inventó datos del usuario en lugar de abstenerse.
- Reproducción al 50 %: **14/18**, perdiendo la primera sesión.
- Reproducción al 25 %: **5/18**.

**Costo:** el almacén usó 2.193 tokens de prompt por sonda frente a 2.256 de la reproducción completa (296 de memoria contra 340 de historial). La escritura costó 14 llamadas y 7.375 tokens de prompt en 6 sesiones. El almacén + filtro usó 954 tokens por sonda con la misma exactitud.

**Decisión interpretativa:** en el régimen en que el historial entra, no se reproduce ninguna de las dos mitades de la predicción de Mem0. El almacén no pierde exactitud (empata 18/18) y tampoco gana en costo: ahorra unos 60 tokens por sonda, pero su escritura necesitaría más de 100 sondas para amortizarse en tokens. La memoria se justifica cuando el historial deja de entrar: con el 25 % del presupuesto, la reproducción cae al nivel de no tener memoria y el almacén mantiene 18/18. El mayor ahorro de tokens provino del filtro, no del reemplazo del historial.

### 6. Filtro por memoria

**Decisión:** derivar filtros de los recuerdos vigentes (`doc_id` de la norma elegida y fecha de publicación comparada con `metadata.date`) y aplicarlos a todas las sondas del brazo con filtro, porque el sistema no sabe de antemano cuáles necesitan el corpus.

**Resultado:** en las dos sondas que requieren el corpus, la sección *gold* llegó en primer lugar con y sin filtro: el filtro no mejoró ni perjudicó la recuperación. En `m003`, la fecha 2019-12-20 coincide con dos documentos (`LEY-27521` y `DEC-50-2019`), por lo que el filtro por `doc_id` resulta más preciso. En las sondas sobre datos del usuario, el filtro dejó la consulta sin pasajes, que es la fuente del ahorro de tokens.

**Limitación:** la fecha de publicación no es fecha de vigencia y no permite seleccionar versiones de normas. Si el usuario preguntara por algo ausente de su norma elegida, el filtro eliminaría justo la evidencia que permitiría responder «eso no está en tu norma»; este caso no está cubierto por las sondas.

### 7. Auditoría del almacén

**Resultado:** en `test`, la auditoría automática no detectó problemas en los 22 registros (17 vigentes): ningún `<think>`, ninguna hipótesis, ningún texto de `analysis`, ningún número ausente de la transcripción y 0 filtraciones de razonamiento.

La lectura manual contra los guiones encontró 20/22 registros correctos y los siguientes problemas:

- `m003-s3-02` atribuye al usuario un total de 71.500 que calculó el asistente: es un dato derivado que quedaría desactualizado si el precio volviera a corregirse.
- La preferencia de párrafo de `m003` quedó restringida a «respuestas sobre normativa».
- El canal de contacto quedó clasificado como memoria procedimental en lugar de semántica.
- En `m002` se omitió que el videojuego era «en formato físico».

Los cinco registros invalidados coinciden exactamente con los cambios de los guiones.

**Decisión:** no corregir registros a mano ni volver a ajustar el extractor después de `test`. Los problemas se reportan como hallazgos.

### 8. Integración con Colab y Drive

**Problema:** el índice BM25 de la Etapa 3 no estaba en `artifacts/` del entorno ni en la ruta esperada de Drive. Además, `artifacts/` existe en el repositorio como carpeta común, no como enlace a Drive.

**Decisión:**

- buscar el índice en `artifacts/`, en `MyDrive/projecto_rag/artifacts/full/index/` y en cualquier carpeta de MyDrive, con la opción de fijar `STAGE3_INDEX_DIR`;
- leer la elección de la Etapa 3 desde Drive cuando esté disponible;
- copiar al final los resultados y el almacén a Drive.

No se reconstruyó el índice ni se cambió el recuperador elegido.

### 9. Alcance y limitaciones aceptadas

**Limitaciones:**

- **Efecto techo:** tres brazos obtienen 18/18, por lo que no pueden distinguirse en el régimen en que el historial entra.
- **Las sondas p7 no ponen a prueba la memoria:** la pregunta basta para recuperar la norma.
- **Los ajustes de escritura se decidieron sobre un solo escenario de `dev`.**
- **La auditoría manual de 22 registros no escala.**
- **No se compararon variantes del puntaje de lectura** (sin recencia o sin importancia) ni otros embedders.

**Conclusión:** con historiales cortos, reproducir todo es tan exacto como el almacén y más barato. La memoria escrita por el propio sistema se justifica cuando el historial deja de entrar en la ventana, y su riesgo principal no son las hipótesis guardadas como hechos, sino omisiones, datos mal atribuidos y actualizaciones equivocadas, que solo se detectan leyendo los registros.

---

## Etapa 7a — Evaluación de respuestas con jueces LLM

### 1. Alcance y reutilización de respuestas congeladas

**Decisión:** evaluar la corrección semántica de las respuestas ya generadas en la Etapa 5B, sin volver a ejecutar el RAG. Se compararon dos jueces abiertos, `qwen3:8b` y `llama3.1:8b`, usando la misma entrada para ambos y dos versiones de la rúbrica (`v1` y `v2`).

**Justificación:** aislar la variación producida por el juez y su rúbrica, sin introducir cambios en recuperación, generación o respuestas de referencia.

**Resultado:** de 288 filas originales, 277 fueron elegibles por juez (68 de `dev` y 209 de `test`). Las 11 filas `not_feasible` (4 de `dev` y 7 de `test`) se documentaron por separado, sin tratarlas como respuestas incorrectas.

### 2. Configuración y alcance del juicio

**Decisión:** utilizar temperatura 0, semilla 42, `think=False`, contexto de 8.192 tokens y reserva de salida de 512, con salida JSON estructurada que incluyera una justificación breve y el veredicto `correcto`, `incorrecto` o `incierto`.

Cada juez recibió pregunta original, reformulación autocontenida, tipo de ítem, claves, referencia y respuesta del sistema. Se excluyeron deliberadamente identidad del generador, calificación automática, política conversacional, presupuestos y pasajes recuperados.

**Limitación:** esta evaluación mide acuerdo sobre corrección respecto de la referencia guardada; **no** mide fidelidad a los pasajes ni validez de citas.

### 3. Auditoría humana y calibración en dev

**Decisión:** utilizar 30 filas anotadas por Alexander Melnikov en `dev` (20 correctas y 10 incorrectas), correspondientes a 11 prompts completos distintos, para diagnosticar los errores de la rúbrica inicial.

**Problema:** la versión `v1` rechazaba algunas respuestas semánticamente equivalentes o trataba inadecuadamente omisiones y abstenciones. Ambos jueces alcanzaron 18/30 (**60,0 %**) de acuerdo con las marcas humanas.

**Decisión:** redactar `v2` con reglas más explícitas para diferenciar la respuesta evaluada de la referencia, aceptar paráfrasis y omisiones no esenciales, y juzgar abstenciones, contradicciones y agregados. Se mantuvieron los mismos modelos y parámetros.

**Resultado en dev:** Qwen pasó de 18/30 a 21/30 (**70,0 %**), y Llama de 18/30 a 20/30 (**66,7 %**). Sin embargo, Llama `v2` marcó las 30 filas como correctas: su acuerdo coincidió con el comparador trivial «siempre correcto».

**Decisión metodológica:** fijar `v2` antes de revisar las etiquetas de `test` y no continuar ajustando los jueces en función de esa partición.

### 4. Auditoría de test y comparación entre versiones

**Decisión:** mantener una muestra de auditoría de `test` de 42 filas (23 correctas y 19 incorrectas). Se mostraron 26 comparaciones, correspondientes a 27 prompts completos distintos, y las repeticiones exactas compartieron veredicto.

**Resultados de acuerdo con las marcas humanas:**

| Juez | `dev` v1 | `dev` v2 | `test` v1 | `test` v2 |
|---|---:|---:|---:|---:|
| `qwen3:8b` | 18/30 (60,0 %) | 21/30 (70,0 %) | 38/42 (90,5 %) | 33/42 (78,6 %) |
| `llama3.1:8b` | 18/30 (60,0 %) | 20/30 (66,7 %) | 24/42 (57,1 %) | 20/42 (47,6 %) |

**Hallazgo:** el aumento del acuerdo observado en `dev` no se sostuvo en `test`: Qwen perdió 11,9 puntos porcentuales y Llama 9,5. Llama `v2` quedó incluso por debajo del comparador «siempre correcto» en `test` (54,8 %).

**Decisión:** reportar ambas versiones y no seleccionar retroactivamente `v1` por su mejor puntaje en `test`. Esa selección requeriría otra muestra independiente para validarse.

### 5. Comparadores y diagnóstico de errores

**Decisión:** comparar los jueces tanto con las marcas humanas auditadas como con la métrica automática de contención de claves para todas las filas elegibles. Esta última se usó como **comparador**, no como verdad humana.

**Evidencia en test:** Qwen `v2` coincidió con las 19 filas humanas incorrectas, pero rechazó 9 de las 23 correctas. Llama `v2` coincidió solo con 5 de las 19 incorrectas, aceptó indebidamente 14 y rechazó 8 correctas.

**Problemas observados:** Qwen penalizó algunas fechas semánticamente equivalentes por su formato y ambos jueces rechazaron una abstención válida representada por cinco filas. Llama también aceptó abstenciones indebidas pese a que la referencia contenía el dato solicitado.

**Conclusión parcial:** los jueces tienen errores sistemáticos diferentes; el acuerdo con contención automática no sustituye la auditoría humana.

### 6. Anotación discordante y dependencia entre filas

**Problema:** en el caso 12 de `test`, la marca humana fue `correcto`, aunque la referencia y la respuesta daban fechas distintas (15 de julio de 2005 frente a 1 de junio de 2005). Los cuatro jueces rechazaron la respuesta.

**Decisión:** conservar la etiqueta original para mantener trazabilidad y señalar la discrepancia, en lugar de corregirla silenciosamente. Como análisis complementario, excluir ese caso produjo en `test` 38/41 para Qwen `v1`, 33/41 para Qwen `v2`, 24/41 para Llama `v1` y 20/41 para Llama `v2`; la conclusión general no cambió.

**Limitaciones aceptadas:** las 42 filas auditadas contienen repeticiones y paráfrasis dependientes, por lo que no representan 42 observaciones independientes; los acuerdos son descriptivos, no estimaciones de precisión para todo el conjunto. La auditoría humana fue asistida y varias síntesis de motivos fueron redactadas por el asistente; no deben atribuirse como justificaciones escritas literalmente por el anotador.

### 7. Reproducibilidad, integración y decisión final

**Decisión:** conservar los notebooks `07_second_read.ipynb` (`v1`), `07_calibrar_dev.ipynb` (calibración) y `07_evaluar_test.ipynb` (`v2` fijada), junto con las rúbricas, auditorías, manifiestos, logs y resultados de la corrida `stage7a_frozen_v2_efc4f9398eda`.

**Resultado:** se generaron 1.108 registros comparados (277 filas × 2 modelos × 2 versiones), además de reportes de acuerdo y matrices por partición. Las decisiones de calibración se registraron en `decision_calibracion_dev.json` y los resultados agregados en `reporte_etapa7a.md` y `reporte_etapa7a.json`.

**Decisión final:** conservar `v2` como variante calibrada y congelada para el diagnóstico, sin nuevos ajustes sobre `test`, pero **no aprobar a ninguno de los dos jueces como corrector autónomo**. La Etapa 7b se evaluará por separado.

---

## Etapa 7b — Reimplementación del loop con LangGraph

### 1. Alcance y elección del framework

**Decisión:** utilizar LangGraph para reimplementar la **orquestación y la persistencia durante la ejecución** del loop de memoria entre sesiones de la Etapa 6, que reutiliza el recuperador y ensamblador de las Etapas 3–5. No reemplazar los algoritmos de extracción, escritura, recuperación y evaluación de memorias desarrollados por el grupo.

**Justificación:** aislar el aporte del framework y evitar atribuirle mejoras derivadas de cambiar simultáneamente el recuperador, la política de memoria o el generador.

### 2. Correspondencia de componentes y persistencia

**Decisión:** organizar el flujo mediante los nodos `write`, `prepare` y `answer` de LangGraph. Utilizar `InMemorySaver` para checkpoints por hilo e `InMemoryStore` para compartir registros de memoria entre hilos del mismo escenario, manteniendo separados los escenarios.

Se reutilizaron las funciones originales `write_session`, `read_memories`, `memory_filter`, `build_probe_prompt` y `score_probe`, los esquemas y las decisiones ADD/UPDATE/NOOP/INVALIDATE. Cada sonda se ejecutó como hilo nuevo y consultó los recuerdos escritos por las sesiones previas correspondientes.

**Limitación:** `InMemorySaver` e `InMemoryStore` no constituyen persistencia durable entre reinicios de Colab. El framework tampoco decidió qué hechos guardar ni cuándo resumir: esas políticas siguieron siendo las del sistema original. No se incorporó un resumen automático.

### 3. Protocolo de comparación

**Decisión:** mantener el corpus y las sondas congelados, BM25 de la Etapa 3, BGE-M3 para recuperación de memoria y Qwen3:8B con `num_ctx=8192`, `num_predict=700`, temperatura 0 y `think=False`. Conservar los presupuestos de 1.500 tokens para pasajes, 600 para memoria y hasta seis recuerdos. Evaluar los brazos `memory` y `memory_filter` sobre las 18 sondas de test de los escenarios `m002` y `m003`.

Se realizó primero una prueba de funcionamiento en `dev` con Qwen3:1.7B. Para el resultado final se empleó Qwen3:8B en GPU T4 y se compararon 36 pares por `(item_id, arm)` con la corrida original de la Etapa 6, verificando la identidad del índice y la compatibilidad de los prompts.

**Justificación:** distinguir cambios en el flujo de control de cambios en el modelo, evidencia disponible, memoria seleccionada o límites de contexto.

### 4. Resultados de test y consumo de tokens

**Resultado:** LangGraph obtuvo **18/18 respuestas correctas** con `memory` y **18/18** con `memory_filter`, exactamente igual que la implementación propia. La evidencia documental entregada y los IDs de memoria seleccionados coincidieron en **18/18 sondas por brazo**.

| Métrica | `memory` | `memory_filter` |
|---|---:|---:|
| Aciertos: manual / LangGraph | 18/18 · 18/18 | 18/18 · 18/18 |
| Pasajes entregados idénticos | 18/18 | 18/18 |
| IDs de recuerdos idénticos | 18/18 | 18/18 |
| Texto de respuesta idéntico | 14/18 | 16/18 |
| Diferencia media de tokens de prompt (LangGraph − manual) | 0,00 | 0,00 |
| Diferencia media de tokens de salida (LangGraph − manual) | +0,44 | +2,56 |

**Interpretación:** las discrepancias textuales no modificaron la corrección y no se asociaron con cambios en la evidencia entregada ni en la memoria recuperada. El consumo registrado de tokens de **prompt de las respuestas a las sondas** fue idéntico. Las diferencias medias en tokens de salida fueron pequeñas. Estos valores **no miden por sí solos el costo total**, ya que también deben considerarse las llamadas de extracción y actualización de memoria y el costo computacional de la orquestación.

### 5. Decisiones que LangGraph no tomó y conclusión

**Hallazgo:** LangGraph proporcionó estructura de grafo, separación de hilos, checkpoints y un store compartido. Sin embargo, el grupo siguió definiendo la escritura de hechos, actualización e invalidación de recuerdos, selección de memoria, filtro documental, ensamblado del prompt, ventana de contexto y criterio de evaluación.

**Decisión final:** conservar la reimplementación como demostración de **paridad funcional** y reproducibilidad de la orquestación, sin afirmar una mejora de exactitud ni un ahorro de tokens atribuible al framework. En este experimento, la ventaja observada de LangGraph fue principalmente arquitectónica; evaluar políticas automáticas de memoria o almacenamiento durable requeriría otro experimento.

**Evidencia:** `07_framework_langgraph.ipynb`, `run_spec.json`, `framework_rows.jsonl`, `write_stats.json`, `paired_comparison.csv` y `paired_summary.json`, correspondientes a la corrida `stage7b_langgraph_b326f7f25e64154f`.
