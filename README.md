# Retrieval & Memory Lab

<!-- ENCABEZADO POR INSTANCIA — editá esta línea al reutilizar el lab en otro curso. -->

**IA Generativa Avanzada y Sistemas Multi-Agente** — Licenciatura en Tecnología Digital,
Universidad Torcuato Di Tella.

Un proyecto evaluado del curso. Construís un asistente con recuperación aumentada (RAG) **con memoria**
sobre un corpus que elegís y limpiás vos, y medís -- en una T4 gratuita de Colab, solo con
modelos abiertos -- cómo conviene repartir una ventana de contexto finita entre lo que dice el
corpus y lo que se dijo en la conversación.

## Empezá por acá
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/solidgoldmagickarp/projecto_rag/blob/master/00_corpus_audit.ipynb)

- **[assignment.md](assignment.md)** — el enunciado: la idea, ocho etapas, las trampas, las
  preguntas para tu informe y la rúbrica (§5).
- **[corpora.md](corpora.md)** — el menú de corpus (cinco opciones, o traé el tuyo).
- **`00_corpus_audit`** — la Etapa 0 resuelta, una auditoría de uno de los corpus del menú.
  Corrélo primero; también es el smoke test de tu entorno.

## Puesta en marcha

### En Colab (el entorno de destino)

El orden importa:

1. **Elegí el entorno de ejecución primero** — *Runtime → Change runtime type → T4 GPU* (en la
   interfaz en español: *Entorno de ejecución → Cambiar tipo de entorno de ejecución*).
   Cambiarlo después reemplaza la VM y borra todo lo que hizo el paso siguiente.
2. **Guardá una copia en Drive** — *File → Save a copy in Drive* (*Archivo → Guardar una copia
   en Drive*). El notebook que abriste desde GitHub es de solo lectura.
3. **Corré la primera celda.** Clona este repositorio, hace `cd` adentro, instala los
   requirements (una vez por VM) y, si ponés `USE_DRIVE = True` en ella, mantiene `artifacts/`
   en tu Google Drive. Todos los imports que vienen después dependen de ella.

Si ves `ModuleNotFoundError: No module named 'environment'`, el entorno de ejecución se
reinició: volvé a correr la primera celda.

> **El disco de Colab se borra cuando se desconecta el entorno de ejecución** (unos 90 minutos
> inactivo, 12 horas como máximo). Tu índice, tus resultados y tu caché del LLM viven en
> `artifacts/`. Activá `USE_DRIVE` en la primera celda de cada notebook el primer día, no el último.

El LLM corre en **Ollama** dentro de la VM de Colab. `llm.setup("qwen3:8b", num_ctx=8192)` lo
instala, lo levanta, descarga el modelo y lo prueba (unos minutos en una VM nueva);
`00_corpus_audit` lo llama en Colab para su chequeo a libro cerrado, y tus etapas que llamen al
modelo también deberían hacerlo.

### En Colab desde VS Code (la extensión de Colab de Google)

Los mismos notebooks corren en una T4 de Colab desde VS Code: abrí el `.ipynb`, después *Select
Kernel → Colab → New Colab Server* y elegí la T4. Las salidas se guardan en tu archivo de notebook
local. Dos diferencias respecto del navegador:

- **Drive**: `drive.mount()` desde una celda no funciona ahí. Con `USE_DRIVE = True`, montalo
  antes con el comando *Colab: Mount Google Drive to Server...* (`Ctrl+Shift+P`), para el
  servidor que usa este notebook; después la primera celda lo encuentra.
- **Los secretos de Colab** no se pueden leer, así que el secreto `GITHUB_TOKEN` de un fork
  privado es más fácil de usar desde el navegador.

El entorno de ejecución sigue corriendo solo mientras VS Code esté conectado: para corridas
largas, no dejes que la computadora entre en suspensión.

### Localmente (para corridas `SMOKE_TEST` en CPU)

```bash
git clone https://github.com/solidgoldmagickarp/retrieval_memory_lab.git
cd retrieval_memory_lab

python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows (PowerShell)
# source .venv/bin/activate         # Linux / macOS

pip install -r requirements.txt
python verify_setup.py
```

Para las etapas que llaman al LLM, instalá Ollama desde <https://ollama.com/download> y descargá
un modelo chico para las corridas smoke (`ollama pull qwen3:1.7b`); después `python
verify_setup.py --model qwen3:1.7b` lo verifica de punta a punta.

Si las descargas fallan con `CERTIFICATE_VERIFY_FAILED` detrás de un proxy corporativo o del
campus, corré `python tools/ca_bundle_windows.py` una vez (Windows): arma un bundle de
certificados que `environment.py` toma automáticamente. La verificación sigue activa.

Corré todas las etapas desde la raíz del repo.

## Trabajar desde el fork de tu grupo

Los notebooks clonan *este* repositorio. Tu propio código también tiene que llegar a Colab:

- **Hacé un fork**, o -- para que tu trabajo sea privado -- creá un repositorio *privado* nuevo
  y subile una copia de este (un fork de un repositorio público es público, y GitHub no te deja
  cambiarlo). Un repositorio privado necesita un token de GitHub como secreto de Colab llamado
  `GITHUB_TOKEN` (alcanza con acceso de lectura al contenido del repositorio). Poné tu
  repositorio en `REPO_URL` de `tools/py_to_notebook.py` y regenerá los notebooks
  (`python tools/py_to_notebook.py`). A partir de ahí la primera celda lo clona y hace `git pull`
  de tus últimos commits cada vez que se corre -- con el token, si es privado.
- Las dependencias extra van en **`requirements-group.txt`** en la raíz del repo; si existe, la
  primera celda lo instala junto con `requirements.txt`. Copiá ahí el bloque de tu corpus de
  `requirements-corpora.txt` y, para la Etapa 7b, las líneas de `requirements-extras.txt` que
  uses: nada más las instala.
- Nombrá los archivos de tus etapas `01_documents.py`, `02_eval_set.py`, `03_retrieval.py`,
  `04_grounded_answers.py`, `05_conversation.py`, `06_memory.py`, `07_second_read.py` (los
  nombres que buscan `tools/py_to_notebook.py` y `tools/run_stages.py`), o convertí otros
  con `python tools/py_to_notebook.py --source tuyo.py`.
- O dejá todo dentro de tus notebooks. Cualquiera de las dos está bien; decí cuál en tu informe.

## Qué hay acá

| Ruta | Qué es |
|---|---|
| [assignment.md](assignment.md) | **El enunciado.** |
| [corpora.md](corpora.md) | El menú de corpus: acceso, versiones fijadas, licencias y la tarea de datos sucios de cada corpus. |
| `00_corpus_audit.py` | La Etapa 0, resuelta: una auditoría medida de python-docs-es. |
| `environment.py` | Se importa primero: guarda de JAX, caché de HF local al repo, bundle TLS, UTF-8, directorios de artefactos, helpers de GPU. |
| `llm.py` | Ollama: instalar/levantar/descargar en Colab, una llamada de chat con `num_ctx` explícito que reporta qué hizo el servidor con tu prompt, salida estructurada, una caché de llamadas. |
| `schema.py` | El contrato de artefactos: documentos, ítems de evaluación, guiones de conversación, escenarios de memoria, filas de resultados -- más validación, congelamiento y chequeos al cargar. |
| `store.py` | Disco: JSONL, hashes, manifiestos verificados al cargar, construir-o-reusar, una caché de embeddings reanudable, resultados por ítem reanudables, descargas fijadas. |
| `console.py` | Tablas, cadenas de veredicto y el `run_report.json` de cada etapa. |
| `requirements*.txt` | Versiones fijadas del núcleo, parsers por corpus, frameworks opcionales. |
| `tools/py_to_notebook.py` | Regenera el `.ipynb` de cada etapa a partir de su `.py`. |
| `tools/check_repo.py` | Chequeos de higiene antes de commitear (rechaza notebooks con salidas: commiteá el `.py` y los notebooks limpios; los notebooks *con* salidas van en el zip de la entrega). |
| `tools/run_stages.py` | Corre en orden los `.py` de las etapas, localmente. |
| `tools/ca_bundle_windows.py` | Arregla fallas de TLS detrás de un proxy que inspecciona el tráfico. |
| `verify_setup.py` | Chequeo del entorno. |

## Qué escribís vos

Este repositorio te da la plomería y una Etapa 0 resuelta sobre un corpus. **Tu Etapa 0 y las
Etapas 1–7 son tuyas**: los documentos, el conjunto de evaluación, el pipeline de recuperación,
la generación de respuestas, el loop de conversación y la memoria. `assignment.md` tiene
fragmentos de código adaptables para cada etapa y, en §3b, los nombres de archivo con los que
las etapas se pasan los artefactos. Los módulos auxiliares son infraestructura: mueven
archivos, cuentan tokens y hablan con el servidor -- ninguno toma una decisión de diseño por vos.

## Créditos y licencia

Se apoya en material previo del curso sobre embeddings, generación aumentada por recuperación,
prompting y salidas estructuradas, y evaluación con LLM como juez. Los corpus se descargan al
momento de correr, nunca se incluyen en el repo; ver [corpora.md](corpora.md) para sus licencias.

MIT License — ver [LICENSE](LICENSE). Copyright (c) 2026 Francisco Traversaro.
