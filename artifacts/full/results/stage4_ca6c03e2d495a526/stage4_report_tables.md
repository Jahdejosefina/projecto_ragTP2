# Etapa 4 · tablas (full, split test, n=23)

Modelo `qwen3:8b` (digest 500a1f067a9f), num_ctx 8192, num_predict 700, pasajes ≤ 2500 tokens. Corrida `ca6c03e2d495a526`; Etapa 3 `stage3_test`.

## Tres filas

| fila | correct (IC95) | con respuesta | abstención OOC | clave | veredicto | citó no entregado | citó gold | abst. con resp. en contexto | tokens pasajes | errores |
|---|---|---|---|---|---|---|---|---|---|---|
| closed_book | 9% (0%–22%) | 0% | 100% | 0% | 0% (n=1) | 0% | 0% | — | 0 | 0 |
| stage3_bm25 | 91% (78%–100%) | 90% | 100% | 90% | 100% (n=1) | 4% | 86% | 0% | 2,453 | 0 |
| oracle | 100% (100%–100%) | 100% | 100% | 100% | 100% (n=1) | 0% | 100% | 0% | 325 | 0 |

## 2×2 · stage3_bm25 (recuperó bien = sección gold entregada)

| | respondió bien | respondió mal |
|---|---|---|
| recuperó bien | 18 | 1 |
| recuperó mal | 1 | 1 |

Errores aparte: 0. Con "recuperó bien" = clave en el texto entregado: {'ret_ok_ans_ok': 19, 'ret_ok_ans_bad': 1, 'ret_bad_ans_ok': 0, 'ret_bad_ans_bad': 1, 'error': 0}.

## Comparaciones pareadas (correct)

| comparación | victorias | derrotas | empates | Δ | IC95 Δ | p (signos) |
|---|---|---|---|---|---|---|
| oracle vs stage3_bm25 | 2 | 0 | 21 | 9% | 0%–22% | 0.500 |
| stage3_bm25 vs closed_book | 19 | 0 | 4 | 83% | 65%–96% | 0.000 |
| oracle vs closed_book | 21 | 0 | 2 | 91% | 78%–100% | 0.000 |

## Números para las preguntas del informe

- Llegó la sección gold en 19 preguntas; se respondieron bien 18. Fallas: lo tenía, respondió otra cosa, se abstuvo.
- Brecha oráculo − stage3_bm25: 9%; stage3_bm25 − libro cerrado: 83%.
- Citó un pasaje no entregado: closed_book 0%; stage3_bm25 4%; oracle 0%.
- Se abstuvo con la respuesta en el contexto: stage3_bm25 0%; oracle 0%.
- Prompt demasiado grande: nuestra cuenta 11768, el servidor evaluó 4098 (num_ctx 8192); error `SILENT_TRUNCATION: the server evaluated 4098 prompt tokens, the template counts 11768; part of the prompt never reached the model`. Respuesta: «{"analysis": "La pregunta plantea si las características prometidas en una publicidad obligan al oferente, incluso si no se repiten en el contrato. Para responder, es necesario analizar el marco legal argentino, especialmente las leyes de contratación pública y publicidad comercial.", "answer": "Sí…»
- Reproducibilidad: 0/3 salidas idénticas al repetir sin caché; resultado cambiado en ninguna.

## Interpretación

(Escribila ustedes: qué leen en estos números y qué harían distinto.)
