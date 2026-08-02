# FearNot Research — Technical Debt

## Advanced Performance Metrics (deferred until N≥10 convictions evaluated)

### Risk-adjusted ratios
- **Priority:** MEDIUM (deferred until ~10 closed convictions)
- **Where:** tracker.py:calcular_performance_convicciones() + web_exporter export
- **Add:** Sharpe ratio, Sortino ratio, Calmar ratio, max drawdown.
- **Rationale:** With N<10, std is unstable and Sharpe becomes noise with appearance of a number. Code can be added now with conditional rendering ("Insufficient data, N=X, need ≥10").
- **Discovered:** 2026-05-29 (Track Record UI build)

### Monte Carlo + statistical distributions
- **Priority:** MEDIUM-HIGH (intellectually valuable, deferred until ~20 convictions)
- **Goal:** Mix statistics + finance + own system. Practical skills cross-applicable for BlackToro/AGM career.
- **Add:**
  1. Distribution fitting on conviction returns (normal? skewed? fat tails?)
  2. Monte Carlo simulation of system returns to estimate confidence intervals on Sharpe, drawdown, etc.
  3. Bootstrap resampling for confidence intervals on win rate
  4. Distribution of MFE vs MAE to characterize trade shapes
- **Why useful:** Allows statements like "with 95% confidence, system Sharpe is between X and Y" instead of single point estimates that lie when N is small.
- **Discovered:** 2026-05-29 (Track Record UI build)


## Track Record Visualization (added 2026-05-27)

### web_exporter filters convictions to last 4 weeks - hides historical track record
- **Priority:** HIGH (blocks core vision of "see if the bot is right over 3 months")
- **Where:** web_exporter.py:cargar_convicciones_recientes()
- **Problem:** Query is WHERE fecha >= (today - 28 days). Evaluated convictions older than 4 weeks disappear from web_data.json. A conviction from 2026-05-11 evaluated at +6.7% vanishes after 2026-06-08. This defeats long-term performance tracking.
- **Fix path:** Add a separate query for closed convictions (evaluado=1) with no date filter, or a dedicated cargar_track_record() function. Web should show "Active Convictions" (recent) AND "Track Record" (all closed) as separate sections.
- **Discovered:** 2026-05-27 during Performance Evaluator build.

### Aggregate performance metrics not included in web_data.json
- **Priority:** MEDIUM (needed for Track Record UI summary)
- **Where:** web_exporter.py (export logic) + tracker.py:calcular_performance_convicciones()
- **Problem:** calcular_performance_convicciones() computes win_rate, avg_return, avg_mfe, avg_mae, alpha_capture - but web_exporter never calls it, so these never reach web_data.json.
- **Fix path:** In web_exporter, call calcular_performance_convicciones() and add result under a performance key in web_data.json. Then render in fearnot-web.
- **Discovered:** 2026-05-27 during Performance Evaluator build.


This document tracks **internal code debt and improvement opportunities** that we deliberately deferred to ship faster. These are things that CAN and SHOULD be fixed eventually — they are not limits imposed by external reality.

For external limitations (filer reporting choices, taxonomy gaps), see `LIMITATIONS.md`.

---

## Format

Each debt entry includes:

- **Area:** Which file/module/system
- **Issue:** What is suboptimal
- **Impact:** Why it matters (correctness? maintainability? performance?)
- **Solution:** Concrete fix
- **Effort:** Rough time estimate (S=<1h, M=2-4h, L=1day+)
- **Priority:** HIGH (blocks growth) / MEDIUM (annoying) / LOW (nice to have)
- **Added:** When this was identified

---

## HIGH priority

### 1. .env loading uses hardcoded mini-parsers in each agent

- **Area:** `agent.py`, `og_agent.py`, `synthesizer.py`, `technical_agent.py`
- **Issue:** Each agent has its own ad-hoc parser of the .env file using `line.split("=", 1)[1].strip()`. This duplicates code, doesn't handle edge cases (quotes, comments, escaped chars), and is verbose.
- **Impact:** Code maintenance burden. Any change to how secrets are loaded requires touching 4+ files. Also looks unprofessional to anyone reviewing the repo.
- **Solution:** Use `python-dotenv` library. Replace all hardcoded parsers with `from dotenv import load_dotenv; load_dotenv()` at the top of each agent. Single line.
- **Effort:** S (30 min including adding to requirements.txt and testing)
- **Priority:** HIGH (visible to recruiters in public repo)
- **Added:** May 20, 2026 (discovered during GitHub public push)

### 2. update_web.sh has hardcoded absolute paths

- **Area:** `update_web.sh`
- **Issue:** Paths like `~/Desktop/macro_agent` and `~/Desktop/fearnot-web` are hardcoded. Script does not work for anyone else who clones the repo, and breaks if you move the folder.
- **Impact:** Breaks reproducibility. Anyone trying to run the pipeline from cloned repo fails.
- **Solution:** Parameterize with environment variables: `MACRO_AGENT_DIR="${MACRO_AGENT_DIR:-$HOME/Desktop/macro_agent}"` etc.
- **Effort:** S (15 min)
- **Priority:** HIGH (visible to recruiters in public repo)
- **Added:** May 20, 2026 (discovered during GitHub public push)

### 3. No requirements.txt validation against actual imports

- **Area:** Repo root + scripts
- **Issue:** `requirements.txt` was assembled by manual grep of imports. There is no automated check that ensures every imported library is listed, or that listed libraries are still used.
- **Impact:** Future imports may not get added to requirements.txt. Future deprecated libraries may stay listed unused.
- **Solution:** Add a `tests/test_requirements.py` that uses `pipreqs` or similar to compare actual imports vs declared. Run in CI.
- **Effort:** M (1-2h to set up + tune)
- **Priority:** HIGH (correctness)
- **Added:** May 20, 2026 (during GitHub public push)

---

## MEDIUM priority

### 4. Sector overrides duplicated between gaap_taxonomy.py and sector_mappings/

- **Area:** `gaap_taxonomy.py` (inline `sector_overrides` per concept) + `sector_mappings/energy.py` (`ENERGY_GAAP_OVERRIDES`)
- **Issue:** Two mechanisms for the same purpose. `gaap_taxonomy.py` has `sector_overrides` inline (used for bank, insurance). `sector_mappings/energy.py` has its own `ENERGY_GAAP_OVERRIDES`. Tech currently uses neither (no overrides needed). The two mechanisms are combined by `sector_router.py` cascade, which means changes need to be coordinated across both files.
- **Impact:** Confusion about where overrides should go. Risk of inconsistency when adding new sectors.
- **Solution:** Pick ONE mechanism. Recommended: move everything to `gaap_taxonomy.py:sector_overrides` for taxonomy concerns, keep `sector_mappings/X.py` only for metrics/validation/helpers (not GAAP overrides).
- **Effort:** M (2-3h with regression testing)
- **Priority:** MEDIUM (works but smells)
- **Added:** May 20, 2026 (Tech sector planning)

### 5. sector_mappings/__init__.py is empty (no explicit exports)

- **Area:** `sector_mappings/__init__.py`
- **Issue:** The package __init__ has no exports. Modules work via `from sector_mappings import energy`, but there's no central contract declaring which modules exist.
- **Impact:** Onboarding friction. Future developer doesn't know at a glance which sectors are available.
- **Solution:** Add explicit imports and __all__:
```python
  from sector_mappings import energy, tech
  __all__ = ["energy", "tech"]
```
- **Effort:** S (5 min + adding tech after registration)
- **Priority:** MEDIUM
- **Added:** May 20, 2026

### 6. No SectorMapping base class — risk of inconsistency across sectors

- **Area:** `sector_mappings/`
- **Issue:** `energy.py` and `tech.py` follow similar patterns by convention, but there's no enforced interface. Future sectors (banking, insurance, industrial, utilities) might diverge.
- **Impact:** As we add 4+ more sectors, drift becomes likely. Refactor cost grows non-linearly.
- **Solution:** After 3-4 sectors are implemented, refactor to a SectorMapping base class (Python ABC or Protocol) that defines required attributes: TICKERS set, helpers (is_ticker, get_subsector), metrics dict, validation_rules dict. Each sector module subclasses or implements the protocol.
- **Effort:** L (4-6h including migration of energy.py and tech.py)
- **Priority:** MEDIUM (do AFTER 4 sectors exist, not before)
- **Added:** May 20, 2026 (Tech sector planning)

### 7. tests/ folder has only one test file

- **Area:** `tests/`
- **Issue:** Only `test_collector.py` exists (from old setup) and now `test_tech_coverage.py`. No coverage for: gaap_taxonomy, sector_router, financials_extractor_v2 core functions, calculated_metrics fallbacks, energy sector specifics.
- **Impact:** Each refactor requires manual testing. Higher risk of regressions over time.
- **Solution:** Build out test suite incrementally. Start with: test_gaap_taxonomy (concept lookup, sector_overrides), test_sector_router (detection, name resolution), test_calculated_metrics (each fallback function with known inputs/outputs).
- **Effort:** L (1-2 days for solid baseline)
- **Priority:** MEDIUM
- **Added:** May 20, 2026

---

## LOW priority

### 8. Legacy debug/patch files in repo root

- **Area:** `debug_sec.py`, `patch_agent_options.py`, `patch_options_flow.py`, `test_cik.py`, `test_financials.py`, `test_sec.py`, `limpiar_duplicados.py`
- **Issue:** One-off scripts and patches living in repo root alongside core modules. Visual clutter.
- **Impact:** Makes the repo look messier than it is. Recruiter scanning root files sees noise.
- **Solution:** Move to `scripts/legacy/` or similar. Update any imports if needed.
- **Effort:** S (30 min including verification that nothing imports these)
- **Priority:** LOW (cosmetic, not functional)
- **Added:** May 20, 2026

### 9. financials_extractor.py (v1) coexists with v2

- **Area:** `financials_extractor.py` vs `financials_extractor_v2.py`
- **Issue:** Both versions exist. v2 is the current production, v1 is legacy.
- **Impact:** Confusion about which is current. Risk of importing wrong version.
- **Solution:** Either move v1 to `legacy/` folder, or delete entirely if no longer referenced.
- **Effort:** S (15 min to verify no references then delete)
- **Priority:** LOW
- **Added:** May 20, 2026

### 10. extraer_financials_v2() has tardios imports inside function

- **Area:** `financials_extractor_v2.py` line 339-345
- **Issue:** Imports (`from sector_router import ...`, `from calculated_metrics import ...`) are inside the function body with comment "Imports tardios para evitar problemas de orden". This suggests there was a circular import that got patched by deferring.
- **Impact:** Slight performance cost (imports re-evaluated on every call — Python caches but still resolves). More importantly: hides architectural smell.
- **Solution:** Investigate the circular import root cause. Typically solved by moving shared types/constants to a separate module that both sides import from.
- **Effort:** M (1-2h to investigate + refactor)
- **Priority:** LOW (works fine in practice)
- **Added:** May 20, 2026

### 11. Sub-sector ranges in tech.py use inconsistent dict structure

- **Area:** `sector_mappings/tech.py:TECH_SPECIFIC_METRICS`
- **Issue:** Some metrics have `healthy_range` as tuple `(min, max)`, others as dict `{big_tech: (), saas: (), semis: ()}`. Caller needs to type-check.
- **Impact:** Future code that consumes these metrics has to handle both shapes.
- **Solution:** Standardize: always dict per sub-sector, even if values are identical. Or: always tuple with sub-sector overrides separate.
- **Effort:** S (30 min)
- **Priority:** LOW
- **Added:** May 20, 2026 (created during Tech sector implementation)

---

## DONE (resolved, kept for history)

(empty for now — items move here when fixed)

---

## Process

### Adding a new debt item

1. Add an entry to the appropriate priority section above
2. Include all 7 fields
3. Commit with message: `docs: add tech debt [AREA] [BRIEF]`

### Resolving an item

1. Implement the fix
2. Move the entry to DONE section with resolution date and commit hash
3. Update any other docs that referenced it

### Priority review

- **Weekly:** review HIGH priority items, decide if any move up to active work
- **Monthly:** review MEDIUM and LOW, re-prioritize based on system evolution

## SEC Frame Extraction — Audit Findings & Verified State (added 2026-06-08)

### Audit conclusions REFUTED by raw-JSON verification
- **Priority:** N/A (documentation — prevents future confusion)
- **Context:** A Claude Code audit (Opus 4.7, AUDIT_REPORT.md) concluded the quarterly
  extractor was "structurally broken" and recommended replacing the frame filter with a
  duration filter. The audit could NOT download SEC JSONs (its bash hung, SEC returned 403),
  so it reasoned from code + documented SEC rules + stockanalysis.com dates — i.e. deduction,
  not data. We then verified every critical claim against raw companyfacts JSON. Three of its
  most severe findings were FALSE:
  1. Audit: "NVDA/CRM/MU never match CY{Y}Q{n}, structurally impossible, 0/6 recovery."
     Reality: NVDA revenue extracts 5/6 (direct), hole only at Q4'24 (correct skip_noncalendar).
     SEC assigns the frame by PROXIMITY to the calendar quarter, not exact date match. NVDA's
     fiscal Q ending Jul 28 still gets frame CY2024Q2.
  2. Audit: "META Q1 2026 OCF ($32,226M) exists without frame."
     Reality: it has frame CY2026Q1. (Older copies Q1'24/Q1'25 lack frame; the recent one has it.)
  3. Audit: "filter-by-frame is broken, rewrite the extractor core."
     Reality: income statement (revenue, op_income, margins) works for all 8 tech tickers,
     calendar and non-calendar. The extractor core was NOT touched.
- **How the frame actually works (verified):** the original 10-Q of a quarter is filed WITHOUT
  a frame. When that quarter reappears as a comparative in the next year's 10-Q, that copy gets
  the frame (same value). So most quarters have a framed record (recent-original OR comparative),
  which extraer_fact_trimestral_auto finds. This is why banking populated correctly.
- **Lesson:** an authorized audit reasoning from deduction (no data access) was wrong on its
  central findings. Verifying against raw SEC JSON before changing code prevented rewriting the
  most delicate part of the system to fix a non-existent problem.
- **Discovered:** 2026-06-08 (post-audit raw-JSON verification)

### Verified-healthy (do NOT "fix")
- banking_financials_q: values correct. NU is an IFRS source limitation (its XBRL exposes no
  recognizable NetInterestIncome tag — only ComprehensiveIncomeAttributableToNoncontrollingInterests
  — and reports in USD, so NOT a unit bug), same class as ROTCE/NIM gaps. Not recoverable by us.
- Income statement quarterly extraction: works for calendar AND non-calendar filers.
- FIX 1 (skip_noncalendar Q4): correct and confirmed by the audit too.

### Latent bug: quarterly path hardcodes unidad="USD"
- **Priority:** MEDIUM (latent — not triggered by any current concept)
- **Where:** extraer_fact_trimestral (unidad default "USD"), extraer_fact_trimestral_auto,
  extraer_trimestre_con_q4 (no unidad param at all), called by extraer_serie_trimestral.
- **Problem:** the whole quarterly chain is wired to USD. Concepts whose canonical unit is not
  USD — EPS (USD/shares), shares (shares), or IFRS filers reporting in non-USD currencies —
  would return None for every quarter. NU does NOT trigger this (it reports USD); it's latent
  until EPS/shares or a non-USD IFRS filer is added to the quarterly path.
- **Fix path:** add unidad param to extraer_fact_trimestral_auto and extraer_trimestre_con_q4;
  resolve unidad per concept in extraer_serie_trimestral (mirror the annual path's
  get_ifrs_unit_for_concept dispatch) and propagate it.
- **Discovered:** 2026-06-08 (audit finding, verified latent)

### Latent bug: dedup ranks by filed-desc (may pick restated over original)
- **Priority:** LOW-MEDIUM (mitigated in practice; original and comparative usually share the value)
- **Where:** extraer_fact_trimestral (matching.sort by filed reverse) and extraer_fact_anual (same).
- **Problem:** among duplicate records for the same period, sorting by filed desc picks the most
  recent — i.e. a restated/comparative copy over the original 10-Q/10-K. Usually identical
  (verified: JPM Q2'24 original-no-frame and comparative-CY2024Q2 both = 22746). Pathological
  cases (genuine restatement, reclassification, rounding) would silently take the restated value.
- **Fix path:** prefer record whose form matches the period (10-Q for quarters, 10-K for FY), then
  earliest filed (the original); optionally expose restatements as metadata, not silent overwrite.
- **Discovered:** 2026-06-08 (audit finding)

### Latent bug: is_flow detection reads only records[0]
- **Priority:** LOW
- **Where:** extraer_fact_anual, is_flow = bool(records) and "start" in records[0].
- **Problem:** decides flow-vs-stock from the FIRST record only. If records[0] is an atypical
  stock-style snapshot, the whole concept gets misclassified. Unlikely for standard taxonomy;
  possible for custom-extension concepts with mixed record types in one bucket.
- **Fix path:** use modal type (>=80% of records have "start") or a per-concept type map.
- **Discovered:** 2026-06-08 (audit finding)

### REAL pending problem: quarterly cash-flow (OCF/capex) coverage is uneven
- **Priority:** HIGH (blocks FCF — a core tech metric; FCF is the check on whether growth is
  real cash or accounting/SBC, the Chanos-layer question)
- **Where:** extraer_serie_trimestral for operating_cash_flow and capex on tech tickers.
- **Problem:** NOT a frame issue. Some tech filers report the cash-flow statement only as YTD
  cumulative (no discrete-quarter record), so the discrete quarter must be DERIVED:
  Q_n = YTD_n - YTD_(n-1). AMZN reports discrete quarters (6/6 OK); others report YTD and need
  derivation. Non-calendar filers complicate it (their YTD starts at the fiscal-year start).
  Measured coverage: AMZN 6/6, CRM 5/6, MSFT 4/6, META/GOOGL/NOW/NVDA/MU ~1/6 for OCF & capex.
- **Fix path (design against raw data, NOT deduction):** per-ticker, inspect how OCF/capex are
  reported (discrete-quarter vs YTD). Where YTD-only, derive discrete quarter by subtracting
  consecutive YTDs, aligning periods correctly (watch non-calendar fiscal starts — same trap that
  produced the -30.2 NVDA Q4). Verify each derived quarter against an independent source.
- **Discovered:** 2026-06-08 (tech vertical build); to be tackled next.

## TD — es_fresco marca como frescos datos vencidos (series mensuales)
- **Detectado:** 2026-07-31 — por el propio agente macro (Opus 5) en su tesis del día.
- **Síntoma:** `michigan_inflation_exp` con fecha de publicación 2026-05-01 (3 meses de rezago) llegó al agente con `es_fresco=true`.
- **Causa probable:** la validación de frescura por `max_dias` no contempla series mensuales con lag de publicación (MICH publica mensual con ~1 mes de rezago).
- **Impacto:** el agente recibe datos vencidos marcados como confiables. Hoy mitigado porque Opus 5 lo detecta y baja la confianza solo — pero el régimen pre-calculado (que no razona) los consume ciego.
- **Fix sugerido:** revisar `max_dias` por serie en el collector; incluir `fecha_publicacion` en el snapshot y validar contra la frecuencia esperada de cada serie.
- **RESUELTO 2026-08-01:**
  - `verificar_freshness` (collector.py) ahora compara `(hoy − fecha_publicacion)` contra `max_dias`, no `(hoy − fecha_descarga)`. La columna ya existía en la tabla (`indicadores.fecha_publicacion NOT NULL`), no hizo falta ALTER TABLE. Fallback defensivo a `fecha_descarga` + WARNING si por algún motivo la columna llega vacía.
  - `FRESHNESS_MAX_DIAS` re-escrito: toda serie fetched por `correr_colector()` tiene entrada explícita, el default 5 pasa a ser sólo red de seguridad. Mensuales (unemployment, sahm_rule, cpi, pce_core, michigan_inflation_exp) fijados en 40 días para cubrir el rezago normal de publicación (~1 mes desde el mes observado). Duplicado de `breakeven_5y5y` eliminado.

## TD — clasificador de noticias archiva temas ajenos bajo POLÍTICA MONETARIA
- **Detectado:** 2026-07-31 — por el agente macro (titular de boicot FIFA clasificado como política monetaria).
- **Causa probable:** clasificación por keywords débiles o categoría default cuando no hay match.
- **Impacto:** contamina el contexto del prompt con ruido; el agente lo declaró, pero gasta tokens y erosiona la señal.
- **Fix sugerido:** categoría "OTROS" como default estricto, o clasificar con una llamada barata al modelo en el news_collector.
- **RESUELTO 2026-08-01:**
  - `clasificar` en `news_collector.py` ahora hace matching con `re.search(r"\b<kw>\b", texto)` (word boundary) en vez de `if kw in texto` (substring). Esto corta el caso "fed" ⊂ "federation" que llevó a que "FIFA federation boycott" cayera en POLÍTICA MONETARIA.
  - Default explícito `OTROS` cuando ningún keyword calza como palabra completa (antes: `MACRO GLOBAL`, que le prestaba peso macro a un titular sin match).
  - Lista de categorías + keywords movida a constante módulo `_CATEGORIAS_KEYWORDS` para separarla de la lógica.
  - No se agregó clasificación por LLM — decisión explícita: primero validar el default honesto en prod.

## TD (FUTURO) — freshness por días hábiles para series de mercado
- **Detectado:** 2026-08-02 — durante re-test del `FRESHNESS_MAX_DIAS` recalibrado.
- **Contexto:** las series diarias de mercado (yfinance intraday, FRED daily) no publican fines de semana ni feriados. Un pipeline corriendo lunes a la mañana ve toda la data del viernes → 3 días calendario de edad, aunque el mercado esté "al día". Post-feriado (ej. lunes feriado + lunes de test = viernes previo) llega a 4.
- **Mitigación actual:** umbral calendario elevado a 4 días para el tier diario (`collector.py:FRESHNESS_MAX_DIAS`). Cubre el peor gap normal; un dato genuinamente estancado dispara a los 5+.
- **Fix sugerido (no urgente):** reemplazar el umbral calendario por un cálculo en días hábiles (`numpy.busday_count` o similar) para el tier de mercado, con calendario NYSE (o al menos excluyendo weekends + feriados US). El tier mensual FRED puede seguir en calendario, la semántica ya es la correcta.
- **Prioridad:** LOW. El umbral de 4 días calendario es honesto; el refinamiento sólo ajusta el margen entre "cubre feriado largo" y "detecta stall real".

## Sesión "despertar bancos" — RESUELTO 2026-08-02

Sesión que cerró la mayoría del gap del workstream bancos/SEC (documentado en ARCHITECTURE.md §4.3 pre-sesión y en items #2, #3 del backlog).

- **Nuevo:** `.github/workflows/banking_pipeline.yml` — cron mensual día 3, 12:00 UTC. Pasos: `banking_collector.py` → `banking_collector_q.py` → `banking_agent.py` → `banking_agent_q.py` → commit `data/` → `health_check.py --include-banking`. Separado del daily porque los 10-K/10-Q no cambian a diario.
- **`banking_agent.py` y `banking_agent_q.py`:** `__main__` ahora llama `registrar_senales(adaptar_para_tracker(output))` al final, matcheando el patrón de `og_agent.py`. Sin este fix, las señales bancarias no llegaban al tracker aunque los `adaptar_para_tracker` existieran.
- **`health_check.py`:** flag `--include-banking` que suma la validación de `tesis_banking_{fecha}.json` y `tesis_banking_q_{fecha}.json` contra hoy UTC (los bancos no siguen calendario de mercado — el `last_business_day` del daily no aplica). Sin el flag el comportamiento actual queda intacto.
- **`web_exporter.py`:** nueva función `construir_banking_pulse` + soporte para prefijos `"banking"` y `"banking_q"` en `cargar_tesis_mas_reciente`. Si al menos una tesis bancaria existe en `data/`, `web_data.json` incluye una clave `banking` con `annual` y/o `quarterly` como sub-secciones. Si no existe ninguna, la clave está ausente — el frontend chequea `if 'banking' in data`.
- **`sector_router.py:25`:** `from sector_mappings import banking` descomentado.

Nota operacional: el `banking_pipeline.yml` NO pushea a `fearnot-web`. La sección `banking` recién aparece en el frontend con el daily del día siguiente. Si se necesita publicación inmediata, agregar step de web_exporter + push a `fearnot-web` en el banking pipeline (`daily_pipeline.yml:124-159` como referencia).

## Limpieza de scripts legacy — EN CURSO 2026-08-02

Backlog #6 (`TECHNICAL_DEBT.md#8`): mover a `scripts/legacy/`:
- `debug_sec.py`, `patch_agent_options.py`, `patch_options_flow.py`
- `test_cik.py`, `test_financials.py`, `test_sec.py`
- `limpiar_duplicados.py`
- `financials_extractor.py` (v1 — reemplazado por v2, `TECHNICAL_DEBT.md#9`)

Movimiento de archivos es operación del usuario (comandos `git mv` entregados en la sesión). Verificar que ningún módulo del pipeline los importa antes de mover — inspección estática sugiere que ninguno lo hace (ninguno aparece en imports de agentes/collectors activos), pero validar con `grep -R "from financials_extractor import" .` u equivalente antes de confirmar.
