# Etapa 7a — Evaluación diagnóstica de jueces

Se comparan v1 y la variante v2 fijada en dev con los dos modelos originales. No se declara fiable a ninguno de los jueces.

Universo: 68 respuestas dev y 209 test; 4 dev y 7 test no factibles quedan excluidas. Auditoría humana: 30 dev y 42 test.

**Observación de anotación:** el caso test 12 conserva «correcto», aunque las fechas difieren. La tabla principal incluye las 42 marcas originales.

| Versión | Juez | Split | Acuerdo con humano | Inciertos | Entradas distintas |
|---|---|---|---:|---:|---:|
| v1 | qwen3:8b | dev | 60.0% de 30 | 0 | 54.5% de 11 |
| v1 | qwen3:8b | test | 90.5% de 42 | 0 | 92.6% de 27 |
| v1 | llama3.1:8b | dev | 60.0% de 30 | 0 | 54.5% de 11 |
| v1 | llama3.1:8b | test | 57.1% de 42 | 0 | 59.3% de 27 |
| v2 | qwen3:8b | dev | 70.0% de 30 | 0 | 63.6% de 11 |
| v2 | qwen3:8b | test | 78.6% de 42 | 0 | 81.5% de 27 |
| v2 | llama3.1:8b | dev | 66.7% de 30 | 0 | 72.7% de 11 |
| v2 | llama3.1:8b | test | 47.6% de 42 | 0 | 51.9% de 27 |

## v1 · qwen3:8b

### dev

Veredictos en 68 filas: {'incorrecto': 54, 'correcto': 14}.

Comparación con contención automática (todas las filas elegibles)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 38 | 0 |
| Correcta | 16 | 14 |

Acuerdo binario: 76.5% de 68. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparación con etiquetas humanas (muestra)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 10 | 0 |
| Correcta | 12 | 8 |

Acuerdo binario: 60.0% de 30. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparador trivial «siempre correcto»: 66.7% de 30.

### test

Veredictos en 209 filas: {'incorrecto': 112, 'correcto': 97}.

Comparación con contención automática (todas las filas elegibles)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 100 | 0 |
| Correcta | 12 | 97 |

Acuerdo binario: 94.3% de 209. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparación con etiquetas humanas (muestra)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 19 | 0 |
| Correcta | 4 | 19 |

Acuerdo binario: 90.5% de 42. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparador trivial «siempre correcto»: 54.8% de 42.

Vista complementaria sin el caso 12 señalado previamente (41 filas)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 19 | 0 |
| Correcta | 3 | 19 |

Acuerdo binario: 92.7% de 41. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

## v1 · llama3.1:8b

### dev

Veredictos en 68 filas: {'correcto': 57, 'incorrecto': 11}.

Comparación con contención automática (todas las filas elegibles)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 2 | 36 |
| Correcta | 9 | 21 |

Acuerdo binario: 33.8% de 68. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparación con etiquetas humanas (muestra)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 0 | 10 |
| Correcta | 2 | 18 |

Acuerdo binario: 60.0% de 30. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparador trivial «siempre correcto»: 66.7% de 30.

### test

Veredictos en 209 filas: {'incorrecto': 15, 'correcto': 194}.

Comparación con contención automática (todas las filas elegibles)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 15 | 85 |
| Correcta | 0 | 109 |

Acuerdo binario: 59.3% de 209. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparación con etiquetas humanas (muestra)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 2 | 17 |
| Correcta | 1 | 22 |

Acuerdo binario: 57.1% de 42. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparador trivial «siempre correcto»: 54.8% de 42.

Vista complementaria sin el caso 12 señalado previamente (41 filas)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 2 | 17 |
| Correcta | 0 | 22 |

Acuerdo binario: 58.5% de 41. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

## v2 · qwen3:8b

### dev

Veredictos en 68 filas: {'incorrecto': 53, 'correcto': 15}.

Comparación con contención automática (todas las filas elegibles)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 32 | 6 |
| Correcta | 21 | 9 |

Acuerdo binario: 60.3% de 68. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparación con etiquetas humanas (muestra)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 10 | 0 |
| Correcta | 9 | 11 |

Acuerdo binario: 70.0% de 30. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparador trivial «siempre correcto»: 66.7% de 30.

### test

Veredictos en 209 filas: {'incorrecto': 121, 'correcto': 88}.

Comparación con contención automática (todas las filas elegibles)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 100 | 0 |
| Correcta | 21 | 88 |

Acuerdo binario: 90.0% de 209. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparación con etiquetas humanas (muestra)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 19 | 0 |
| Correcta | 9 | 14 |

Acuerdo binario: 78.6% de 42. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparador trivial «siempre correcto»: 54.8% de 42.

Vista complementaria sin el caso 12 señalado previamente (41 filas)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 19 | 0 |
| Correcta | 8 | 14 |

Acuerdo binario: 80.5% de 41. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

## v2 · llama3.1:8b

### dev

Veredictos en 68 filas: {'correcto': 66, 'incorrecto': 2}.

Comparación con contención automática (todas las filas elegibles)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 2 | 36 |
| Correcta | 0 | 30 |

Acuerdo binario: 47.1% de 68. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparación con etiquetas humanas (muestra)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 0 | 10 |
| Correcta | 0 | 20 |

Acuerdo binario: 66.7% de 30. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparador trivial «siempre correcto»: 66.7% de 30.

### test

Veredictos en 209 filas: {'correcto': 170, 'incorrecto': 39}.

Comparación con contención automática (todas las filas elegibles)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 21 | 79 |
| Correcta | 18 | 91 |

Acuerdo binario: 53.6% de 209. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparación con etiquetas humanas (muestra)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 5 | 14 |
| Correcta | 8 | 15 |

Acuerdo binario: 47.6% de 42. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

Comparador trivial «siempre correcto»: 54.8% de 42.

Vista complementaria sin el caso 12 señalado previamente (41 filas)

| Referencia / juez | Incorrecta | Correcta |
|---|---:|---:|
| Incorrecta | 5 | 14 |
| Correcta | 7 | 15 |

Acuerdo binario: 48.8% de 41. Inciertos del juez: 0; etiquetas humanas ambiguas: 0.

## Alcance y límites

- Los jueces se conservan para diagnóstico; no fueron aprobados como correctores automáticos sin supervisión.
- La rúbrica v2 se fijó después de revisar dev y antes de anotar test; no se adapta usando resultados de test.
- La comparación humana usa las marcas explícitas de Alex: 30 filas de dev y 42 de test.
- El grupo test 12 conserva la marca correcto pese a la diferencia de fechas. Se señala y se informa una vista complementaria excluyéndolo, sin sustituir la marca.
- Las etiquetas son humanas; las síntesis de motivos son asistidas. Solo el motivo de test 14 fue escrito expresamente por Alex.
- La auditoría fue asistida; dev incluyó ejemplos explicados por el asistente antes de anotar.
- Las 42 filas de test representan 26 comparaciones mostradas y 27 prompts completos distintos. El grupo 11 reúne dos preguntas originales distintas con la misma comparación mostrada.
- Los prompts idénticos reutilizan veredictos; las filas no son observaciones independientes ni muestras de variabilidad del juez.
- La muestra humana incluye cobertura por tipo. Su porcentaje no es una estimación ponderada de precisión del corpus completo.
- La contención de claves se usa como comparador y no como verdad humana.
- Los puntajes de dev se leen como desarrollo; solo test comprueba el comportamiento de la variante ya fijada.
- Se evalúan respuestas guardadas de Etapa 5B, no Etapa 6, citas ni fidelidad a pasajes recuperados.
- Qwen comparte familia con el generador. La diferencia con Llama no identifica causalmente autopreferencia.
- Las 11 filas not_feasible se informan por separado; no reciben veredicto semántico.
- La Etapa 7b queda fuera de este reporte.
