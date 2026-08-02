# FearNot Research — Reglas de la casa

Sistema multi-agente de research macro. Mapa completo: ARCHITECTURE.md.
Deuda y decisiones: TECHNICAL_DEBT.md. Límites del extractor SEC: LIMITATIONS.md.

## Reglas operativas (no negociables)
1. **El usuario ejecuta, vos editás.** El bash de este harness suele estar roto:
   trabajá con Read/Edit/Write; todo comando lo corre el usuario y te pega el
   output. Nunca asumas que un comando tuyo corrió.
2. **Mostrá el diff completo ANTES de commitear. Nunca commitees ni pushees
   sin aprobación explícita** — el usuario audita cada cambio.
3. **`data/` es del robot.** Los pipelines de GitHub Actions commitean la data;
   las sesiones locales NUNCA commitean archivos de data/ (son regenerables).
4. **Pull antes de trabajar.** El Action diario commitea todos los días hábiles
   (~12:12 UTC); una sesión local sin pull previo choca seguro.
5. **Modelos SOLO desde config.py** (MODEL + extract_text). Nunca hardcodees un
   string claude-* en otro archivo. extract_text existe porque Opus 5 devuelve
   thinking blocks — no leas response.content[0].text directo.
6. **Un estreno por vez.** No apilar cambios sin verificar el anterior en
   producción (pestaña Actions en verde).
7. **Si cambiás la arquitectura, actualizá ARCHITECTURE.md en la misma sesión**
   — y TECHNICAL_DEBT.md si resolvés o descubrís deuda.
8. **scripts/legacy/ es un cementerio.** No importes ni resucites nada de ahí.

## Semántica que cuesta aprender (ya la pagamos)
- Las fechas de FRED son del PERÍODO OBSERVADO, no del comunicado: un mensual
  al día "tiene" 30-90 días. Los umbrales de FRESHNESS_MAX_DIAS ya lo reflejan.
- Los crons de GitHub demoran 30-90 min. El banking_pipeline corre 15:00 UTC
  a propósito para no chocar con el diario — no lo "optimices" a más temprano.
- Cadencias del sistema: diario (macro/técnica/energía), lunes (Synthesizer),
  mensual día 3 (bancos). El guardián valida bancos solo con --include-banking.
- Filosofía del proyecto: cero alucinación — toda cifra se cita con fuente,
  todo agujero de datos se declara, toda señal va al tracker. Un sistema que
  falla en silencio es peor que uno que se cae.
