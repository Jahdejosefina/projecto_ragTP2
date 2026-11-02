# Decision log — Etapa 7a

Se auditó dev con 30 marcas humanas, correspondientes a 11 entradas distintas. La versión inicial tuvo 60 % de acuerdo con Alex para ambos jueces.

Se creó v2 con una referencia y una respuesta evaluada explícitamente separadas, y reglas más claras para abstenciones, información central y agregados. Qwen alcanzó 70 % y Llama 66,7 % en dev. Llama marcó correctas las 30 filas, por lo que ese porcentaje coincide con el comparador trivial.

Se fijó v2 antes de revisar test y se conservaron ambos jueces para diagnóstico. Se rechazó interpretar sus puntajes como una verdad automática o seguir ajustando sobre los mismos 11 casos.

Alex etiquetó las 26 comparaciones mostradas de test, mapeadas a las 42 filas originales. Se preservaron todas sus marcas, incluida la discrepancia de fechas del caso 12. La vista que excluye ese caso fue especificada antes de comparar veredictos de test.

La ejecución completa reutiliza los 30 veredictos v2 de dev por juez y evalúa las filas restantes con los mismos modelos, tokenizers, rúbrica y parámetros. No vuelve a generar respuestas RAG.

Los resultados y matrices están en reporte_etapa7a.md y reporte_etapa7a.json. No se alteró el decision_log del repositorio ni se implementó la Etapa 7b.
