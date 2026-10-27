# Escenarios de memoria

## m001 — Clara, persona completamente ficticia que consulta documentación normativa sobre consumo.

### Sesión s1 (2026-09-01T10:00:00)
- **Usuario:** Soy Clara. Compré un curso de fotografía con material impreso enviado a domicilio en Academia Ejemplo Alfa y pagué 120000 pesos por el curso y el material. Mi canal preferido de contacto es el teléfono.
- **Asistente:** Registrado: compra en Academia Ejemplo Alfa, precio de 120000 pesos y contacto por teléfono.
- **Usuario:** Para mis próximas consultas sobre normativa, usá el documento LEY-24806 de nuestro corpus. Su fecha de publicación registrada es 1997-05-13. Por ahora prefiero respuestas en un párrafo.
- **Asistente:** Tomaré como referencia LEY-24806, con fecha registrada 1997-05-13, y responderé en un párrafo.
### Sesión s2 (2026-09-08T10:00:00)
- **Usuario:** Sobre aquella compra: además del curso y el material, pagué 3000 pesos por el envío del material impreso. No hubo otros gastos.
- **Asistente:** El envío costó 3000 pesos adicionales.
- **Usuario:** Cambio mi preferencia de contacto: ahora prefiero el correo electrónico, no el teléfono.
- **Asistente:** Tu canal preferido actual pasa a ser el correo electrónico.
### Sesión s3 (2026-09-15T10:00:00)
- **Usuario:** También cambio el formato de las respuestas: a partir de ahora quiero listas con viñetas, en lugar de un párrafo.
- **Asistente:** Usaré listas con viñetas.
#### p1 · extraction (tras s1)
¿En qué academia te dije que compré el curso?
**Evidencia sesiones:** ['s1']
**Clave/veredicto:** ['Academia Ejemplo Alfa'] / None
**Gold corpus, si aplica:** []

#### p2 · multi_session (tras s2)
Sumando la compra y el envío que te conté en nuestras conversaciones, ¿cuánto pagué en total?
**Evidencia sesiones:** ['s1', 's2']
**Clave/veredicto:** ['123000', '123.000', '123 000'] / None
**Gold corpus, si aplica:** []

#### p3 · temporal (tras s2)
Antes de cambiar mi preferencia de contacto, ¿qué canal había elegido?
**Evidencia sesiones:** ['s1', 's2']
**Clave/veredicto:** ['teléfono', 'telefónico'] / None
**Gold corpus, si aplica:** []

#### p4 · knowledge_update (tras s2)
¿Cuál es mi canal de contacto preferido ahora?
**Evidencia sesiones:** ['s1', 's2']
**Clave/veredicto:** ['correo electrónico', 'email', 'e-mail'] / None
**Gold corpus, si aplica:** []

#### p5 · preference (tras s3)
¿Qué formato te pedí que uses ahora para responderme?
**Evidencia sesiones:** ['s3']
**Clave/veredicto:** ['viñetas'] / None
**Gold corpus, si aplica:** []

#### p6 · abstention (tras s3)
¿Cuál es el número de pedido de mi compra?
**Evidencia sesiones:** []
**Clave/veredicto:** None / None
**Gold corpus, si aplica:** []

#### p7 · multi_session (tras s3)
En la norma educativa que te pedí usar, ¿qué número relacionado con la aprobación de una carrera o curso debe informar una institución reconocida oficialmente cuando hace publicidad?
**Evidencia sesiones:** ['s1']
**Clave/veredicto:** ['número de resolución', 'numero de resolución', 'resolución'] / None
**Gold corpus, si aplica:** [{'doc_id': 'LEY-24806', 'section_id': 'LEY-24806#ART-1'}]

#### p8 · knowledge_update (tras s1)
¿Mi canal de contacto preferido es el teléfono?
**Evidencia sesiones:** ['s1']
**Clave/veredicto:** None / yes
**Gold corpus, si aplica:** []

#### p9 · knowledge_update (tras s2)
¿Mi canal de contacto preferido es el teléfono?
**Evidencia sesiones:** ['s1', 's2']
**Clave/veredicto:** None / no
**Gold corpus, si aplica:** []

## m002 — Mateo, persona completamente ficticia que consulta documentación normativa sobre consumo.

### Sesión s1 (2026-09-01T10:00:00)
- **Usuario:** Soy Mateo. Compré un videojuego en formato físico en Tienda Ejemplo Beta y pagué 85000 pesos por el producto. Mi canal preferido de contacto es el teléfono.
- **Asistente:** Registrado: compra en Tienda Ejemplo Beta, precio de 85000 pesos y contacto por teléfono.
- **Usuario:** Para mis próximas consultas sobre normativa, usá el documento LEY-26043 de nuestro corpus. Su fecha de publicación registrada es 2005-07-18. Por ahora prefiero respuestas en un párrafo.
- **Asistente:** Tomaré como referencia LEY-26043, con fecha registrada 2005-07-18, y responderé en un párrafo.
### Sesión s2 (2026-09-08T10:00:00)
- **Usuario:** Sobre aquella compra: además del producto, pagué 4500 pesos por el envío. No hubo otros gastos.
- **Asistente:** El envío costó 4500 pesos adicionales.
- **Usuario:** Cambio mi preferencia de contacto: ahora prefiero el correo electrónico, no el teléfono.
- **Asistente:** Tu canal preferido actual pasa a ser el correo electrónico.
### Sesión s3 (2026-09-15T10:00:00)
- **Usuario:** También cambio el formato de las respuestas: a partir de ahora quiero listas con viñetas, en lugar de un párrafo.
- **Asistente:** Usaré listas con viñetas.
#### p1 · extraction (tras s1)
¿En qué tienda te dije que hice la compra?
**Evidencia sesiones:** ['s1']
**Clave/veredicto:** ['Tienda Ejemplo Beta'] / None
**Gold corpus, si aplica:** []

#### p2 · multi_session (tras s2)
Sumando el producto y el envío que te conté en nuestras conversaciones, ¿cuánto pagué en total?
**Evidencia sesiones:** ['s1', 's2']
**Clave/veredicto:** ['89500', '89.500', '89 500'] / None
**Gold corpus, si aplica:** []

#### p3 · temporal (tras s2)
Antes de cambiar mi preferencia de contacto, ¿qué canal había elegido?
**Evidencia sesiones:** ['s1', 's2']
**Clave/veredicto:** ['teléfono', 'telefónico'] / None
**Gold corpus, si aplica:** []

#### p4 · knowledge_update (tras s2)
¿Cuál es mi canal de contacto preferido ahora?
**Evidencia sesiones:** ['s1', 's2']
**Clave/veredicto:** ['correo electrónico', 'email', 'e-mail'] / None
**Gold corpus, si aplica:** []

#### p5 · preference (tras s3)
¿Qué formato te pedí que uses ahora para responderme?
**Evidencia sesiones:** ['s3']
**Clave/veredicto:** ['viñetas'] / None
**Gold corpus, si aplica:** []

#### p6 · abstention (tras s3)
¿Cuál es el número de pedido de mi compra?
**Evidencia sesiones:** []
**Clave/veredicto:** None / None
**Gold corpus, si aplica:** []

#### p7 · multi_session (tras s3)
Según la norma que te indiqué para mis consultas, ¿qué advertencia sanitaria debe llevar el envase del videojuego?
**Evidencia sesiones:** ['s1']
**Clave/veredicto:** ['la sobreexposición es perjudicial para la salud'] / None
**Gold corpus, si aplica:** [{'doc_id': 'LEY-26043', 'section_id': 'LEY-26043#ART-1'}, {'doc_id': 'LEY-26043', 'section_id': 'LEY-26043#intro'}]

#### p8 · knowledge_update (tras s1)
¿Mi canal de contacto preferido es el teléfono?
**Evidencia sesiones:** ['s1']
**Clave/veredicto:** None / yes
**Gold corpus, si aplica:** []

#### p9 · knowledge_update (tras s2)
¿Mi canal de contacto preferido es el teléfono?
**Evidencia sesiones:** ['s1', 's2']
**Clave/veredicto:** None / no
**Gold corpus, si aplica:** []

## m003 — Inés, persona completamente ficticia que consulta documentación normativa sobre consumo.

### Sesión s1 (2026-09-01T10:00:00)
- **Usuario:** Soy Inés. Compré una campera en Indumentaria Ejemplo Gamma y pagué 64000 pesos por el producto. Mi canal preferido de contacto es el teléfono.
- **Asistente:** Registrado: compra en Indumentaria Ejemplo Gamma, precio de 64000 pesos y contacto por teléfono.
- **Usuario:** Para mis próximas consultas sobre normativa, usá el documento LEY-27521 de nuestro corpus. Su fecha de publicación registrada es 2019-12-20. Por ahora prefiero respuestas en un párrafo.
- **Asistente:** Tomaré como referencia LEY-27521, con fecha registrada 2019-12-20, y responderé en un párrafo.
### Sesión s2 (2026-09-08T10:00:00)
- **Usuario:** Tengo que corregir un dato de mi compra: la campera costó 69000 pesos, no 64000. El precio que te había dicho antes era incorrecto.
- **Asistente:** Entendido. El precio correcto de la campera es 69000 pesos. Reemplazo el importe anterior.
- **Usuario:** Cambio mi preferencia de contacto: ahora prefiero el correo electrónico, no el teléfono.
- **Asistente:** Tu canal preferido actual pasa a ser el correo electrónico.
### Sesión s3 (2026-09-15T10:00:00)
- **Usuario:** Además de los 69000 pesos de la campera, pagué 2500 pesos de envío. No hubo otros gastos. A partir de ahora quiero respuestas con viñetas, no en un párrafo.
- **Asistente:** Registrado: 2500 pesos de envío, 71500 pesos en total y respuestas con viñetas.
#### p1 · extraction (tras s1)
¿En qué tienda te dije que hice la compra?
**Evidencia sesiones:** ['s1']
**Clave/veredicto:** ['Indumentaria Ejemplo Gamma'] / None
**Gold corpus, si aplica:** []

#### p2 · multi_session (tras s3)
Considerando el precio corregido y el envío, ¿cuánto terminé pagando por la compra?
**Evidencia sesiones:** ['s1', 's2', 's3']
**Clave/veredicto:** ['71500', '71.500', '71 500'] / None
**Gold corpus, si aplica:** []

#### p3 · temporal (tras s2)
¿Qué precio te había dicho inicialmente antes de corregirlo?
**Evidencia sesiones:** ['s1', 's2']
**Clave/veredicto:** ['64000', '64.000', '64 000'] / None
**Gold corpus, si aplica:** []

#### p4 · knowledge_update (tras s2)
¿Cuál es el precio correcto de la campera ahora?
**Evidencia sesiones:** ['s1', 's2']
**Clave/veredicto:** ['69000', '69.000', '69 000'] / None
**Gold corpus, si aplica:** []

#### p5 · preference (tras s3)
¿Qué formato te pedí que uses ahora para responderme?
**Evidencia sesiones:** ['s3']
**Clave/veredicto:** ['viñetas'] / None
**Gold corpus, si aplica:** []

#### p6 · abstention (tras s3)
¿Cuál es el número de pedido de mi compra?
**Evidencia sesiones:** []
**Clave/veredicto:** None / None
**Gold corpus, si aplica:** []

#### p7 · multi_session (tras s3)
Según la norma de talles que te pedí usar, ¿a partir de qué edad se contempla a la población destinataria?
**Evidencia sesiones:** ['s1']
**Clave/veredicto:** ['doce años', '12 años', 'doce (12) años'] / None
**Gold corpus, si aplica:** [{'doc_id': 'LEY-27521', 'section_id': 'LEY-27521#ART-1'}]

#### p8 · knowledge_update (tras s1)
¿El precio de mi campera es de 64000 pesos?
**Evidencia sesiones:** ['s1']
**Clave/veredicto:** None / yes
**Gold corpus, si aplica:** []

#### p9 · knowledge_update (tras s2)
¿El precio de mi campera es de 64000 pesos?
**Evidencia sesiones:** ['s1', 's2']
**Clave/veredicto:** None / no
**Gold corpus, si aplica:** []
