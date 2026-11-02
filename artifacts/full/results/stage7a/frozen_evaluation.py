"""Orquestación y reporte; importa sin modificar los motores v1 y v2 fijados."""
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(baseline, engine, base_dir, cal_dir, output_base, freeze, provenance, audit_texts):
    base_dir, cal_dir = Path(base_dir), Path(cal_dir)
    require(sha(engine.__file__) == freeze['calibration_engine_sha256'], 'Cambió el motor v2 fijado.')
    require(hashlib.sha256(engine.RUBRIC.encode()).hexdigest() == freeze['rubric_sha256'], 'Cambió la rúbrica fijada.')
    require(engine.PARAMS == freeze['parameters'], 'Cambiaron los parámetros fijados.')
    require(engine.MODEL_TAGS == freeze['retained_models'], 'Cambiaron los jueces fijados.')
    require(sha(cal_dir / 'manifest.json') == freeze['calibration_manifest_sha256'], 'Cambió la corrida de calibración.')
    require(sha(cal_dir / 'stage7_calibration_engine.py') == freeze['calibration_engine_sha256'], 'Cambió el motor guardado de dev.')
    require(engine.read_json(cal_dir / 'decision_calibracion_dev.json') == freeze, 'Cambió la decisión previa a test.')
    manifest = engine.read_json(cal_dir / 'manifest.json')
    require(sha(base_dir / 'stage7_engine.py') == manifest['baseline_engine_sha256'] == sha(baseline.__file__), 'Cambió el motor v1.')
    require(sha(base_dir / 'entradas.jsonl') == engine.EXPECTED_ENTRIES_SHA256, 'Cambiaron las respuestas RAG guardadas.')
    rows = engine.load_journal(base_dir / 'entradas.jsonl')
    require(Counter(r['split'] for r in rows) == {'dev': 68, 'test': 209}, 'Cambió el universo de evaluación.')
    require(len({r['row_id'] for r in rows}) == len(rows), 'Hay identificadores repetidos.')
    excluded = engine.load_journal(base_dir / 'exclusiones.jsonl')
    require(Counter(r['split'] for r in excluded) == {'dev': 4, 'test': 7}, 'Cambiaron las exclusiones originales.')
    labels, audits = {}, {}
    for split in ('dev', 'test'):
        confirmed = list(csv.DictReader(io.StringIO(audit_texts[split])))
        actual = list(csv.DictReader(io.StringIO((base_dir / f'auditoria_{split}.csv').read_text(encoding='utf-8-sig'))))
        require(actual == confirmed, f'Cambió auditoria_{split}.csv. Actualizá el notebook para conservar la revisión más reciente.')
        require([r['row_id'] for r in actual] == engine.read_json(base_dir / f'muestra_{split}.json'), 'Cambió la muestra humana original.')
        labels[split], pending = engine.read_audit(base_dir, rows, split)
        require(not pending, f'Faltan etiquetas humanas de {split}.')
        audits[split] = actual
    lookup = {r['row_id']: r for r in rows}
    grouped_ids = []
    for group in provenance['groups']:
        for rid in group['row_ids']:
            require(labels['test'][rid] == group['human_correct'], 'La marca humana no coincide con su grupo.')
            row = lookup[rid]
            require((row['standalone_question'], row['reference_answer'], row['candidate_answer']) ==
                    (group['question'], group['reference'], group['candidate']), 'Cambió una comparación mostrada.')
            require(engine.digest(engine.messages_for(row)) in group['judge_prompt_hashes'], 'Cambió el prompt de un caso de test.')
            grouped_ids.append(rid)
    require(len(grouped_ids) == 42 and set(grouped_ids) == set(labels['test']), 'Mapeo humano incompleto o repetido.')
    dev_rows = [lookup[r['row_id']] for r in audits['dev']]
    original, seeds = {}, {}
    for model in engine.MODEL_TAGS:
        fp = freeze['model_fingerprints'][model]
        require(engine.read_json(engine.model_directory(cal_dir, model) / 'model.json') == fp, 'Cambió la identidad del juez de dev.')
        require(baseline.read_json(baseline.model_directory(base_dir, model) / 'model.json') == fp, 'Cambió la identidad del juez v1.')
        original[model] = baseline.completed_records(base_dir, model, rows)
        require(len(original[model]) == len(rows), 'La corrida v1 está incompleta.')
        seeds[model] = engine.completed_records(cal_dir, model, dev_rows)
        require(len(seeds[model]) == 30, 'La calibración v2 está incompleta.')
    spec = {
        'stage': '7a_frozen_diagnostic_evaluation', 'source_commit': engine.COMMIT,
        'baseline_directory': base_dir.name, 'calibration_directory': cal_dir.name,
        'engine_sha256': sha(engine.__file__), 'report_controller_sha256': sha(__file__),
        'freeze_sha256': engine.digest(freeze), 'rubric_sha256': freeze['rubric_sha256'],
        'parameters': engine.PARAMS, 'models': engine.MODEL_TAGS,
        'model_fingerprints': freeze['model_fingerprints'], 'source_sha256': sha(base_dir / 'entradas.jsonl'),
        'audit_sha256': {s: engine.digest(a) for s, a in audits.items()},
        'annotation_provenance_sha256': engine.digest(provenance),
        'scope': '277 respuestas guardadas: 68 dev y 209 test. Reutiliza 30 veredictos de dev por juez.',
        'acceptance': 'Diagnóstico; ningún juez fue aprobado como corrector sin supervisión.',
    }
    run = Path(output_base) / ('stage7a_frozen_v2_' + engine.digest(spec)[:12])
    run.mkdir(parents=True, exist_ok=True)
    engine.pin_manifest(run / 'manifest.json', spec)
    engine.write_json(run / 'decision_calibracion_dev.json', freeze)
    engine.write_json(run / 'registro_revision_test.json', provenance)
    engine.atomic_text(run / 'stage7_calibration_engine.py', Path(engine.__file__).read_text())
    engine.atomic_text(run / 'frozen_evaluation.py', Path(__file__).read_text())
    engine.atomic_text(run / 'rubrica_v2.txt', engine.RUBRIC)
    engine.atomic_text(run / 'entradas.jsonl', (base_dir / 'entradas.jsonl').read_text())
    engine.atomic_text(run / 'exclusiones.jsonl', (base_dir / 'exclusiones.jsonl').read_text())
    for split, audit in audits.items():
        engine.write_csv(run / f'auditoria_{split}.csv', audit, engine.AUDIT_FIELDS)
    for model, records in seeds.items():
        folder = engine.model_directory(run, model)
        engine.pin_manifest(folder / 'model.json', freeze['model_fingerprints'][model])
        existing = engine.completed_records(run, model, rows)
        for rid, record in records.items():
            if rid in existing:
                require(existing[rid] == record, 'Un veredicto dev fijado fue sustituido.')
            else:
                engine.append_jsonl(folder / 'veredictos.jsonl', record)
    unique = {engine.digest(engine.messages_for(r)) for r in rows}
    seeded = {engine.digest(engine.messages_for(r)) for r in dev_rows}
    print(f'Auditorías: {len(labels["dev"])} dev + {len(labels["test"])} test.')
    print(f'Entradas v2 distintas: {len(unique)}; {len(seeded)} ya evaluadas por cada juez.')
    print(f'Hasta {len(engine.MODEL_TAGS) * len(unique - seeded)} nuevas llamadas, más preflight y reintentos.')
    print('Caso 12: se conserva la marca humana correcto; la discrepancia de fechas se documenta.')
    print('Destino:', run)
    return run, rows, excluded, labels, original


def metric(engine, rows, records, references):
    triples = [(r, references[r['row_id']], records[r['row_id']]) for r in rows
               if r['row_id'] in references and r['row_id'] in records]
    pairs = [(ref, rec['judgment']['verdict']) for _, ref, rec in triples]
    result = engine.comparison(pairs)
    result['missing_judgments'] = sum(r['row_id'] in references for r in rows) - len(triples)
    unique = {}
    for _, ref, rec in triples:
        key = rec['prompt_hash']
        pair = (ref, rec['judgment']['verdict'])
        require(key not in unique or unique[key] == pair, 'Un prompt idéntico tiene etiquetas o veredictos incompatibles.')
        unique[key] = pair
    result['unique_inputs_view'] = engine.comparison(unique.values())
    for view in (result, result['unique_inputs_view']):
        tn, fp = view['matrix'][0]
        fn, tp = view['matrix'][1]
        view['recall_incorrect'] = tn / (tn + fp) if tn + fp else None
        view['recall_correct'] = tp / (tp + fn) if tp + fn else None
        view['balanced_accuracy'] = ((view['recall_incorrect'] + view['recall_correct']) / 2
                                    if tn + fp and tp + fn else None)
    return result


def display_metric(data):
    score = data['agreement_on_binary']
    return 'sin decisiones binarias' if score is None else f"{score:.1%} de {data['n_binary']}"


def matrix_lines(title, data):
    m = data['matrix']
    return [title, '', '| Referencia / juez | Incorrecta | Correcta |', '|---|---:|---:|',
            f'| Incorrecta | {m[0][0]} | {m[0][1]} |', f'| Correcta | {m[1][0]} | {m[1][1]} |', '',
            f"Acuerdo binario: {display_metric(data)}. Inciertos del juez: {data['judge_uncertain']}; "
            f"etiquetas humanas ambiguas: {data['reference_ambiguous']}.", '']


def finish(baseline, engine, run, base_dir, cal_dir, rows, excluded, labels, original, freeze, provenance):
    current = {model: engine.completed_records(run, model, rows) for model in engine.MODEL_TAGS}
    if any(len(records) != len(rows) for records in current.values()):
        print('Corrida parcial: ejecutá de nuevo para reanudar. No se genera un reporte completo.')
        return None
    variants = {'v1': original, 'v2': current}
    flagged = {rid for f in provenance['quality_flags'] for rid in f['row_ids']}
    results, exports, conditions = {}, [], []
    for version, by_model in variants.items():
        results[version] = {}
        for model, records in by_model.items():
            splits = {}
            for split in ('dev', 'test'):
                subset = [r for r in rows if r['split'] == split]
                counts = Counter(records[r['row_id']]['judgment']['verdict'] for r in subset)
                automatic = {r['row_id']: r['automatic_correct'] for r in subset}
                human = labels[split]
                values = {
                    'eligible': len(subset), 'excluded_source': sum(r['split'] == split for r in excluded),
                    'verdict_counts': dict(counts),
                    'judge_correct_fraction_all_eligible': counts['correcto'] / len(subset),
                    'vs_automatic': metric(engine, subset, records, automatic),
                    'vs_human': metric(engine, subset, records, human),
                    'audit_size': len(human), 'audit_human_label_counts': dict(Counter(human.values())),
                    'human_always_correct_baseline': engine.comparison([(v, 'correcto') for v in human.values()]),
                }
                if split == 'test':
                    values['vs_human_excluding_preflagged_case_12'] = metric(
                        engine, subset, records, {k: v for k, v in human.items() if k not in flagged})
                splits[split] = values
                for row in subset:
                    rid = row['row_id']
                    exports.append({**row, 'version': version, 'judge': model, **records[rid]['judgment'],
                                    'human_correct': human.get(rid, ''), 'annotation_flag': rid in flagged})
                for policy, fraction in sorted({(r['policy'], r['passage_fraction']) for r in subset}):
                    condition = [r for r in subset if (r['policy'], r['passage_fraction']) == (policy, fraction)]
                    c = Counter(records[r['row_id']]['judgment']['verdict'] for r in condition)
                    conditions.append({'version': version, 'judge': model, 'split': split, 'policy': policy,
                                       'passage_fraction': fraction, 'eligible': len(condition),
                                       'correcto': c['correcto'], 'incorrecto': c['incorrecto'], 'incierto': c['incierto'],
                                       'judge_correct_fraction': c['correcto'] / len(condition)})
            call_dirs = [base_dir] if version == 'v1' else [cal_dir, run]
            calls = [c for directory in call_dirs for c in engine.load_journal(engine.model_directory(directory, model) / 'llamadas.jsonl')]
            results[version][model] = {
                'by_split': splits, 'model': freeze['model_fingerprints'][model],
                'same_family_as_generator': model.startswith('qwen3'),
                'attempts_inference': len(calls),
                'usage_inference_excludes_preflight': {k: sum((c.get('usage') or {}).get(k) or 0 for c in calls)
                                                     for k in ('prompt_tokens', 'output_tokens', 'ms')},
                'usage_scope': 'v1 original' if version == 'v1' else 'v2 calibración dev más completado fijado',
            }
    disagreements = {}
    group_by_row = {rid: g['group'] for g in provenance['groups'] for rid in g['row_ids']}
    for model, records in current.items():
        for row in rows:
            rid = row['row_id']
            if rid not in labels['test']:
                continue
            expected = {'0': 'incorrecto', '1': 'correcto'}.get(labels['test'][rid])
            record = records[rid]['judgment']
            if record['verdict'] == expected:
                continue
            key = (model, group_by_row[rid], records[rid]['prompt_hash'],
                   original[model][rid]['judgment']['verdict'], record['verdict'])
            if key not in disagreements:
                disagreements[key] = {
                    'case': group_by_row[rid], 'row_ids': [], 'judge': model,
                    'question': row['standalone_question'], 'reference': row['reference_answer'],
                    'candidate': row['candidate_answer'], 'human_correct': labels['test'][rid],
                    'v1_verdict': original[model][rid]['judgment']['verdict'],
                    'v2_verdict': record['verdict'], 'v2_reason': record['analysis'],
                    'annotation_flag': rid in flagged,
                }
            disagreements[key]['row_ids'].append(rid)
    limitations = [
        'Los jueces se conservan para diagnóstico; no fueron aprobados como correctores automáticos sin supervisión.',
        'La rúbrica v2 se fijó después de revisar dev y antes de anotar test; no se adapta usando resultados de test.',
        'La comparación humana usa las marcas explícitas de Alex: 30 filas de dev y 42 de test.',
        'El grupo test 12 conserva la marca correcto pese a la diferencia de fechas. Se señala y se informa una vista complementaria excluyéndolo, sin sustituir la marca.',
        'Las etiquetas son humanas; las síntesis de motivos son asistidas. Solo el motivo de test 14 fue escrito expresamente por Alex.',
        'La auditoría fue asistida; dev incluyó ejemplos explicados por el asistente antes de anotar.',
        'Las 42 filas de test representan 26 comparaciones mostradas y 27 prompts completos distintos. El grupo 11 reúne dos preguntas originales distintas con la misma comparación mostrada.',
        'Los prompts idénticos reutilizan veredictos; las filas no son observaciones independientes ni muestras de variabilidad del juez.',
        'La muestra humana incluye cobertura por tipo. Su porcentaje no es una estimación ponderada de precisión del corpus completo.',
        'La contención de claves se usa como comparador y no como verdad humana.',
        'Los puntajes de dev se leen como desarrollo; solo test comprueba el comportamiento de la variante ya fijada.',
        'Se evalúan respuestas guardadas de Etapa 5B, no Etapa 6, citas ni fidelidad a pasajes recuperados.',
        'Qwen comparte familia con el generador. La diferencia con Llama no identifica causalmente autopreferencia.',
        'Las 11 filas not_feasible se informan por separado; no reciben veredicto semántico.',
        'La Etapa 7b queda fuera de este reporte.',
    ]
    report = {'stage': '7a', 'time': engine.utc(), 'status': 'diagnostic_report_with_annotation_flag',
              'calibration_declared_reliable': False, 'freeze_decision': freeze,
              'results': results, 'test_v2_disagreements': list(disagreements.values()),
              'annotation_quality_flags': provenance['quality_flags'], 'limitations': limitations}
    engine.write_json(Path(run) / 'reporte_etapa7a.json', report)
    fields = ['version', 'judge', 'row_id', 'split', 'policy', 'passage_fraction', 'type',
              'standalone_question', 'reference_answer', 'candidate_answer', 'automatic_correct',
              'verdict', 'error_type', 'analysis', 'human_correct', 'annotation_flag']
    engine.write_csv(Path(run) / 'resultados_comparados.csv', exports, fields)
    engine.write_csv(Path(run) / 'resultados_por_condicion.csv', conditions, list(conditions[0]))
    lines = ['# Etapa 7a — Evaluación diagnóstica de jueces', '',
             'Se comparan v1 y la variante v2 fijada en dev con los dos modelos originales. '
             'No se declara fiable a ninguno de los jueces.', '',
             'Universo: 68 respuestas dev y 209 test; 4 dev y 7 test no factibles quedan excluidas. '
             'Auditoría humana: 30 dev y 42 test.', '',
             '**Observación de anotación:** el caso test 12 conserva «correcto», aunque las fechas difieren. '
             'La tabla principal incluye las 42 marcas originales.', '',
             '| Versión | Juez | Split | Acuerdo con humano | Inciertos | Entradas distintas |',
             '|---|---|---|---:|---:|---:|']
    for version, by_model in results.items():
        for model, data in by_model.items():
            for split, v in data['by_split'].items():
                h = v['vs_human']
                lines.append(f"| {version} | {model} | {split} | {display_metric(h)} | {h['judge_uncertain']} | {display_metric(h['unique_inputs_view'])} |")
    lines.append('')
    for version, by_model in results.items():
        for model, data in by_model.items():
            lines.extend([f'## {version} · {model}', ''])
            for split, v in data['by_split'].items():
                lines.extend([f'### {split}', '', f"Veredictos en {v['eligible']} filas: {v['verdict_counts']}.", ''])
                lines += matrix_lines('Comparación con contención automática (todas las filas elegibles)', v['vs_automatic'])
                lines += matrix_lines('Comparación con etiquetas humanas (muestra)', v['vs_human'])
                lines.append(f"Comparador trivial «siempre correcto»: {display_metric(v['human_always_correct_baseline'])}.")
                lines.append('')
                if split == 'test':
                    lines += matrix_lines('Vista complementaria sin el caso 12 señalado previamente (41 filas)',
                                          v['vs_human_excluding_preflagged_case_12'])
    lines.extend(['## Alcance y límites', ''] + ['- ' + item for item in limitations])
    engine.atomic_text(Path(run) / 'reporte_etapa7a.md', '\n'.join(lines) + '\n')
    log = [
        '# Decision log — Etapa 7a', '',
        'Se auditó dev con 30 marcas humanas, correspondientes a 11 entradas distintas. '
        'La versión inicial tuvo 60 % de acuerdo con Alex para ambos jueces.', '',
        'Se creó v2 con una referencia y una respuesta evaluada explícitamente separadas, '
        'y reglas más claras para abstenciones, información central y agregados. '
        'Qwen alcanzó 70 % y Llama 66,7 % en dev. Llama marcó correctas las 30 filas, '
        'por lo que ese porcentaje coincide con el comparador trivial.', '',
        'Se fijó v2 antes de revisar test y se conservaron ambos jueces para diagnóstico. '
        'Se rechazó interpretar sus puntajes como una verdad automática o seguir ajustando sobre los mismos 11 casos.', '',
        'Alex etiquetó las 26 comparaciones mostradas de test, mapeadas a las 42 filas originales. '
        'Se preservaron todas sus marcas, incluida la discrepancia de fechas del caso 12. '
        'La vista que excluye ese caso fue especificada antes de comparar veredictos de test.', '',
        'La ejecución completa reutiliza los 30 veredictos v2 de dev por juez y evalúa las filas restantes '
        'con los mismos modelos, tokenizers, rúbrica y parámetros. No vuelve a generar respuestas RAG.', '',
        'Los resultados y matrices están en reporte_etapa7a.md y reporte_etapa7a.json. '
        'No se alteró el decision_log del repositorio ni se implementó la Etapa 7b.',
    ]
    engine.atomic_text(Path(run) / 'decision_log_etapa7.md', '\n'.join(log) + '\n')
    print('\nVersión | Juez | Split | Acuerdo humano (filas) | Inciertos | Entradas distintas')
    for version, by_model in results.items():
        for model, data in by_model.items():
            for split, v in data['by_split'].items():
                h = v['vs_human']
                print(f"{version} | {model} | {split} | {display_metric(h)} | {h['judge_uncertain']} | {display_metric(h['unique_inputs_view'])}")
    print('\nMatrices v2 de test: filas=humano incorrecto/correcto; columnas=juez incorrecto/correcto.')
    for model in engine.MODEL_TAGS:
        v = results['v2'][model]['by_split']['test']
        print(model, json.dumps(v['vs_human']['matrix']), '| Siempre correcto:', display_metric(v['human_always_correct_baseline']))
        print('  Sin el caso 12 señalado:', display_metric(v['vs_human_excluding_preflagged_case_12']))
    print('\nDesacuerdos v2 de test (numeración de las 26 comparaciones mostradas):')
    print(json.dumps(list(disagreements.values()), ensure_ascii=False, indent=2))
    print('\nReporte diagnóstico generado. Caso 12 señalado; no se cambió su etiqueta.')
    print('Copiá la tabla, las matrices y los desacuerdos al chat. No ajustes la rúbrica con test.')
    print('Carpeta:', run)
    return report
