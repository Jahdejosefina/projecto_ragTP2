# Etapa 6 · memoria entre sesiones (full, split test)

Modelo `qwen3:8b` (digest 500a1f067a9f), num_ctx 8192, num_predict 700; pasajes ≤ 1500, memoria ≤ 600 (6 recuerdos), historial ≤ 3000. Embedder BAAI/bge-m3. Corrida `14e442282fc21efb`.

## Sondas correctas por habilidad

| habilidad | no_memory | full_replay | memory | memory_filter | replay_50 | replay_25 |
|---|---|---|---|---|---|---|
| extraction | 0/2 | 2/2 | 2/2 | 2/2 | 1/2 | 0/2 |
| multi_session | 2/4 | 4/4 | 4/4 | 4/4 | 2/4 | 2/4 |
| temporal | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 0/2 |
| knowledge_update | 0/6 | 6/6 | 6/6 | 6/6 | 5/6 | 0/6 |
| abstention | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| preference | 0/2 | 2/2 | 2/2 | 2/2 | 2/2 | 1/2 |
| total | 4/18 | 18/18 | 18/18 | 18/18 | 14/18 | 5/18 |

Pares p8+p9 correctos: {'no_memory': '0/2', 'full_replay': '2/2', 'memory': '2/2', 'memory_filter': '2/2', 'replay_50': '1/2', 'replay_25': '0/2'}.

## Costo por brazo

| brazo | correctas | recall de sesiones con evidencia | tokens de prompt (media) | memoria | historial | errores |
|---|---|---|---|---|---|---|
| no_memory | 4/18 | 0.0 | 1894 | 0 | 0 | 0 |
| full_replay | 18/18 | 1.0 | 2256 | 0 | 340 | 0 |
| memory | 18/18 | 1.0 | 2193 | 296 | 0 | 0 |
| memory_filter | 18/18 | 1.0 | 954 | 296 | 0 | 0 |
| replay_50 | 14/18 | 0.49 | 2031 | 0 | 127 | 0 |
| replay_25 | 5/18 | 0.062 | 1907 | 0 | 12 | 0 |

Camino de escritura: 14 llamadas y 7390 tokens de prompt en 6 sesiones.

Régimen: historial máximo 460 tokens; la reproducción completa dejaría de entrar a partir de ~21 sesiones de 142 tokens.

## Auditoría del almacén

{'records': 22, 'valid': 17, 'think_tag': 0, 'hedge': 0, 'analysis_leak': 0, 'unsaid_numbers': 0, 'think_leaks_llm': 0}

## Filtro por memoria

- m002/p7: sin filtro True (puesto 1); doc_id ['LEY-26043'] True (puesto 1); fecha ['2005-07-18'] -> ['LEY-26043'] True.
- m003/p7: sin filtro True (puesto 1); doc_id ['LEY-27521'] True (puesto 1); fecha ['2019-12-20'] -> ['DEC-50-2019', 'LEY-27521'] True.
