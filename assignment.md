# Proyecto · Retrieval & Memory Lab

<!-- ---------------------------------------------------------------------------
     ENCABEZADO POR INSTANCIA. Editá las dos líneas de abajo al usar esto en
     otro curso o cuatrimestre. Valores repetidos en otros lugares que hay que
     actualizar junto con ellas: el tamaño de los grupos en §6; el plazo de tres
     semanas en el ítem del disco de Colab de §6; cada versión fijada en
     corpora.md y sus gemelas en 00_corpus_audit.py (PO_COMMITS, ARCHIVE_SHA256
     y su fecha de descarga); las versiones fijadas para coincidir con Colab en
     requirements.txt, y requirements-extras.txt, que se resuelve contra ellas;
     llm.OLLAMA_VERSION y llm.KNOWN_DIGESTS, y las mediciones fechadas del
     docstring de llm.py; la línea del curso en el README. El texto supone que el
     curso construyó un pipeline de RAG antes de este proyecto ("el pipeline que
     construimos para RAG", §0 y Etapas 0-3, y una oración en la entrada de
     legalize-ar de corpora.md); en un curso donde no fue así, apuntá esas
     oraciones a tu propio material. Todo lo demás se sostiene solo.
     --------------------------------------------------------------------- -->

**IA Generativa Avanzada y Sistemas Multi-Agente · UTDT**

Grupos de hasta **4**. Enunciado publicado el **domingo 2026-09-27**, entrega el **domingo 2026-10-18**.

<!-- --------------------------- fin del encabezado por instancia ---------- -->

---

## 0 · La idea

Este trabajo toma el pipeline de recuperación que construimos para RAG, lo saca del corpus sobre
el que se construyó, lo apunta a un corpus que elegís y limpiás **vos**, y después le pide que
sostenga una conversación -- dentro de una sesión y entre sesiones -- en una T4 gratuita.

**Tesis.** *El modelo no recuerda nada entre llamadas. Todo lo que puede usar en un turno es lo
que tu sistema puso en su ventana de contexto. La recuperación y la memoria son la misma
decisión -- qué entra en una ventana finita -- tomada frente a dos fuentes: un corpus que
escribió otra persona, y una conversación que tu sistema va escribiendo sobre la marcha. La
primera la podés limpiar antes de empezar; la segunda la limpiás mientras sucede, con el mismo
modelo que está hablando.*

El pipeline de RAG que construimos corría sobre un corpus que ya había sido limpiado para él. Acá
ese trabajo es tuyo -- y es donde están la mayoría de las sorpresas.

Las dos mitades comparten una misma línea de base honesta: **si entra, pegalo.** Un recuperador
tiene que ganarle a pegar los documentos; una memoria tiene que ganarle a reproducir el
historial. Buena parte de este lab consiste en averiguar cuándo lo logran.

`un corpus que limpiaste → una vara que congelaste → recuperación medida con ella → respuestas
que podés verificar → una ventana compartida por pasajes y conversación → memoria que sobrevive
a la sesión -- cada una medida contra "pegalo y listo"`

Las Etapas 3-4 reusan lo que construimos para RAG. Las Etapas 5-6 no suponen nada: los
fragmentos de código y las fuentes de abajo alcanzan para arrancar.

## 1 · Hechos de referencia (para argumentar con evidencia, no con intuiciones)

Afirmaciones específicas y verificables que vale la pena citar -- y contrastar con tus propios
números. Cuando un resultado es la evaluación que un proveedor hizo de su propio producto, se
aclara.

**El pipeline de recuperación y sus piezas**

- Generación aumentada por recuperación (RAG): un recuperador le pasa pasajes a un generador en
  tiempo de inferencia; el conocimiento paramétrico queda en los pesos, el no paramétrico en un
  índice que podés inspeccionar y actualizar. Lewis et al., *Retrieval-Augmented Generation for
  Knowledge-Intensive NLP Tasks*, NeurIPS 2020 (arXiv:2005.11401).
- Reciprocal Rank Fusion (RRF) puntúa un documento con `Σ 1/(k + rank)` sobre las listas
  rankeadas en las que aparece, con `k = 60` en el paper original -- una constante, no algo para
  ajustar con 30 preguntas. Cormack, Clarke & Büttcher, SIGIR 2009.
- Los cross-encoders vuelven a puntuar pares (consulta, pasaje) de forma conjunta y se usan como
  segunda etapa sobre una lista de candidatos de una primera etapa. Nogueira & Cho, *Passage
  Re-ranking with BERT* (arXiv:1901.04085).
- HyDE hace que un LLM escriba un *documento hipotético* -- un pasaje que respondería la
  pregunta -- y busca con su embedding en lugar del de la pregunta (el paper promedia varios de
  esos documentos junto con la pregunta misma). Gao et al., *Precise Zero-Shot Dense Retrieval
  without Relevance Labels*, ACL 2023 (arXiv:2212.10496).
- Contextual retrieval antepone a cada chunk un contexto específico, escrito por un LLM para ese
  chunk, antes de calcular el embedding y antes de armar el índice BM25. En la evaluación propia
  de Anthropic, la tasa de fallas de recuperación en el top-20 bajó de 5,7% a 3,7% solo con
  embeddings contextuales, a 2,9% agregando BM25 contextual, y a 1,9% agregando un reranker.
  Anthropic, *Introducing Contextual Retrieval* (2024) -- la evaluación de un proveedor, con su
  propio modelo escribiendo el contexto. Un contexto escrito por una plantilla a partir de
  metadatos es otra cosa, mucho más barata.

**La ventana es un presupuesto, no una capacidad**

- *Lost in the Middle*: la exactitud tiene forma de U según la posición del documento relevante
  -- es máxima al principio o al final del contexto. Con 20 documentos, GPT-3.5-Turbo con la
  respuesta en el medio sacó un puntaje *por debajo* de su exactitud a libro cerrado de 56,1%. En
  un experimento separado de recuperador-lector, leer 50 documentos recuperados en vez de 20 la
  mejoró solo en alrededor de 1,5 puntos, aunque el recuperador seguía encontrando más
  respuestas. Liu et al., TACL 2024 (arXiv:2307.03172).
- RULER: de los 17 modelos de contexto largo evaluados, todos declarando 32K tokens o más, solo
  alrededor de la mitad mantuvo un desempeño satisfactorio a 32K. Hsieh et al., COLM 2024
  (arXiv:2404.06654).
- La familia de modelos que vas a usar también se degrada: el reporte de Qwen3 le da a Qwen3-8B
  (sin thinking) un puntaje RULER de 96,3 a 4K tokens, 91,2 a 32K y 77,4 a 128K -- la evaluación
  del proveedor, sobre los pesos en precisión completa. Lo que corre en una T4 es una
  cuantización de 4 bits: tomá esos números como un techo, y medí los tuyos. Qwen Team, *Qwen3
  Technical Report* (arXiv:2505.09388).
- *Context Rot*: en 18 modelos, el desempeño se vuelve cada vez menos confiable a medida que
  crece el largo de la entrada, aun con la tarea fija. Reporte técnico de Chroma (2025) -- un
  reporte de la industria, sin revisión de pares.
- Hechos del runtime, del servidor que vas a usar (Ollama): la API de chat **no tiene estado**
  -- tu cliente manda la conversación entera en cada llamada; la ventana de contexto (`num_ctx`)
  es un parámetro por request, y cuando no lo mandás el servidor usa su valor por defecto --
  **4.096 tokens en una T4** (las versiones recientes eligen el valor por defecto según la
  memoria de la GPU; los 15 GB de una T4 dan 4.096). La referencia online del Modelfile dice
  2.048: medilo, no confíes en la documentación. El endpoint `/v1` compatible con OpenAI no
  permite fijar `num_ctx` por request en absoluto. El docstring de `llm.py` lista qué hace el
  servidor cuando un prompt no entra, medido en la versión que fija este lab -- y como parte de
  eso cambia entre versiones, `llm.chat` lo verifica en cada llamada sobre la tuya (la Etapa 4
  te hace verlo suceder una vez, a propósito).

**Recuperación dentro de una conversación**

- MTRAG, un benchmark de RAG conversacional multi-turno (110 conversaciones, 842 tareas):
  mandarle al recuperador la conversación completa, o incluso unos pocos turnos, "consistently
  under-performed" frente al último turno del usuario solo, y reescribir el último turno con un
  LLM mejoró sobre eso; los turnos tardíos, las preguntas sin respuesta y las preguntas que no se
  sostienen solas fueron las más difíciles. Katsis et al., TACL 2025 (arXiv:2501.03468).
- Separar el QA conversacional en *reescribir la pregunta, y después responderla* funciona, y el
  reescritor puede acercarse a la calidad humana. Vakulenko et al., WSDM 2021 (arXiv:2004.14652).
- Las reescrituras humanas "may lack sufficient information for optimal retrieval"; el paper
  nombra cuatro propiedades de una buena reescritura -- corrección, claridad, informatividad, no
  redundancia -- y juzga las reescrituras por la recuperación que producen. Ye et al., Findings of
  EMNLP 2023 (arXiv:2310.09716).

**Memoria**

- Un vocabulario: memoria **de trabajo** (*working*: la información activa para la decisión
  actual -- cada prompt se arma a partir de ella), **episódica** (*episodic*: experiencias
  pasadas), **semántica** (*semantic*: conocimiento sobre el mundo y, acá, sobre el usuario),
  **procedimental** (*procedural*: cómo actuar -- en los pesos, o en tu código y tus prompts).
  Sumers et al., *Cognitive Architectures for Language Agents* (CoALA), TMLR (arXiv:2309.02427).
  Usá estas palabras en tu informe.
- Generative Agents recupera recuerdos por `recency + importance + relevance` (recencia +
  importancia + relevancia), cada uno normalizado min-max a [0, 1], todos con peso 1; la recencia
  decae como 0,995 por hora de juego *desde la última vez que se recuperó el recuerdo*; la
  importancia es un entero de 1 a 10 que puntúa el LLM; la reflexión se dispara cuando la
  importancia sumada de los eventos recientes supera 150. Park et al., UIST 2023
  (arXiv:2304.03442).
- MemGPT trata la ventana como un sistema operativo trata la RAM: un contexto principal fijo
  (instrucciones de sistema, un contexto de trabajo escribible, una cola FIFO de mensajes
  encabezada por un *resumen recursivo* de los desalojados) respaldado por almacenamiento
  externo. Pasado un umbral de advertencia (por ejemplo, 70% de la ventana) le avisa al modelo
  que la memoria está bajo presión; en el umbral de vaciado desaloja mensajes por alrededor de la
  mitad de la ventana y los incorpora al resumen. Packer et al. (arXiv:2310.08560).
- Mem0 escribe recuerdos con cuatro operaciones -- ADD, UPDATE, DELETE, NOOP. En el benchmark
  LoCoMo, en su propia evaluación, **el contexto completo sacó más puntaje que Mem0** (puntaje de
  LLM-juez 72,90 contra 66,88) leyendo alrededor de 15× los tokens por pregunta (~26.000 -- la
  conversación entera -- contra ~1.800 de recuerdos recuperados). La memoria compró costo y
  latencia, no exactitud -- donde el historial entraba. Chhikara et al. (arXiv:2504.19413).
- Zep/Graphiti guarda dos líneas de tiempo por hecho (cuándo fue verdadero, cuándo se registró)
  y, ante una contradicción, *invalida* el hecho viejo en lugar de borrarlo. Rasmussen et al.
  (arXiv:2501.13956). No necesitás un grafo para esto: alcanza con unas columnas de timestamp en
  una fila.

**Evaluar la memoria**

- LongMemEval evalúa cinco habilidades -- extracción de información, razonamiento
  multi-sesión, razonamiento temporal, **actualizaciones de conocimiento**, **abstención** --
  sobre 500 preguntas. La exactitud cae en interacciones sostenidas: entre 30 y 60% para LLMs de
  contexto largo que leen el historial entero en lugar de solo las sesiones que contienen la
  respuesta. Las sesiones con la respuesta están etiquetadas, así que la recuperación se puede
  puntuar sin juez, y las reglas del juez difieren por tipo (una respuesta actualizada cuenta
  aunque también se mencione la vieja). Wu et al., ICLR 2025 (arXiv:2410.10813).
- LoCoMo puntúa sus preguntas "adversarial" (sin respuesta) según si la salida contiene la
  cadena en inglés "not mentioned" o "no information available" -- un "no se menciona" correcto
  en español sacaría cero. Maharana et al., ACL 2024 (arXiv:2402.17753). Por eso este lab puntúa
  la abstención a partir de un campo de un schema, no de una cadena de texto.
- No encontramos ningún benchmark en español de memoria de largo plazo ni de RAG
  conversacional. Vas a escribir tus propias sondas (*probes*), sobre tu propio corpus (Etapa 2).

**Compresión y resúmenes**

- El resumen recursivo para diálogos largos funciona -- y en una auditoría manual de 100
  muestras, alrededor del 10% del contenido de los resúmenes estaba mal: hechos inventados
  (2,7%), relaciones incorrectas (3,2%), detalles faltantes (3,9%). Wang et al.
  (arXiv:2308.15022).
- LLMLingua comprime prompts de lo grueso a lo fino -- descarta demostraciones enteras, y
  después tokens de poca información puntuados por un modelo de lenguaje chico -- y reporta hasta
  20× de compresión con poca pérdida. Jiang et al., EMNLP 2023 (arXiv:2310.05736).
- RECOMP comprime los documentos recuperados en un resumen corto, y puede devolver una *cadena
  vacía* cuando no ayudan -- el lector entonces responde sin texto recuperado, desde sus pesos.
  Eso no es abstención: negarse a responder es una decisión aparte, y la vas a medir aparte. Xu
  et al., ICLR 2024 (arXiv:2310.04408).

## 2 · El alcance lo definís vos

**Empezá estimando tu presupuesto.** Antes de escribir código, calculá cuánto tiempo tiene
realmente tu grupo y qué te compra una sesión gratuita de Colab. Este lab tiene costos que un
pipeline de RAG de un solo turno no tiene:

- **qué entra en la T4 a la vez** -- el generador, el embedder y el reranker comparten 15 GB
  (§7 tiene la cuenta);
- **cuántas pasadas de embeddings vas a pagar** -- una por cada variante de chunking o de
  prefijo que pruebes;
- **cuántas llamadas al LLM cuesta cada experimento** -- ítems × turnos × llamadas por turno
  (respuesta, reescritura, actualización del resumen, escritura en memoria) × brazos. Hacé la
  multiplicación antes de correrlo. Una grilla que parece razonable puede ser diez horas de
  generación;
- **cuánto lleva escribir el conjunto de evaluación** -- más de lo que pensás, y no se lo puede
  saltear.

Después decidí qué etapas vas a llevar hasta el final, cuáles al mínimo y cuáles vas a saltear.
Escribí ese plan -- es la primera entrada de tu registro de decisiones, y lo vas a comparar con lo
que realmente pasó.

Acá hay más de lo que cualquier grupo va a terminar bien. Esa es la idea: **cómo construir este
proyecto es decisión tuya.**

Lo que se evalúa es también **qué elegiste hacer y por qué** -- qué llevaste hasta el final, qué
recortaste o hiciste al mínimo, cómo gastaste tu tiempo y tu cómputo. Un proyecto que hace
**todo a medias** saca menos que uno que hace **menos, pero hasta el final, con una razón
explícita para el recorte.** Y un proyecto con menos etapas pero con un punto de vista genuino --
uno que conecta lo que construiste con otra cosa que sabés, o que cuestiona un resultado en vez
de reportarlo -- puede sacar más que una implementación impecable y completa sin nada de sus
autores adentro.

**Sobre el uso de IA.** Usala. Escribí código con ella, depurá con ella, discutí con ella. Pero
fijate lo que le hace a este trabajo: si un modelo puede producir la implementación en una tarde,
la implementación ya no es lo que distingue tu trabajo. Lo que queda es lo que no puede hacer por
vos -- decidir qué valía la pena construir, juzgar si un resultado es creíble, notar lo que nadie
te pidió que buscaras, y sostener una opinión que puedas defender. Esa parte escribila vos; es la
parte que leemos. En tu informe, contá brevemente cómo la usaste. Y una regla específica de este
lab: **si un modelo redactó alguno de tus ítems de evaluación, guiones de conversación o sondas
de memoria, decí cuáles y cómo los verificó una persona.** Un conjunto de evaluación escrito por
un modelo mide si tu sistema está de acuerdo con ese modelo.

**Entregable: un registro de decisiones.** Junto con tus notebooks y tu informe, llevá un
registro continuo: el presupuesto que estimaste al principio, qué probaste, qué recortaste y por
qué (tiempo, VRAM, llamadas, beneficio conceptual). Terminar en un lugar distinto de tu plan está
bien y es esperable -- decilo, y decí qué te hizo cambiar de opinión. **Cualquier edición del
conjunto de evaluación congelado es una entrada del registro.**

**El análisis extra es bienvenido.** Si aparece algo más interesante que las etapas de abajo --
una comparación que no sugerimos, un modo de falla que merece un párrafo, un vínculo con otro
paper o con otra materia -- seguilo, y contanos. Un hilo del que vale la pena tirar, si querés un
punto de partida: **¿tu ventana es tan grande como dice?** Tomá 10-20 de tus preguntas, rellená
el contexto con pasajes irrelevantes de tu propio corpus hasta unos 2K, 4K, 8K y 16K tokens (usá
un único `num_ctx` lo bastante grande para el más largo más su reserva de salida -- por ejemplo,
20.480 -- para los cuatro, y defendelo como pide §7), y poné el pasaje con la respuesta al
principio, en el medio y al final. Graficá con qué frecuencia sobrevive la respuesta. Compará tu
curva con los números de RULER del reporte de Qwen3 y con *Lost in the Middle*. ¿Cuál es la
ventana más grande en la que realmente confiarías -- y cuánto te habría costado usar más?

## 3 · Las etapas

### Etapa 0 · El corpus como decisión

**Por qué esta etapa.** El pipeline que construimos para RAG corría sobre un corpus elegido para
que los problemas de la recuperación aparecieran sin ningún trabajo sobre los datos: documentos
largos, estructura explícita, identificadores oficiales, referencias literales dentro del texto.
El tuyo no lo eligió nadie. Y su techo es el techo del pipeline: ninguna técnica posterior
recupera lo que los documentos no contienen.

**Pasos sugeridos.**
1. Elegí un corpus de [corpora.md](corpora.md), o traé el tuyo (las mismas ocho preguntas).
2. Auditá el tuyo como `00_corpus_audit` audita python-docs-es, y agregá lo que la auditoría
   resuelta deja afuera: cantidad de documentos; distribución de largos **en tokens del
   generador** (la auditoría resuelta solo estima el total); marcadores de estructura y qué tan
   regulares son; qué identifica a un documento y si sobrevive a una nueva descarga; cobertura de
   metadatos -- la proporción de documentos con una fecha / versión / estado utilizable; una
   estimación de casi-duplicados sobre una muestra (la auditoría resuelta solo cuenta el
   solapamiento exacto de párrafos entre versiones); y diez documentos crudos leídos por una
   persona, de principio a fin.
3. Completá la tabla de la auditoría (propiedad · medido · **qué etapa posterior paga por cada
   "no"**).
4. Conseguí tres números antes de comprometerte: el tamaño del corpus frente a la ventana que te
   podés permitir; un **chequeo puntual a libro cerrado** (cinco preguntas, sin recuperación); y
   el tamaño de la tarea de datos sucios.
5. Escribí un borrador de `corpus_card.md`: fuente y versión fijada, licencia y atribución, regla
   del subconjunto, defectos conocidos, qué pone a prueba bien el corpus.

Si elegiste python-docs-es, la auditoría resuelta es **donde tu Etapa 0 empieza, no donde
termina**. Mide las dos rutas de entrada a ese corpus y no elige ninguna; esa elección es tuya.

**Preguntas para el informe:** ¿Qué propiedades de las siete no cumple tu corpus -- y cuánto te
cuesta la octava, la similitud -- y en qué etapa vas a pagar por cada una? ¿Tu subconjunto
entraría en una ventana con el `num_ctx` que te podés permitir -- y si entrara, para qué
construir recuperación? ¿Cuánto de tu corpus es plausible que el generador ya haya leído, y cómo
vas a distinguir recuperación de recuerdo? ¿Qué hace que dos de tus documentos se puedan
confundir, y querés conservar esa propiedad?

---

### Etapa 1 · De la fuente a los documentos *(obligatoria)*

**Por qué esta etapa.** Todas las etapas posteriores cuelgan del registro de documento: las
etiquetas apuntan a él, los chunks se cortan siguiendo sus secciones, los filtros leen sus
metadatos, las citas nombran su id. El corpus sobre el que construimos RAG traía ese registro de
regalo. Acá lo construís vos -- y la mayor parte del trabajo es decidir qué es un *documento*.

**Pasos sugeridos.**
1. **Obtené y fijá** la fuente (commit, rama, versión de DOI, fecha de dump, o una lista de URLs
   con fecha de descarga y sha256) y registrala en un manifiesto.
2. **Extraé** según el formato. Para las tablas, decidí: mantenerlas, linealizarlas en oraciones
   "encabezado: valor", o reemplazarlas por una fuente estructurada oficial. Revisá una muestra
   a ojo.
3. **Normalizá**: Unicode NFC, espacios en blanco, guiones de corte de línea, encabezados y pies
   de página repetidos, markup (sacá la sintaxis, conservá los nombres que lleva:
   `` :meth:`Path.resolve` `` debería dejar `Path.resolve`).
4. **Ids estables.** `doc_id` a partir de la identidad propia de la fuente; `section_id` =
   `doc_id` + un camino estructural. Nunca el orden de las filas, nunca un nombre de archivo de
   descarga.
5. **Metadatos** -- fecha, versión, estado o vigencia, orador, URL -- y *validalos contra el
   cuerpo* (ver la nota de método más abajo).
6. **Casi-duplicados**: estimalos sobre una muestra (Jaccard de shingles o coseno de
   embeddings), decidí una política y registrala (`version`, `canonical_id`, `duplicate_of`,
   ...).
7. Escribí `documents.jsonl` (el contrato `schema.Document`), su manifiesto y `corpus_card.md`.
8. **Medí qué cambió la limpieza**: por regla, documentos tocados y caracteres eliminados; un
   diff antes/después sobre diez documentos.

```python
import unicodedata

from schema import Document, DocMetadata, Section, documents_hash, validate_documents
from store import build_or_load, write_jsonl

def normalize(text: str) -> str:
    # NFC importa: algunos extractores emiten acentos descompuestos ("e" + U+0301). Para BM25 y
    # para el puntaje por coincidencia exacta, "información" pasa a ser dos cadenas distintas --
    # ningún error, solo fallos.
    text = unicodedata.normalize("NFC", text)
    return " ".join(text.split())

CLEANING_HITS: dict[str, int] = {}    # regla -> documentos que cambió    } el paso 8 pasa
CLEANING_CHARS: dict[str, int] = {}   # regla -> caracteres que eliminó   } a ser un print

def apply(rule: str, fn, text: str) -> str:
    out = fn(text)
    if out != text:
        CLEANING_HITS[rule] = CLEANING_HITS.get(rule, 0) + 1
        CLEANING_CHARS[rule] = CLEANING_CHARS.get(rule, 0) + len(text) - len(out)
    return out

doc = Document(doc_id="3.13/library/pathlib", title="pathlib",
               text=body, sections=[Section(section_id="3.13/library/pathlib#basic-use", title="Uso básico",
                                            level=2, start=0, end=812)],
               metadata=DocMetadata(version="3.13", status="current", source_url=url, lang="es"))

# El hash del corpus depende de los documentos, no del orden en que los escribiste: va en
# cada manifiesto de índice, así un índice puede decir a partir de qué corpus se construyó.
corpus_sha = documents_hash(docs)
validate_documents(ART / "documents.jsonl").show().raise_if_failed()
```

**Trampa: dos documentos que son el mismo documento.** Informes mensuales consecutivos armados
con una misma plantilla; la misma página en tres versiones de la documentación; una ley y su
texto actualizado posterior; una pregunta y su duplicado marcado por un moderador. Cada uno tiene
su propio `doc_id`, con texto casi idéntico. Una métrica a nivel de documento entonces cuenta como
fallo el *contenido correcto* recuperado bajo el id de un hermano: una técnica que cae en la otra
versión parece peor, y un filtro de versión que resuelve el problema parece que perjudica.
Encontrá los casi-duplicados acá y registrá cuáles son **versiones** (respuestas distintas: "en
3.12" vs "en 3.13") y cuáles son **copias** (intercambiables). En la Etapa 2, una pregunta que no
fija una versión tiene un *conjunto* gold; una pregunta que sí la fija necesita que el filtro de
versión sea parte del sistema.

**Validá los metadatos contra el texto.** Un campo puede estar mal con total seguridad -- un
"status: in force" en una norma cuyas propias notas dicen que fue derogada, una fecha que es un
valor de relleno. Si alguna etapa posterior filtra por un campo, verificá ese campo contra el
cuerpo en una muestra y reportá la tasa de desacuerdo.

**Preguntas para el informe:** ¿Qué cambió la limpieza, en números, y qué regla cambió más? Nombrá
un defecto que un loader ingenuo habría dejado pasar sin ningún error, y cómo lo encontraste.
¿Cómo definiste un documento y una sección, y qué se rompe si una etapa posterior no está de
acuerdo? ¿Tus `doc_id` sobrevivirían a una descarga nueva el mes que viene? ¿Cómo trataste los
casi-duplicados, y a qué te compromete eso en el conjunto de evaluación?

---

### Etapa 2 · La vara de medir *(obligatoria)*

**Por qué esta etapa.** La medición más útil del pipeline de RAG que construimos no usaba ningún
modelo: preguntas escritas a mano, cada una etiquetada con el documento que la responde. Acá la
vara tiene que llegar más lejos -- preguntas de seguimiento que solo tienen sentido en contexto, y
hechos dichos en una sesión y preguntados en otra. Nadie armó eso para tu corpus en español.
Junto con la Etapa 1, esta etapa **alimenta todo**, y se **congela antes de ajustar cualquier
decisión del pipeline contra ella.**

**Pasos sugeridos.**
1. **Un solo turno: al menos 30 preguntas escritas a mano, parafraseadas**, escritas a partir de
   una lista de *temas*, no con el pasaje abierto. Categorías (el vocabulario de
   `schema.CATEGORIES`): *topical* (temáticas); *identifier* (nombres exactos, números, códigos);
   *metadata* (una versión, una fecha, un período); y *fuera del corpus* (`out_of_corpus`: al
   menos 3, y **adyacentes** -- un mes que no tenés, una función que no existe en tu versión --
   no "¿quién ganó el Mundial de 1986?"; y decidí ahora qué es una respuesta correcta a una de
   ellas -- negarse, o un "eso no existe en tu versión" fundamentado -- y después puntuá cada brazo
   con esa regla). Gold a nivel de **documento y sección**, como *conjunto* cuando las copias son
   intercambiables, más una `answer_key` (clave de respuesta) corta donde exista -- y, para una
   pregunta de sí/no, su `expected_verdict` (ver más abajo). Las preguntas de identificador se
   pueden *derivar* de identificadores que aparecen en exactamente un documento -- derivalas, no
   las escribas.
2. **Chequeá la contaminación** (fragmento de abajo) y corré ahora una recuperación **solo con
   BM25**. Reescribí los ítems marcados.
3. **Guiones de conversación** (`schema.Dialogue`): 3-6 turnos cada uno. Cada turno de
   seguimiento lleva una etiqueta de dependencia (`schema.DEPENDENCIES`: `coreference`
   (correferencia), `ellipsis` (elipsis), `topic_shift` (cambio de tema), `return` (volver a un
   tema anterior), `unanswerable` (sin respuesta) -- el primer turno es `standalone`), gold y clave
   de respuesta por turno, la **respuesta guionada del asistente** que va a contener el historial
   del turno siguiente, y una **reescritura autónoma escrita a mano** (la fila oráculo de la
   Etapa 5).
4. **Escenarios multi-sesión** (`schema.Scenario`): una persona *ficticia* cuyos datos importan
   para tu corpus (una versión que usa, una región que sigue, una fecha "a la cual" pregunta),
   sesiones con **timestamps simulados**, y sondas etiquetadas con la habilidad que evalúan
   (`schema.ABILITIES`) y las sesiones que contienen la evidencia. Cada escenario necesita al
   menos un hecho que **cambia** y uno que **nunca se dijo**.
5. **Separá roles**: quien construya la Etapa 6 no debería ser el único autor de sus sondas.
6. **Dev y test.** Marcá un puñado de ítems por categoría con `split: "dev"` (cada fila es
   `"test"` por defecto): eso es lo que ajustás y mirás mientras construís. Reportá sobre `test`.
7. **Congelá** contra el corpus completo:
   `schema.freeze_eval("eval", environment.artifacts_dir(False) / "documents.jsonl")` escribe
   `eval/FROZEN.json`; commitealo *antes de que exista ningún resultado* (si lo congelás en Colab,
   queda en un disco que se borra al desconectarse: descargalo y commitealo desde tu máquina). A
   partir de ahí, `schema.load_eval("eval", documents_path=...)` rechaza un conjunto editado -- o
   un corpus que cambió por debajo -- y una edición posterior es una entrada del registro de
   decisiones, con cada fila puntuada antes de ella vuelta a correr o descartada. (Los ítems smoke
   viven en `eval/smoke/`, se cargan con `require_frozen=False`; ver §7.)

```python
import re
import Stemmer   # PyStemmer

stem = Stemmer.Stemmer("spanish").stemWord
STOP = set("de la que el en y los se del las un por con no una su para es al lo como más".split())

def content_words(text: str) -> list[str]:
    # La MISMA normalización que usa tu canal léxico: un chequeo que tokeniza distinto que
    # BM25 mide un solapamiento distinto del que infla a BM25.
    return [stem(w) for w in re.findall(r"\w+", text.lower()) if w not in STOP]

def contamination(question: str, gold_text: str, n: int = 5) -> dict:
    q, g = content_words(question), content_words(gold_text)
    overlap = sum(w in set(g) for w in q) / max(len(q), 1)
    grams = lambda ws, k: {tuple(ws[i:i + k]) for i in range(len(ws) - k + 1)}
    shared = max((k for k in range(len(q), 0, -1) if grams(q, k) & grams(g, k)), default=0)
    return {"overlap": round(overlap, 2), "longest_shared_ngram": shared, "flag": shared >= n}
```

**Trampa: las preguntas escritas leyendo el pasaje miden copia.** Escribir una pregunta con el
pasaje gold abierto importa sus palabras raras y sus frases exactas. BM25 entonces las encuentra,
la recuperación densa no necesita generalizar, y "el híbrido le gana al denso" o "el reranker
ayuda" pasan a ser artefactos de *cómo se escribieron las preguntas*. Ningún error en ningún lado;
la tabla simplemente mide otra cosa. Escribí a partir de temas, medí el solapamiento, reescribí lo
marcado, y mantené las preguntas deliberadamente literales en su propia categoría
(identificadores), donde la coincidencia literal es justamente el punto y se mide como tal.

**No dejes que un modelo escriba tu vara de medir.** Si un modelo redacta preguntas a partir de un
pasaje, reusan su redacción (ver arriba). Si las redacta el *generador*, el conjunto de evaluación
mide si el sistema está de acuerdo consigo mismo. Un ítem redactado es una propuesta hasta que una
persona verificó la respuesta contra el corpus -- decí cuáles son esos ítems.

**Una clave de respuesta no puede decir que no.** La contención pasa cuando *cualquier* cadena de
la clave aparece en la respuesta. Para "¿puedo usar X en 3.12?" la clave natural es la versión en
la que llegó X -- y "No, X llegó en 3.13" y "Sí, X está desde 3.13" la contienen las dos. Cada
"¿puedo usar X en mi versión?", cada sonda de antes/después de la actualización, cada "¿soporta
...?" puntúa igual sea el veredicto correcto o no, y una memoria que nunca registró la
actualización puntúa tan bien como una que sí. Dales a esos ítems un `expected_verdict` (`"yes"` /
`"no"`) y puntuá el veredicto aparte de la clave: a partir de la primera palabra de la respuesta,
de forma estricta (cualquier otra cosa es *unclear*, poco claro, y se cuenta como tal), y sobre el
texto crudo -- la normalización que saca los acentos para la contención convierte *sí* en *si*,
el condicional. Dos agujeros más, uno de cada lado. "No lo sé" también empieza con *no*: una
abstención no es el veredicto "no", o cada abstención puntúa bien en los ítems "no". Y un
veredicto solo premia a un brazo que dice "sí" a todo en cada ítem "sí" -- una actualización se
ve solo en un *par*: la misma pregunta hecha antes y después de ella, veredictos opuestos, los dos
correctos.

**Preguntas para el informe:** ¿Cómo evitaste que las preguntas copiaran al corpus, y qué dice tu
chequeo de contaminación? ¿Qué fracción de tus etiquetas gold son conjuntos en lugar de ids
únicos, y por qué? ¿Qué habilidades de memoria cubren tus escenarios, con cuántas sondas cada una
-- y cuáles dejaste afuera? Describí una pregunta que haría un usuario real y que tu conjunto no
puede medir. Si después tus columnas temática y de identificador no coinciden sobre una técnica,
¿en cuál vas a confiar -- y por qué decidirlo ahora?

---

### Etapa 3 · Recuperación sobre tu corpus

**Por qué esta etapa.** Este es el protocolo que usamos para RAG -- congelar la vara, mover una
variable, leer la tabla -- ahora sobre un corpus que limpiaste vos. Los resultados no se
transfieren entre corpus: en el corpus sobre el que lo construimos, no todas las piezas pagaron lo
que costaban, y una mejora resultó tener una causa ajena al mecanismo propio de la técnica.
Averiguá qué piezas se ganan su costo *acá*.

*(Recortar las Etapas 5-7 es una elección legítima según §2. El intercambio que discutiríamos es
el que parece más seguro: una grilla completa de la Etapa 3 y nada después. La Etapa 3 repite un
protocolo que ya corrimos; la Etapa 5 es donde vive la pregunta de este proyecto. Tres filas bien
acotadas acá y una Etapa 5 real hacen un proyecto mejor. Si parás en la Etapa 4, defendelo en el
registro de decisiones.)*

**Pasos sugeridos.**
1. **Construí el índice.** Hijos cortados siguiendo la estructura, dimensionados en tokens **del
   reranker** con el prefijo incluido; padres = la unidad estructural, con un tope en tokens del
   generador; un prefijo contextual a partir de metadatos (título, sección, versión -- y el
   *año*, para cualquier cosa periódica); `BAAI/bge-m3`; `bm25s` con un stemmer en español,
   stopwords y la normalización de identificadores **de tu corpus**; un manifiesto de índice (id
   y revisión del embedder, largo máximo de secuencia, parámetros del chunker, el hash del
   corpus). `store.cached_matrix(..., art_dir=ART)` guarda los embeddings en `ART/embeddings/`,
   con clave en la especificación del encoder que le pasás más los ids de los chunks *y sus
   textos* -- así un prefijo nuevo o un re-corte es una matriz nueva, nunca una vieja.
2. **Una función de recuperación, un flag por pieza.** Una pieza faltante **lanza una
   excepción**. Cada resultado registra la configuración que lo produjo.
3. **Filas**: solo BM25 (una línea de base, y también un detector de contaminación) · denso ·
   + prefijo · + léxico vía RRF · + rerank · + padre · + filtro de metadatos (parseado de la
   pregunta acá; de la memoria en la Etapa 6). HyDE, si lo probás, es una *rama etiquetada*, no
   una fila acumulativa.
4. **Métricas, por categoría**: hit@k y MRR a nivel de documento; hit@k a nivel de **sección**;
   *answer-delivered* (respuesta entregada: la clave de respuesta aparece en el texto entregado);
   tokens del generador entregados; latencia. Opcionalmente, para las preguntas fuera del corpus:
   la distribución de los puntajes máximos -- ¿puede la recuperación sola decirte que la
   respuesta no está?
5. **Entregá por presupuesto de tokens, no por k** (ver la trampa).
6. **Acotá el ruido**: victorias/derrotas/empates pareados contra la fila anterior, un test de
   signos o un test exacto de McNemar, y un intervalo bootstrap por fila.
7. **Abrí la caja** en el movimiento más grande: rankings por canal para las preguntas que
   cambiaron de resultado.

```python
from dataclasses import asdict, dataclass

@dataclass(frozen=True)
class RetrievalConfig:
    dense: bool = True
    prefix: bool = False
    lexical: bool = False
    rerank: bool = False
    parent: bool = False
    metadata_filter: bool = False
    budget_tokens: int = 3000   # entregados al generador, contados en SU tokenizer

def retrieve(query: str, cfg: RetrievalConfig, index) -> list[dict]:
    # Lanzá una excepción, no la saltees. Una pieza que avisa y sigue produce una fila idéntica
    # a la anterior, y vas a leer "sin efecto" en una tabla que nunca corrió la pieza.
    if cfg.lexical and index.bm25 is None:
        raise RuntimeError("lexical=True but no BM25 index is loaded")
    if cfg.rerank and index.reranker is None:
        raise RuntimeError("rerank=True but no reranker is loaded")
    if cfg.metadata_filter and index.metadata is None:
        raise RuntimeError("metadata_filter=True but no document metadata is loaded")
    ...

def rrf(ranked_lists: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in ranked_lists:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)

def diff_rows(prev: RetrievalConfig, cur: RetrievalConfig) -> str:
    changed = [k for k, v in asdict(cur).items() if asdict(prev)[k] != v]
    if not changed:
        return "identical configuration -- a duplicate row, not a new one"
    return (f"one variable: {changed[0]}" if len(changed) == 1
            else f"{len(changed)} variables differ ({', '.join(changed)}) -- NOT a cumulative row")
```

Chequeá también la ventana del reranker: lee `max_length` tokens de (consulta + hijo) y descarta
el resto en silencio. Imprimí la proporción de tus pares que supera ese límite, en el propio
tokenizer del reranker.

**Trampa: un acierto de documento no es una respuesta entregada.** El hit@k a nivel de documento
cuenta un acierto cuando llega *cualquier* pasaje del documento gold -- el encabezado y el primer
artículo, digamos, mientras la respuesta está diez artículos más adelante. Por construcción
tampoco puede ver la entrega del documento padre: el padre siempre está en el mismo documento que
el hijo. La recuperación entonces parece cerca de su techo, y las respuestas "no está en el
contexto" de la Etapa 4 se le atribuyen a la generación. Etiquetá el gold a nivel de sección,
chequeá si la clave de respuesta fue *entregada*, reportá las dos cosas -- y leé la brecha entre
ellas antes de empezar la Etapa 4.

**Trampa: "el mismo k" no es el mismo presupuesto.** Con `k = 5`, los padres pueden entregar el
doble de tokens que los hijos, y más tokens aumentan la probabilidad de que la cadena de la
respuesta esté en algún lugar del contexto. La mejora se le acredita entonces a la técnica cuando
vino del volumen -- el mismo error que comparar dos formas de modelo que difieren en tamaño y
acreditarle la diferencia a la forma: un presupuesto comparable es una restricción que imponés,
no algo que te viene dado. Llená cada fila hasta el mismo presupuesto de tokens (en tokens del
generador), reportá los tokens realmente entregados por fila, e imprimí un veredicto cuando dos
filas difieran en más de una tolerancia que declares.

**Calculá tu piso de ruido antes de afirmar nada.** Con 30 resultados binarios cerca del 85%, el
intervalo del 95% de una sola fila abarca aproximadamente ±12 puntos. Para una comparación
*pareada*, solo las preguntas discordantes llevan información: si `n` preguntas cambiaron y todas
se movieron para el mismo lado, el test de signos bilateral da `p = 2 × 0.5ⁿ` -- un 5-0 da
alrededor de 0,06, un 6-0 alrededor de 0,03. Así que "26/30 → 28/30" no es evidencia de nada. Un
resultado débil que podés acotar vale más que uno fuerte que no podés.

**RRF supone que los canales fallan de forma independiente.** Cuando una consulta engaña a los dos
canales de la misma manera -- el canal denso cae en un grupo de pasajes parecidos, BM25 en los
mismos tokens genéricos -- su acuerdo rankea *más alto* los pasajes equivocados, y el consenso
entierra el correcto. Antes de acreditarle (o culpar) a una pieza, mirá los rankings por canal de
las preguntas que hizo cambiar.

**Preguntas para el informe:** ¿Qué piezas se ganaron su costo en tu corpus, por encima de tu cota
de ruido -- y cuáles sacaste? Para el movimiento más grande, ¿qué mostró abrir la caja: ganó por la
razón que da su paper? ¿Qué tan separados están tus números a nivel de documento y a nivel de
sección (o de respuesta entregada), y qué predice eso para la Etapa 4? Con tokens igualados, ¿es
mejor entregar muchos hijos o pocos padres? ¿Ayudó el filtro de metadatos, y en qué categoría?

---

### Etapa 4 · Respuestas fundamentadas con un presupuesto en el que podés confiar

**Por qué esta etapa.** La recuperación fija el techo; la generación decide cuánto de él se
alcanza. Esta etapa mide esa segunda superficie -- y construye el componente del que dependen
todas las etapas posteriores: **un ensamblador de prompts que llena un presupuesto de tokens, con
una cuenta que verificaste contra la del propio servidor.**

**Pasos sugeridos.**
1. **Ensamblador**: prompt de sistema + pasajes delimitados (marcadores `[doc_id · section]`) +
   pregunta, con una reserva de salida igual a `num_predict`. El prompt entero se cuenta con la
   plantilla de chat del generador (`llm.count_prompt_tokens(messages, model)`); el `count` por
   pasaje que reciben los fragmentos de abajo puede ser `lambda t: llm.count_tokens(t, MODEL)`,
   que cuenta texto pelado y no ve los marcadores de plantilla de cada mensaje -- dejá un margen,
   y dejá que `llm.chat` verifique el total. Cada llamada registra tu cuenta *y* el
   `prompt_eval_count` del servidor.
2. **Generación**: `qwen3:8b`, `think=False`, temperatura 0, un schema de Pydantic como `format`
   (`llm.structured`), y un `num_ctx` explícito en cada llamada, a través de la API nativa.
   Declará el campo de razonamiento **primero**, mantenelo obligatorio, y dale un nombre que
   también quede primero alfabéticamente: según la versión del servidor, las claves se escriben
   en el orden del schema (la versión que fija este lab hace eso) o en orden alfabético, y en
   cualquiera de los dos casos querés que el modelo razone *antes* de comprometerse con una
   respuesta. `llm.probe_key_order` te dice qué hace tu servidor.
3. **Puntuá sin juez**: la abstención **a partir del booleano del schema**; citas ⊆ ids
   entregados; citados ∩ gold; contención de la clave de respuesta después de normalizar
   (acentos, formatos de números, comas decimales); el veredicto de los ítems de sí/no, puntuado
   aparte de la clave (Etapa 2); flags de consistencia (el booleano dice "no hay suficiente
   contexto" pero la respuesta no es una abstención, y viceversa). Una llamada con `r.error`
   seteado -- una respuesta que no se pudo parsear, un prompt truncado, un rechazo del servidor --
   es su **propia categoría**: nunca una abstención, nunca una respuesta puntuada.
4. **Tres filas sobre preguntas idénticas**: a libro cerrado (sin recuperación), tu mejor
   configuración de la Etapa 3, y **oráculo** (la sección gold entregada).
5. **La tabla 2×2 por pregunta**: recuperó bien / mal × respondió bien / mal. Nombra las dos
   fallas que vale la pena separar: *fiel al pasaje equivocado* y *lo tenía, respondió otra cosa*.
6. *Opcional:* posición del pasaje -- el pasaje con la respuesta primero, en el medio o último,
   con una cantidad fija de pasajes y de tokens. Rellená hasta 10-20 pasajes si querés tener
   chances de ver un efecto.

```python
from pydantic import BaseModel, Field
import llm

class GroundedAnswer(BaseModel):
    # Declarados en el orden en que el modelo debería escribirlos, obligatorios, y con nombres
    # tales que el orden alfabético coincida ("analysis" < "answer" < "can_answer" < "citations"):
    # el razonamiento viene ANTES que la respuesta en cualquier servidor.
    analysis: str = Field(max_length=600)       # un tope, para que un análisis largo no se coma num_predict
    answer: str = Field(max_length=1200)
    can_answer: bool
    citations: list[str]

def assemble(passages: list[dict], budget: int, count) -> tuple[list[dict], list[dict]]:
    delivered, skipped, used = [], [], 0
    for p in passages:
        n = count(p["text"])
        if used + n > budget:
            skipped.append(p)   # saltear y registrar -- no `break`: un break en el primer pasaje
            continue            # que no entra descarta también todos los más chicos que vienen después
        delivered.append(p)
        used += n
    return delivered, skipped

answer, r = llm.structured(messages, GroundedAnswer, model="qwen3:8b", num_ctx=8192, num_predict=700)
print(r.expected_prompt_tokens, r.prompt_tokens, r.done_reason, r.error)
```

`llm.chat` rechaza un prompt que no entra (`ContextOverflow`, antes de mandarlo; y le pide al
servidor que rechace en lugar de truncar), y marca un prompt que el servidor evaluó solo en parte
(`SILENT_TRUNCATION`). Las dos cosas necesitan el tokenizer del modelo: funcionan para los tags de
`llm.HF_TOKENIZERS`, y para cualquier otro tag primero agregás ahí su repo de HuggingFace. Apagá
la guarda una vez (`strict_ctx=False`), a propósito, con un prompt demasiado grande -- y mirá qué
vuelve.

**Trampa: el servidor le corta el frente a un prompt demasiado grande.** Cuando un único prompt
supera `num_ctx`, Ollama conserva sus primeros tokens y su *cola*, y descarta el medio. Lo que se
va son tus instrucciones, la regla de abstención y los pasajes mejor rankeados; la pregunta del
final sobrevive. El modelo igual responde con fluidez -- a partir de tus pasajes peor rankeados --
y `format` igual hace que la salida sea JSON válido. El servidor lo registra una vez, como una
advertencia en un log que nadie lee. El valor por defecto en una T4 es 4.096 tokens, así que cinco
pasajes y un prompt de sistema alcanzan para chocarlo; y el endpoint `/v1` compatible con OpenAI
no puede fijar `num_ctx` por request, así que cualquier framework apuntado a él hereda el valor
por defecto del servidor. Las conclusiones equivocadas que esto produce: "el reranker no ayuda a
la generación" (sus mejores pasajes fueron los primeros en irse), "el modelo ignora la regla de
abstención", "más pasajes perjudican". Fijá `num_ctx` en cada llamada, mantené el prompt por
debajo de `num_ctx − num_predict`, y compará `prompt_eval_count` con tu propia cuenta en cada
llamada.

**Contá lo que te da el schema.** La abstención es un booleano: buscar la cadena "No lo sé" la
cuenta mal, porque el modelo puede parafrasear, o escribir "No lo sé" en el análisis mientras
responde en el campo de respuesta. Una cita es una *afirmación* -- verificala contra lo que
realmente se entregó.

**Los efectos de posición necesitan una ventana en la que valga la pena perderse.** Con cinco
pasajes en cinco mil tokens, un resultado nulo no refuta *Lost in the Middle*. Si evaluás la
posición, decí qué tamaño de prueba *podría* haber mostrado el efecto.

**Preguntas para el informe:** De las preguntas en las que llegó el pasaje con la respuesta,
¿cuántas se respondieron bien, y cómo eran las fallas? ¿Qué tan grande es la brecha entre la fila
oráculo y tu mejor fila de recuperación -- y entre libro cerrado y tu mejor fila? ¿Con qué
frecuencia el modelo citó un pasaje que no se le dio, o se abstuvo mientras la respuesta estaba en
su contexto? Mostrá un prompt demasiado grande: tu cuenta, la cuenta del servidor, y qué respondió
el modelo. ¿Importó la posición a tu escala, y podría tu prueba haberlo mostrado si importara?

---

### Etapa 5 · La conversación: una ventana, dos fuentes *(el corazón del lab)*

**Por qué esta etapa.** La API no tiene estado: todo lo que el modelo "recuerda" dentro de una
sesión es lo que tu código vuelve a poner en la ventana en cada turno. Una vez que hay una
conversación, la ventana tiene dos reclamantes -- los pasajes del corpus y el historial -- y cada
turno tiene las mismas dos superficies de falla que el RAG de un solo turno: **con qué busca el
recuperador**, y **qué ve el generador**.

**Pasos sugeridos -- Parte A: con qué buscar.**
1. Sobre tus guiones de conversación, contra el gold por turno, compará cuatro configuraciones de
   consulta: solo el **último turno**; la **conversación completa**; una **reescritura
   condensada** del último turno hecha por un LLM a partir del historial reciente (un schema con
   un solo campo, por ejemplo `{"query": str}`); y tu reescritura **oráculo** escrita a mano.
   (Acordate de Ye et al.: la reescritura humana no siempre es la mejor consulta.)
2. Reportá hit@k y hit@k de sección **por etiqueta de dependencia y por número de turno**.
3. **Leé 20 reescrituras a mano.** Un reescritor que responde la pregunta, agrega detalles
   específicos o incluye sus pasos de razonamiento dirige la recuperación como lo hace HyDE -- por
   razones ajenas a reescribir.

**Pasos sugeridos -- Parte B: qué conservar. El experimento central.**
4. **Estrategias de historial**: el buffer completo (solo mientras realmente entre -- chequealo);
   una ventana de los últimos N turnos; un **buffer de resumen** al estilo MemGPT (un resumen
   continuo más los turnos recientes, que se vuelve a resumir cuando el historial cruza un umbral
   de su presupuesto); opcionalmente, compresión extractiva de pasajes (conservar las oraciones
   que tu reranker puntúa más alto) para hacer lugar.
5. **El experimento.** Fijá `num_ctx` (por ejemplo, 8.192) y un presupuesto total de prompt para
   pasajes + historial. Mové **una sola** cosa: la división entre ellos (por ejemplo, 80/20 vs
   50/50 vs 30/70 del total), *o* una elección de compresión con una división fija. Mantené todo
   lo demás fijo: los guiones, el recuperador, el ganador de la Parte A, la reserva de salida.
   **Dimensioná el historial para que sea una restricción real.** Un guion de 3-6 turnos son unos
   pocos cientos de tokens de historial: frente a un presupuesto de historial de mil o más, cada
   estrategia conserva todo, la división solo mueve el presupuesto de pasajes, y la tabla dice
   "el historial no importa". Reproducí tus guiones uno detrás de otro como una sola conversación
   larga (cada turno conserva su propio gold y el id de su guion, para el bootstrap), imponé un
   total lo bastante chico como para que el lado del historial de cada división sea una
   restricción en buena parte de los turnos, o las dos cosas -- e imprimí los tokens de historial
   por turno contra el presupuesto de cada división antes de la primera respuesta.
6. **Reproducí historiales guionados.** Cada brazo ve el *mismo* historial -- las respuestas
   guionadas del asistente de la Etapa 2 -- y solo se genera el turno actual. Si cada brazo se
   realimentara con sus propias respuestas anteriores, los brazos divergirían a partir del turno 2
   y cada comparación posterior quedaría confundida; reproducir además cuesta una fracción de las
   llamadas.
7. **Métricas por turno**: contención de la respuesta, abstención correcta en los turnos sin
   respuesta, tokens y llamadas al LLM por turno, latencia. Acotá el ruido **por guion**, no por
   turno.
8. **Poné a prueba el resumen**: al final de cada guion, preguntá por un detalle de los turnos
   1-2, y auditá el texto del resumen en sí buscando hechos inventados, relaciones equivocadas y
   detalles faltantes.

```python
def turn_messages(system: str, history: list[dict], passages: list[dict], question: str,
                  hist_budget: int, pass_budget: int, count) -> list[dict]:
    # Armá la ventana vos, en cada turno, dentro de un presupuesto que verificaste. No le pases al
    # servidor una lista de mensajes que crece confiando en que entre: pasado num_ctx descarta los
    # turnos más viejos sin avisarte (ver la Trampa de abajo).
    kept, used = [], 0
    for msg in reversed(history):                 # los más nuevos primero
        n = count(msg["content"])
        if used + n > hist_budget:
            break                                 # acá descartar los turnos MÁS VIEJOS es justamente la idea
        kept.insert(0, msg)
        used += n
    context, _ = assemble(passages, pass_budget, count)
    context_block = "\n\n".join(f"[{p['doc_id']} · {p['section']}]\n{p['text']}" for p in context)
    return ([{"role": "system", "content": system}] + kept +
            [{"role": "user", "content": f"<contexto>\n{context_block}\n</contexto>\n\n{question}"}])

class Rewrite(BaseModel):
    query: str = Field(max_length=300)   # un solo campo: nada con qué razonar, nada que responder

def conversation_query(history: list[dict], question: str) -> str:
    # Para la configuración de conversación completa: el turno MÁS NUEVO primero. El embedder
    # trunca por la derecha en su max_seq_length, y una concatenación en orden cronológico pierde
    # justamente el turno que dice qué se está preguntando ahora. Solo los turnos del usuario --
    # una elección: incluí las respuestas del asistente si tu "conversación completa" significa
    # las dos cosas, y decí cuál hiciste.
    return " \n".join([question] + [m["content"] for m in reversed(history) if m["role"] == "user"])
```

**Trampa: tu brazo de historial completo es una ventana deslizante.** Cuando los mensajes de una
llamada a `/api/chat` superan `num_ctx`, Ollama **descarta los mensajes más viejos** -- conserva
el mensaje de sistema y los más recientes -- y lo registra solo en nivel debug. Pasada la
ventana, tu "buffer completo" es en secreto "prompt de sistema + los últimos turnos", así que
"completo vs. ventana vs. resumen" queda confundido; "el modelo se olvidó de lo que dije en el
turno 2" es el servidor, no el modelo; y el brazo con "más historial" en realidad no recibió más.
Tu ensamblador decide qué entra, y `prompt_eval_count` lo confirma.

**Trampa: una consulta con la conversación completa pierde su último turno.** Los embedders de
oraciones truncan por la derecha en el `max_seq_length` que fijes (§7 sugiere 512-1.024). Una
conversación concatenada en orden cronológico conserva sus *primeros* turnos y descarta en
silencio el más nuevo -- el único turno que dice qué se está preguntando ahora. El resultado
coincide con un hallazgo publicado (MTRAG: las consultas con la conversación completa rinden menos
que el último turno) por una razón que no tiene nada que ver con ese hallazgo, y empeora turno a
turno a medida que crece la conversación. (Un único guion de 3-6 turnos puede no llegar nunca al
límite -- contá la consulta en tokens del embedder; reproducidos uno detrás de otro, tus guiones
van a llegar.) Poné el último turno primero, o truncá por la izquierda, contando en el propio
tokenizer del embedder. BM25 no tiene ese límite, así que ahora los dos canales ven consultas
distintas -- vale una oración en tu informe.

**Un total igualado es una restricción que imponés.** Compará los brazos con el mismo total de
tokens de prompt *tal como los contó el servidor*. Y mantené `num_ctx` constante entre brazos:
cada cambio de `num_ctx` vuelve a cargar el modelo, así que intercalar brazos que difieren en él
convierte tu columna de latencia en un conteo de recargas. Imponé los presupuestos en tu
ensamblador.

**Lo que entra al historial es lo que vio el usuario.** Guardá la `answer` (y sus citas), no el
campo `analysis`. La propia recomendación de Qwen es no conservar el razonamiento en el historial,
y el campo de análisis *es* razonamiento.

**Los turnos no son independientes.** Cincuenta turnos de diez guiones no son cincuenta muestras:
al hacer bootstrap, remuestreá guiones, no turnos.

**Preguntas para el informe:** ¿Qué configuración de consulta ganó en qué tipo de dependencia, y
cambia el ranking con el número de turno? Con una ventana fija, ¿dónde quedó la mejor división
pasajes/historial para tu corpus -- y la diferencia está por encima de tu cota de ruido? ¿Qué
hicieron mal tus resúmenes, contado en las tres categorías de la auditoría? ¿Cuánto cuesta cada
estrategia por turno, en llamadas y tokens, y vale la pena el ganador? ¿Dónde perdió la
reescritura oráculo frente a la del modelo, o le ganó?

---

### Etapa 6 · Memoria entre sesiones

**Por qué esta etapa.** Entre sesiones no sobrevive nada que no escribas. Acá la memoria es un
corpus que tu sistema escribe *en tiempo de ejecución*, a partir de una fuente que puede estar
equivocada -- su propia extracción -- y que tiene que mantener actualizado. En los términos de
CoALA: la ventana ensamblada es la memoria de trabajo; las transcripciones y los resúmenes de las
sesiones son episódicos; los hechos extraídos son semánticos; las preferencias sobre *cómo*
responder son procedimentales. La línea de base honesta es "reproducir todo lo que entre" -- y en
la evaluación propia de Mem0, esa línea de base ganó en exactitud.

**Pasos sugeridos.**
1. **Líneas de base**: sin memoria (el piso), y reproducción completa de las sesiones pasadas,
   todo lo que entre. *Declará el régimen*: ¿el historial de tu escenario entra en la ventana o
   no?
2. **Camino de escritura**: después de cada sesión (o turno), extraé hechos candidatos con un
   schema; recuperá los recuerdos existentes más parecidos; decidí **ADD / UPDATE / NOOP /
   INVALIDATE**; guardá `created_at`, `valid_from` y `valid_to`. **Invalidá, no borres**: "¿qué
   había dicho antes?" tiene que seguir teniendo respuesta.
3. **Camino de lectura**: recuperá recuerdos por relevancia (el mismo embedder), opcionalmente con
   recencia e importancia al estilo de Generative Agents -- sobre los timestamps **simulados** del
   escenario -- y ponelos en un **espacio de memoria** (*memory slot*) del ensamblador de la Etapa
   4, dentro de su presupuesto.
4. **La memoria alimenta la recuperación.** Los hechos del usuario que se corresponden con
   metadatos del corpus se convierten en filtros: la versión que usa, la fecha "a la cual"
   pregunta, la región que sigue (corpora.md nombra un gancho por corpus). Medilo en las sondas
   que lo necesitan -- y notá cuando el filtro *saca* el pasaje que le permitiría al modelo decir
   "eso no está disponible para vos".
5. **Métricas**: exactitud de las sondas por habilidad, reportada como **conteos** (3/4, no 75%);
   recall de las sesiones con evidencia (sin juez); tokens y llamadas al LLM por sesión; un conteo
   de registros guardados que están mal o que nunca se dijeron.
6. **Compará** sin memoria / reproducción / almacén con presupuestos declarados. El resultado de
   Mem0 predice que el almacén gana en costo y pierde en exactitud *donde la reproducción entra*.
   Reproducilo o refutalo a tu escala -- y encontrá dónde la reproducción deja de entrar.

```python
from datetime import datetime
from typing import Literal

class MemoryRecord(BaseModel):
    memory_id: str
    kind: Literal["semantic", "episodic", "procedural"]
    subject: str                      # por ejemplo, "python_version" -- un único valor ACTUAL por subject
    text: str
    created_at: datetime              # cuándo lo escribió el sistema
    valid_from: datetime              # cuándo pasó a ser cierto (el tiempo simulado de la sesión)
    valid_to: datetime | None = None  # se setea en INVALIDATE; el registro se queda
    source_session: str
    importance: int = Field(default=5, ge=1, le=10)

class WriteDecision(BaseModel):
    # El razonamiento declarado primero, obligatorio, y con un nombre que también quede primero
    # ("analysis" < "decision" < "target_id" < "text"). Si la decisión se llamara "action", en un
    # servidor que escribe las claves en orden alfabético el modelo decidiría primero y
    # justificaría después.
    analysis: str = Field(max_length=400)
    decision: Literal["ADD", "UPDATE", "NOOP", "INVALIDATE"]
    target_id: str | None = None
    text: str | None = None

def score(recency: list[float], importance: list[float], relevance: list[float]) -> list[float]:
    def minmax(xs):
        if not xs:
            return []
        lo, hi = min(xs), max(xs)
        if hi - lo < 1e-6:   # Solo si es EXACTAMENTE constante. Un término casi constante (la recencia
            return [0.0] * len(xs)   # de reloj en una reproducción) igual se estira: imprimí antes cada rango.
        return [(x - lo) / (hi - lo) for x in xs]
    return [a + b + c for a, b, c in zip(minmax(recency), minmax(importance), minmax(relevance))]
```

**Guardá solo lo que querés conservar.** Una respuesta estructurada guardada entera lleva consigo
su campo `analysis`, y un escritor de memoria o un resumidor que conserva ese texto guarda
**hipótesis formuladas como hechos** -- "el usuario probablemente usa 3.11" -- que después
recupera como cosas que dijo el usuario. Guardá solo los campos del schema que querés conservar
(un schema también para los resúmenes), chequeá que ningún registro guardado contenga un análisis
o un bloque `<think>`, y reportá el conteo. El razonamiento también puede llegar al propio
`content`: se reportó que qwen3 filtra `</think>` ahí incluso con `think=False`, y la forma en que
las bibliotecas cliente y las versiones del servidor separan `thinking` de `content` fue cambiando
con el tiempo -- `llm.chat` saca y *cuenta* esas filtraciones, así que el conteo es una línea de tu
informe. Un costo relacionado sin ninguna filtración: un framework que no manda `think` deja que
el servidor *active* el thinking para qwen3, y cada llamada gasta en silencio tokens de salida en
un razonamiento que después se tira.

**Chequeá el rango antes de normalizar.** En una reproducción guionada el reloj casi no se mueve,
así que la recencia medida con el reloj es casi constante -- y min-max estira ese ruido a [0, 1],
donde pesa tanto como la relevancia. Usá los timestamps simulados del escenario, e imprimí el
rango de cada término.

**Declará el régimen.** Cada afirmación de "la memoria le gana / pierde contra el contexto
completo" dice si el historial entraba en la ventana, y con qué `num_ctx`.

**Preguntas para el informe:** ¿En qué habilidades la memoria le ganó a no tener memoria, y en
cuáles la reproducción le ganó a la memoria -- con qué costo en tokens? Mostrá una actualización
de conocimiento de punta a punta: qué se guardó, qué se invalidó, qué obtuvo la sonda. ¿Qué guardó
tu extractor que no era cierto, o que no se dijo? ¿Alguna memoria del usuario mejoró la
recuperación como filtro -- o la perjudicó? ¿En qué punto tu escenario deja de entrar en la
ventana, y qué cambia entonces?

---

### Etapa 7 · Una segunda lectura: juez y framework *(opcional, recomendada)*

**Por qué esta etapa.** Las dos partes son segundas lecturas de lo que construiste: una lee las
respuestas, la otra lee el diseño.

**7a · Un juez.** Para respuestas abiertas que la contención no puede puntuar. Dale al juez la
pregunta, la clave de respuesta y la respuesta como **campos separados y etiquetados**; incluí el
contexto recuperado *solo* cuando evalúes la fidelidad a él (si no, premiás ser fiel al pasaje
equivocado). Usá una rúbrica por tipo de ítem -- las reglas de LongMemEval para actualizaciones de
conocimiento y abstención son un buen punto de partida --, un veredicto estructurado, temperatura
0. **Auditá a mano al menos 30 juicios, o el 20%, lo que sea mayor**, y reportá la matriz de
confusión contra la contención y contra vos. Si el juez es el mismo modelo que el generador,
nombrá la autopreferencia; si podés, corré un juez de otra familia de modelos en una pasada
separada que lea tus respuestas guardadas (un modelo de 8B a la vez entra cómodo en una T4) -- y
agregá su tokenizer a `llm.HF_TOKENIZERS`, o los chequeos de contexto de `llm.chat` quedan
desactivados para él.

**7b · Un framework.** Reimplementá tu loop de las Etapas 5/6 en uno de estos: LangGraph (un
checkpointer para la memoria del hilo, un store para la memoria entre hilos), la `Memory` de
LlamaIndex con memory blocks, o el middleware de resumen de LangChain 1.x (no el deprecado
`ConversationBufferMemory`). Mapealo pieza por pieza con el tuyo, volvé a correr tus sondas, y
compará tokens y respuestas. Después nombrá **qué decidió el framework por vos**: cuándo resume,
qué guarda, su ventana por defecto, si manda `think` o no -- y si por defecto usó un modelo pago o
el endpoint `/v1` (y por lo tanto la ventana por defecto del servidor, 4.096 tokens en una T4).
`requirements-extras.txt` tiene versiones que se resuelven junto con las del núcleo; copiá las
líneas que uses a `requirements-group.txt`, que la primera celda de cada notebook instala.

**Un juez es un instrumento: calibralo antes de leerlo.** El puntaje promedio de un juez sin
calibrar es un número sobre el juez.

**Preguntas para el informe:** ¿Dónde el juez no coincidió con la contención y con tu auditoría, y
en cuál confiás? ¿Cuánto importa acá la autopreferencia, y cómo lo sabés? ¿Qué decidió el
framework por vos que vos habías decidido a mano -- y cambió tu presupuesto o tus resultados?

## 3b · Artefactos y traspasos

Cada etapa consume la salida de las anteriores, así que acuerden los nombres de archivo antes de
que alguien empiece -- sobre todo si reparten las etapas entre integrantes. Commiteá lo que es
chico y hecho a mano; regenerá lo que es grande, y verificalo al cargar. Los artefactos generados
viven en `artifacts/smoke/` o `artifacts/full/` (`environment.artifacts_dir(SMOKE_TEST)`), lo que
evita que un índice smoke se lea alguna vez como el real; `artifacts/` está en el gitignore, y en
Colab puede vivir en Drive.

| Artefacto | Lo escribe | Lo lee | ¿En git? |
|---|---|---|---|
| `corpus_card.md` | Etapas 0-1 | informe | commit |
| `artifacts/<profile>/documents.jsonl` + manifiesto (versión fijada de la fuente, conteos, hash del corpus) | Etapa 1 | Etapas 2, 3, 6 | no |
| `eval/single_turn.jsonl`, `eval/dialogues.jsonl`, `eval/scenarios.jsonl` | Etapa 2 | Etapas 3-7 | commit |
| `eval/FROZEN.json` | Etapa 2 (`schema.freeze_eval`) | cada etapa que calcula una métrica (`schema.load_eval`) | commit |
| `artifacts/<profile>/index/` -- chunks, BM25 y el manifiesto del índice | Etapa 3 | Etapas 3-6 | no |
| `artifacts/<profile>/embeddings/` (`store.cached_matrix(..., art_dir=ART)`) | Etapa 3 | Etapas 3-6 | no |
| `artifacts/<profile>/llm_cache/` (`llm.use_cache(ART / "llm_cache" / "qwen3_8b.jsonl")`) | Etapas 4-7 | las mismas etapas, al volver a correr | no |
| `artifacts/<profile>/results/*.jsonl` -- una fila por ítem por brazo (`store.ResultsLog`) | Etapas 3-7 | tablas, informe | va en el zip de la entrega |
| `artifacts/<profile>/memory/` -- el almacén de memoria y su log de operaciones | Etapa 6 | Etapas 6-7 | va en el zip |
| `artifacts/<profile>/run_report.json` | cada etapa (`console.StageRun`) | vos, y nosotros | va en el zip |
| `decision_log.md` | todas las etapas | quienes corrigen | commit |

**Procedencia.** Un índice sabe qué `documents.jsonl` (por hash) y qué embedder lo construyeron;
una fila de resultados sabe su configuración y el hash del conjunto de evaluación contra el que se
puntuó -- poné las dos cosas en el `run_spec` de `ResultsLog`, por ejemplo
`{"config": asdict(cfg), "eval": ev.key()}`, porque las filas tienen como clave ese hash y nada más
(`ev.key()` son los hashes congelados o, para el conjunto smoke sin congelar, un hash de sus filas
-- así un ítem smoke editado se recalcula, nunca se reanuda); una etapa que carga un artefacto
verifica su manifiesto y rechaza una discrepancia (`store.check_manifest`,
`schema.load_eval(..., documents_path=...)`), y se verifica que cada id gold esté en el índice
antes de calcular una sola métrica (`schema.validate_eval` los verifica contra los documentos; el
chequeo contra tu índice lo escribís vos). La forma más común de obtener una tabla equivocada es
puntuar un índice nuevo contra un conjunto de evaluación viejo, o un índice smoke contra el corpus
completo -- ningún error, solo números sobre otra cosa.

**Prerrequisitos duros**, para que sepas cuánto te cuesta un recorte: la Etapa 2 necesita los ids
de sección de la Etapa 1; la Etapa 3 necesita las Etapas 1 y 2; la Etapa 4 necesita *cualquier*
configuración de la Etapa 3; la Etapa 5 necesita el ensamblador de la Etapa 4 y los guiones de la
Etapa 2; la Etapa 6 necesita el *loop* de la Etapa 5 (no sus experimentos) y los escenarios de la
Etapa 2; la Etapa 7 necesita cualquier conjunto de respuestas guardadas. Las Etapas 1 y 2 alimentan
todo. **Recortá desde el final, no desde el medio.**

**Repartir el trabajo.** Después del congelamiento, cuatro líneas de trabajo pueden correr en
paralelo, cada una contra un stub de la anterior: la grilla de la Etapa 3; el ensamblador de la
Etapa 4 sobre un recuperador denso simple; el loop de la Etapa 5 sobre un primer borrador del
ensamblador; el almacén de la Etapa 6 sobre un primer borrador del loop. Enchufar después el mejor
recuperador cuesta volver a correr una vez -- presupuestalo.

## 4 · Entregables

Subí al campus **un solo zip** con:

- **Notebook(s)**, con sus salidas, que cubran las etapas que elegiste. Leemos las salidas: un
  notebook sin ellas no nos muestra nada.
- **Informe** (PDF, o markdown en un notebook): decisiones de diseño y su justificación; la
  ficha del corpus (*corpus card*); la descripción del conjunto de evaluación y su chequeo de
  contaminación; la tabla de la Etapa 3 con cotas de ruido; las filas de la Etapa 4 y la 2×2; la
  tabla de la Etapa 5A por dependencia y turno y el experimento de la Etapa 5B; los resultados de
  la Etapa 6 por habilidad; la auditoría del juez si la hiciste; y las respuestas a las preguntas
  de cada etapa. Más el párrafo sobre cómo usaste IA.
- **Registro de decisiones** (§2).
- **`eval/` con `FROZEN.json`, tu corpus card, y los resultados, la memoria y el
  `run_report.json` de `artifacts/<profile>/`**, para que podamos recalcular tus tablas.
  `store.pack_for_review(ART)` comprime la parte de `artifacts/<profile>/` sin las cachés
  pesadas; agregá vos `eval/`, `corpus_card.md` y `decision_log.md`.

No incluyas el corpus crudo, los embeddings ni las cachés de los modelos.

## 5 · Rúbrica

| Criterio | Qué se evalúa |
|---|---|
| **Priorización** | La calidad de los recortes hechos bajo una restricción real; la coherencia entre el presupuesto fijado al principio (tiempo, memoria de la T4, llamadas al LLM), lo que elegiste y lo que dice el registro de decisiones. |
| **Diseño experimental** | La vara de medir -- cómo se escribieron los ítems, el chequeo de contaminación, la granularidad del gold, congelada antes de ajustar; una variable por comparación; presupuestos igualados en tokens tal como los contó el servidor; una cota de ruido declarada antes de la afirmación. |
| **Comprensión conceptual** | Por qué está cada pieza y dónde actúa (offline / online, camino de escritura / camino de lectura, superficie de recuperación / superficie de generación); cómo compiten el corpus y la conversación por una sola ventana. |
| **Lectura de resultados** | Tablas leídas contra la cota de ruido; la caja abierta en los movimientos más grandes; "no llegó" distinguido de "llegó y no se usó"; el régimen declarado en cada afirmación sobre memoria. |
| **Contribución original** | Un hallazgo sobre datos sucios, una comparación o un modo de falla que nadie pidió, un vínculo con otro paper o con otra materia; una opinión que argumentás en lugar de reportar. |
| **Reproducibilidad y claridad** | Los notebooks corren a partir del conjunto de evaluación y la corpus card commiteados; los artefactos se regeneran o se verifican al cargar; los resultados por ítem nos permiten recalcular tus tablas; el informe es legible. |

**Cero puntos por tipear código.** Un proyecto que hace menos etapas, bien razonadas, le gana a
uno que las hace todas a medias -- y un proyecto con algo propio para decir les gana a los dos.

## 6 · Restricciones y logística

- **Solo código abierto, sin APIs pagas**: `sentence-transformers`, `bm25s` + PyStemmer,
  `transformers` (solo para tokenizers y plantillas de chat), numpy, pydantic, y Ollama corriendo
  `qwen3` localmente. LangChain / LangGraph / LlamaIndex / RAGAS son opcionales (Etapa 7). Todos
  los frameworks usan por defecto un modelo o un embedder pago cuando no decís otra cosa: declará
  explícitamente el LLM local, el embedder local y `num_ctx`. Un framework que te pide una API key
  eligió en silencio un valor por defecto.
- **Entorno de ejecución**: Google Colab, GPU T4 (nivel gratuito). Usá un flag `SMOKE_TEST` para
  iterar sobre un subconjunto mínimo antes de comprometerte con una corrida completa (§7).
- **Importá `environment` primero**, en cada notebook: entre otras cosas evita que JAX (que trae
  `bm25s`, y que Colab tiene instalado) reserve de antemano la mayor parte de la GPU en el momento
  en que se inicializa -- a lo que Ollama respondería corriendo el generador en silencio
  parcialmente en la CPU, varias veces más lento, sin ningún error.
- **Después de reiniciar el entorno de ejecución, chequeá dónde corre el modelo**
  (`llm.placement(model)` debería decir `100% GPU`). Un proceso del modelo que quedó huérfano de
  un entorno anterior puede conservar su VRAM a través de un reinicio; *Disconnect and delete
  runtime* (*Desconectar y borrar el entorno de ejecución*) lo libera.
- **Usá la API nativa y mandá `num_ctx` en cada llamada** (`llm.chat` lo hace). Fijá los tags de
  los modelos; nunca un `qwen3` a secas.
- **El disco de Colab es efímero -- planificá en consecuencia.** Cuando el entorno de ejecución se
  desconecta (unos 90 minutos inactivo, 12 horas como máximo en el nivel gratuito) todo lo que hay
  bajo `artifacts/` desaparece salvo que esté en Drive. Este es un trabajo de tres semanas; no lo
  vas a hacer en una sola sesión. Poné `USE_DRIVE = True` en la primera celda de cada notebook, y
  dejá que las etapas reusen lo que ya está construido. Los modelos en sí (unos 5 GB el
  generador, 3 GB el embedder y el reranker) se vuelven a descargar en cada VM nueva:
  presupuestá unos minutos para eso.
- **Llevar el código a Colab**: la primera celda de cada notebook clona el repo, hace `cd`
  adentro, trae los arreglos e instala los requirements. Para tu propio código, ver la sección
  "Trabajar desde el fork de tu grupo" del README.
- **Datos**: de [corpora.md](corpora.md), o los tuyos. Fijá la versión, respetá la licencia y su
  atribución, y nunca commitees los datos crudos.
- **Los escenarios de memoria son ficticios**: nada de datos personales reales en tus guiones.
- **Grupos**: hasta 4 integrantes.

## 7 · Guía de dimensionamiento

Rangos de partida -- elegí valores concretos que entren en tu presupuesto; esa elección es en sí
parte de lo que se evalúa. Son rangos, no metas; contá los tuyos en lugar de confiar en los
nuestros.

- **Subconjunto del corpus**: **no** tiene que entrar en la ventana, por un margen amplio -- de
  unos cientos de miles a unos pocos millones de tokens del generador (aproximadamente 50-300
  documentos largos, o unos pocos miles de posts o bloques de discurso) -- y tiene que incluir los
  vecinos confundibles que querés poner a prueba.
- **Hijos y padres**: hijos de 200-400 tokens en el tokenizer **del reranker**, prefijo incluido,
  con 10-20% de solapamiento -- y chequeá el par (consulta + hijo) más largo contra la ventana de
  512 tokens del reranker; padres = la unidad estructural, con un tope de alrededor de
  1.000-1.500 tokens del generador.
- **Embedder**: `BAAI/bge-m3` en fp16, `max_seq_length` 512-1.024. *Declara* 8.192, pero trunca
  en silencio en lo que sea que fijes; contá en su propio tokenizer. No usa prefijos de
  *instrucción* de consulta/pasaje (a diferencia de la familia e5) -- no confundir con el prefijo
  contextual de la Etapa 3, que es parte del texto del pasaje.
- **Reranker**: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (multilingüe), `max_length` 512,
  corrido sobre los hijos antes de subirlos a sus padres. Un reranker de MS MARCO solo en inglés
  empeora el español.
- **Primera etapa y entrega**: 30-100 candidatos por canal; RRF `k = 60`; entregá 1.500-5.000
  tokens del generador (o k = 3-8, y reportá los tokens).
- **Generador**: `qwen3:8b`, `think=False`, temperatura 0, un schema, un `num_ctx` explícito.
  **Por qué no el tag `qwen3:4b`**: en Ollama resuelve a Qwen3-4B-*Thinking*-2507, una versión
  solo-thinking -- no el hermano híbrido de `qwen3:8b` (ese es `qwen3:4b-q4_K_M`) -- así que
  `think=False` puede no hacer lo que esperás, y "4b vs 8b" pasa a comparar dos post-entrenamientos
  además de dos tamaños. Su caché KV cuesta exactamente lo mismo por token (la misma geometría 36
  × 8 × 128, ver abajo), así que el único contexto que compra es lo que liberan sus pesos ~2,7 GB
  más chicos. Uses el tag que uses, fijalo y verificalo con `llm.probe_thinking`.
- **La cuenta de `num_ctx`**: la caché KV de qwen3 cuesta unos 144 KiB por token en fp16 (36 capas
  × 8 cabezas KV × 128 dimensiones × 2 por K y V × 2 bytes) -- alrededor de 0,6 GB a 4.096, 1,2 GB
  a 8.192, 2,4 GB a 16.384 y 4,8 GB a 32.768 -- además de unos 5,2 GB de pesos y el buffer de
  cómputo que reserva el servidor. 8.192 es cómodo con el embedder y el reranker cargados; 16.384
  es posible; más es una decisión que hay que defender. Mantené `num_ctx` fijo dentro de un
  experimento.
- **Reserva de salida**: `num_predict` 256-768; prompt ≤ `num_ctx − num_predict`.
- **El experimento de la Etapa 5B**: `num_ctx` fijo (8.192), y dentro de él un total que imponés,
  dimensionado según tu historial y no según la ventana: el presupuesto de historial más chico
  debería ser una restricción real en la mayoría de los turnos puntuados. Los guiones reproducidos
  de a uno (unos pocos cientos de tokens de historial) no restringen nada por encima de eso;
  reproducidos uno detrás de otro (unos pocos miles de tokens hacia el final), un total de
  pasajes + historial de alrededor de 2.000-3.000 tokens hace que cada división restrinja en
  algún punto. El prompt de sistema (unos pocos cientos) y la memoria (0-1.000) van aparte. Mové
  un límite por vez.
- **Conjunto de evaluación**: un solo turno ≥ 30 (≥ 3 fuera del corpus; ≥ 5 de identificador
  donde tu corpus tenga identificadores; ≥ 5 de metadatos/temporales), gold a nivel de sección en
  todos los ítems con respuesta; 8-15 guiones de conversación de 3-6 turnos; 3-6 escenarios de
  memoria de 2-4 sesiones, 5-10 sondas cada uno, con al menos una actualización y un hecho nunca
  dicho por escenario.
- **Memoria**: recuperá 3-10 recuerdos por turno dentro de un espacio de memoria de 300-1.000
  tokens; resumí el historial alrededor del 70% de su presupuesto (la línea de advertencia de
  MemGPT); recencia de 0,995 por hora solo sobre timestamps simulados.
- **Juez**: veredictos estructurados; auditá ≥ 30 juicios o el 20%.
- **Llamadas al LLM**: contalas antes de correr (§2). A unos 10-20 segundos por respuesta
  fundamentada en una T4, 60 ítems × 3 brazos es del orden de una hora.
- **`SMOKE_TEST = True`**: los documentos gold de unas seis preguntas de un solo turno (una o dos
  por categoría) más una muestra con semilla de distractores; dos guiones de tres turnos; un
  escenario de dos sesiones con tres sondas -- guardados en `eval/smoke/` y cargados con
  `schema.load_eval("eval/smoke", require_frozen=False)`, así nunca tocan el conjunto congelado.
  Un embedder chico y un generador chico están bien (por ejemplo, `intfloat/multilingual-e5-small`,
  que espera los prefijos `"query: "` / `"passage: "`, y `qwen3:1.7b`; registrá cuáles en el
  manifiesto), y `num_ctx` puede ser más chico -- **siempre que cada presupuesto se derive de
  él**. Incluí **un prompt deliberadamente demasiado grande y un id gold deliberadamente
  faltante**, para ver saltar cada guarda. Sus números no significan nada -- existe para probar
  que el código corre y que las guardas funcionan.
- **Chequeos de cordura que no son metas**: el hit@k de documento al azar es de alrededor de k /
  (cantidad de documentos), y el piso real es tu fila solo-BM25; si a libro cerrado se responde la
  mitad de tus preguntas, tu conjunto está evaluando el preentrenamiento, no la recuperación;
  `prompt_eval_count` debería coincidir con la cuenta de tu plantilla con una diferencia de pocos
  tokens, y un valor menor significa truncamiento.
- **Reproducibilidad**: semillas para el muestreo y los bootstraps; temperatura 0; tags de modelos
  fijados, corpus fijados, el hash de `FROZEN.json`. Volvé a correr un puñado de llamadas: si las
  salidas varían, esa varianza es parte de tu piso de ruido.
