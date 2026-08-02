# FearNot Research — Architecture Audit

**Fecha:** 2026-07-31
**Alcance:** `~/Desktop/macro_agent` (backend) + `~/Desktop/fearnot-web` (frontend).
**Método:** auditoría estática (solo lectura). Bash del harness roto, sin `find`/`grep`; el inventario de archivos se armó siguiendo referencias explícitas en `update_web.sh`, `.github/workflows/daily_pipeline.yml`, docstrings e imports. Toda afirmación cita archivo y línea. Lo que no pude verificar aparece como **no determinable** con la razón.

---

## 1. Mapa del sistema

Flujo completo, día laboral típico (Mar–Vie). Los pasos exactos en producción están en `.github/workflows/daily_pipeline.yml:54-97`; `update_web.sh` (local) los replica con paths hardcodeados.

```
                                   ┌───────────────────────────┐
                                   │  APIs EXTERNAS            │
                                   │  FRED · EIA · NewsAPI ·   │
                                   │  yfinance · SEC EDGAR     │
                                   └────────────┬──────────────┘
                                                │
        ┌──────────────────┬────────────────────┼─────────────────────┬─────────────────────┐
        ▼                  ▼                    ▼                     ▼                     ▼
 ┌────────────┐    ┌───────────────────┐ ┌──────────────────┐ ┌─────────────────┐  ┌───────────────────┐
 │collector.py│    │technical_collector│ │og_collector.py + │ │news_collector.py│  │banking_collector  │
 │ (macro:    │    │.py + options_flow_│ │og_news_collector │ │ (NewsAPI head-  │  │ + _q.py           │
 │ FRED+yfi)  │    │collector.py       │ │.py (yfi+EIA+News)│ │ lines macro)    │  │ (SEC → banking_*) │
 └─────┬──────┘    └─────────┬─────────┘ └─────────┬────────┘ └────────┬────────┘  └─────────┬─────────┘
       │                     │                     │                   │                     │
       ▼                     ▼                     ▼                   │                     ▼
             ┌──────────────────────────────────────────────────────────┐          ┌───────────────────┐
             │              data/macro.db  (SQLite, versionado)         │          │ banking_financials│
             │  tablas: indicadores, alertas, senales_tecnicas,         │          │ + _q (long fmt)   │
             │  indicadores_tecnicos_mercado, indicadores_options_flow, │          │                   │
             │  precios_og, spreads_og, indicadores_eia, noticias_og,   │          │                   │
             │  senales, convicciones, banking_financials(_q)           │          │                   │
             └───────┬─────────────────┬───────────────────┬────────────┘          └─────────┬─────────┘
                     │                 │                   │                                 │
        ┌────────────┘                 │                   └────────────┐                    │
        ▼                              ▼                                ▼                    ▼
 ┌────────────┐             ┌─────────────────────┐        ┌────────────────────┐   ┌────────────────────┐
 │ agent.py   │  ── llama ──│ technical_agent.py  │        │  og_agent.py       │   │ banking_agent.py   │
 │ (Macro,    │             │ (Technical, Claude) │        │  (Energy Desk,     │   │ + _q.py            │
 │ Claude)    │             │                     │        │   Claude)          │   │  (HUÉRFANOS —      │
 │ +news      │             │  lee tesis macro    │        │  lee tesis         │   │   ver §4)          │
 │            │             │  del día            │        │  macro+tecnica     │   │                    │
 └─────┬──────┘             └─────────┬───────────┘        └─────────┬──────────┘   └────────┬───────────┘
       │                              │                              │                       │
       ▼                              ▼                              ▼                       ▼
 tesis_YYYY-MM-DD.json  tesis_tecnica_YYYY-MM-DD.json   tesis_og_YYYY-MM-DD.json  tesis_banking(_q)_*.json
       │                              │                              │                       │
       ▼                              ▼                              ▼                       ▼
       └─────── tracker.registrar_senales() ── convicciones/senales en macro.db ─────────────┘
                                     │
                                     │  (SOLO LUNES)
                                     ▼
                        ┌───────────────────────────┐
                        │  synthesizer.py           │
                        │  (CIO, Claude)            │
                        │  lee las 3 tesis + DB     │
                        │  → convicciones semanales │
                        └────────────┬──────────────┘
                                     ▼
                        convicciones_YYYY-MM-DD.json
                                     │
                                     ▼
                     tracker.evaluar_convicciones_vencidas()
                     (path-dependent: MFE/MAE/vol; yfinance re-fetch)
                                     │
                                     ▼
                        ┌───────────────────────────┐
                        │  web_exporter.py          │
                        │  compone data/web_data.json│
                        └────────────┬──────────────┘
                                     ▼
                        health_check.py (guard rail final)
                                     │
                                     ▼
                fearnot-web/public/web_data.json (push a repo separado)
                                     ▼
                Vercel redeploy · fearnot-web.vercel.app
```

**Anclas de contrato entre etapas:**
- Cada tesis JSON se escribe con nombre `data/{prefijo}_{fecha}.json`. Contrato en `health_check.py:19-38` (macro `tesis_`, técnica `tesis_tecnica_`, energía `tesis_og_`).
- El agente técnico depende de leer la tesis macro del día: `technical_agent.py:228-250` (`leer_regimen_macro`).
- El og_agent lee tesis macro + técnica de disco: `og_agent.py:134-153`.
- El synthesizer lee las 3 tesis + DB: `synthesizer.py:163-235`.
- web_exporter arma `data/web_data.json` con `metadata.fecha = date.today()`: `web_exporter.py:342-349`.
- health_check valida existencia + tamaño mínimo + claves obligatorias + `fecha == target`: `health_check.py:48-101`.

---

## 2. Inventario de .py

Estado: **ACTIVO** = llamado en pipeline de producción o import in-graph desde algo activo. **DORMIDO** = wired pero no ejecutado por el pipeline actual. **MUERTO** = script one-off, patch aplicado, o legacy sin referencias. **DUPLICADO** = coexiste con reemplazo.

> El listado de `.py` se armó desde imports directos, referencias en `update_web.sh`, `.github/workflows/daily_pipeline.yml`, y `TECHNICAL_DEBT.md#8` (donde se enumeran los legacy). **No determinable:** existencia de `.py` adicionales en carpetas fuera de las citadas (no puedo hacer `find` sin bash).

### Backend — `~/Desktop/macro_agent/`

| Archivo | Propósito | Cuándo corre | Estado |
|---|---|---|---|
| `collector.py` | FRED + yfinance → tabla `indicadores` en `macro.db`; calcula yield_curve + régimen básico | Diario Mar–Vie en Actions (`daily_pipeline.yml:60`) | ACTIVO |
| `news_collector.py` | NewsAPI top-headlines filtradas por keywords macro → cache JSON | Diario (`daily_pipeline.yml:63`); también importado por `agent.py:12` | ACTIVO |
| `technical_collector.py` | 200DMA, momentum 12M, VIX term struct, VRP, breadth (S&P sample) → `senales_tecnicas`, `indicadores_tecnicos_mercado` | Diario (`daily_pipeline.yml:70`) | ACTIVO |
| `options_flow_collector.py` | VIX9D/VIX6M/IV percentile/put-call → `indicadores_options_flow` | Diario (`daily_pipeline.yml:73`); leído por `technical_agent.py:18-36` | ACTIVO |
| `og_collector.py` | Precios OG (yfinance) + EIA inventories + spreads → varias tablas | Diario (`daily_pipeline.yml:66`) | ACTIVO |
| `og_news_collector.py` | Noticias sector energético → `noticias_og` | Diario (`daily_pipeline.yml:67`) | ACTIVO |
| `agent.py` | Macro Agent (Claude) — genera `tesis_YYYY-MM-DD.json` | Diario (`daily_pipeline.yml:76`) | ACTIVO |
| `technical_agent.py` | Technical Agent (Claude) — `tesis_tecnica_*.json`; llama al tracker | Diario (`daily_pipeline.yml:79`) | ACTIVO |
| `og_agent.py` | Energy Desk (Claude) — `tesis_og_*.json`; llama al tracker | Diario (`daily_pipeline.yml:82`) | ACTIVO |
| `synthesizer.py` | CIO (Claude) — convicciones semanales; persiste a tabla `convicciones` | Lunes (`daily_pipeline.yml:85-90`) | ACTIVO (weekly) |
| `tracker.py` | Registrar señales, evaluar señales/convicciones vencidas, calcular performance | Al final de cada agente (import) + `daily_pipeline.yml:93` explícito | ACTIVO |
| `web_exporter.py` | Compone `data/web_data.json` para el frontend | Diario (`daily_pipeline.yml:96`) | ACTIVO |
| `health_check.py` | Valida outputs del día (tamaño, JSON, claves, fecha) | Diario, último paso (`daily_pipeline.yml:179-181`) | ACTIVO |
| `config.py` | `MODEL` + `extract_text(response)` (parser thinking-safe) | Import compartido por los 6 agentes | ACTIVO |
| `banking_collector.py` | SEC EDGAR → `banking_financials` (anual). Universo 7 bancos | **No invocado por el pipeline** (`daily_pipeline.yml`) | DORMIDO |
| `banking_collector_q.py` | SEC EDGAR → `banking_financials_q` (trimestral) | **No invocado por el pipeline** | DORMIDO |
| `banking_agent.py` | Claude sobre `banking_financials` anual | **No invocado** — su `if __name__ == "__main__"` (`banking_agent.py:345-357`) espera CLI manual | DORMIDO |
| `banking_agent_q.py` | Claude sobre `banking_financials_q` trimestral | **No invocado** — CLI manual (`banking_agent_q.py:381-393`) | DORMIDO |
| `tendencia.py` | Analiza pendiente de una serie trimestral (subiendo/bajando/estable + racha) | Import de `banking_agent_q.py:27` | DORMIDO (viaja con banking_q) |
| `financials_extractor_v2.py` | Extractor SEC EDGAR con dispatch us-gaap/ifrs; nucleo del workstream bancos+SEC | Import de `banking_collector.py` (implícito por docstring `banking_collector.py:6`); usado como CLI manual (`financials_extractor_v2.py:19-22`) | DORMIDO (ejecutado sólo cuando corren los banking_collectors, que están dormidos) |
| `financials_extractor.py` | Extractor v1 basado en yfinance | Reemplazado por v2 según `TECHNICAL_DEBT.md#9` (líneas 155-163) | DUPLICADO (v1 legacy) |
| `gaap_taxonomy.py` | Mapeo concepto→[tags us-gaap] con `sector_overrides` inline | Import de `sector_router.py:21` | DORMIDO (soporta workstream SEC) |
| `ifrs_taxonomy.py` | Ídem para IFRS (NU) | Import de v2 (implícito por docstring `ifrs_taxonomy.py:1-15`) | DORMIDO |
| `sector_router.py` | Detecta sector del ticker y decide qué tags GAAP probar | Import de v2 | DORMIDO |
| `sector_mappings/__init__.py` | Vacío (`sector_mappings/__init__.py:1`, marcado por Read como 1 línea) — sin `__all__` | — | DORMIDO / documentado en `TECHNICAL_DEBT.md#5` |
| `sector_mappings/energy.py` | Overrides GAAP + métricas energy | Import de `sector_router.py:24` | DORMIDO |
| `sector_mappings/tech.py` | Overrides + métricas tech | Import de `sector_router.py:27` | DORMIDO |
| `sector_mappings/banking.py` | Descripción de métricas bank | Docstring lo cita (`sector_mappings/banking.py:1-27`), pero `sector_router.py:25` deja el import comentado (`# TODO`) — no lo carga | DORMIDO (imports comentados) |
| `calculated_metrics.py` | Métricas derivadas de facts SEC (ej. shares diluted XOM, operating income XOM) | Import citado por `banking_collector.py:11-12` | DORMIDO (parte del workstream SEC) |
| `debug_sec.py` | Script one-off de exploración | Manual, sin caller | MUERTO (listado en `TECHNICAL_DEBT.md#8:147`) |
| `patch_agent_options.py` | Script que **patcheaba** `technical_agent.py` para meter options flow — ya aplicado | Manual, sin caller | MUERTO (líneas 1-15) |
| `patch_options_flow.py` | Idem para `technical_collector.py` — ya aplicado | Manual, sin caller | MUERTO (`patch_options_flow.py:1-15`) |
| `test_cik.py` | Test exploratorio SEC | Manual | MUERTO (listado en `TECHNICAL_DEBT.md#8`) |
| `test_financials.py` | Test exploratorio yfinance | Manual | MUERTO |
| `test_sec.py` | Test exploratorio SEC | Manual | MUERTO |
| `limpiar_duplicados.py` | Script one-off (Modelo B dedup) — la lógica ya está en tracker (`tracker.py:124-136`) | Manual, DRY RUN por default | MUERTO (`TECHNICAL_DEBT.md#8`) |
| `tests/test_collector.py` | Tests unitarios/integración del collector | Manual (pytest) — **no** se corre en Actions (`daily_pipeline.yml` no llama pytest) | DORMIDO |
| `tests/test_tech_coverage.py` | Regression del tech SEC coverage | Manual — `python3 -m tests.test_tech_coverage` (`tests/test_tech_coverage.py:11`) | DORMIDO |
| `tests/test_banking_coverage.py` | Verifica routing + cobertura de los 3 conceptos nucleo de banca (NII, deposits, loans) para los 7 bancos (`tests/test_banking_coverage.py:1-20`). Dos modos: sin red (Test A) y `--live` que baja SEC | Manual — `python3 tests/test_banking_coverage.py [--live]` (`tests/test_banking_coverage.py:10-11`). No corre en Actions | DORMIDO |

**Notas de inventario:**
- `sector_mappings/__init__.py` está vacío. Confirmado por Read → "the file has 1 lines" (probablemente sólo newline). Coincide con `TECHNICAL_DEBT.md#5`.
- **No determinable:** si hay `.py` adicionales en subcarpetas no listadas (`scripts/`, `logs/`, etc.). El pipeline no los referencia.

### Frontend — `~/Desktop/fearnot-web/`

Componentes verificados por Read directo o por import:

| Archivo | Propósito | Estado |
|---|---|---|
| `app/layout.tsx` | Root layout con fuentes Geist (`app/layout.tsx:1-33`) | ACTIVO |
| `app/page.tsx` | Home; fetch client-side de `/web_data.json` (`app/page.tsx:63-71`) | ACTIVO |
| `app/research/page.tsx` | Research archive; server component; incluye `ConvictionsSection`, `DailyPulseCard`, `EnergyPulseSection` (`app/research/page.tsx:1-6`) | ACTIVO |
| `app/research/ConvictionsSection.tsx` | Client component que consume convicciones (`app/research/ConvictionsSection.tsx:1-30`) | ACTIVO |
| `app/research/DailyPulseCard.tsx` | Referenciado desde `research/page.tsx:5`. **No determinable:** contenido no leído. | ACTIVO |
| `app/research/EnergyPulseSection.tsx` | Referenciado desde `research/page.tsx:6`. **No determinable:** contenido no leído. | ACTIVO |
| `app/components/Header.tsx` | Referenciado desde `page.tsx:5` y `research/page.tsx:2`. **No determinable:** contenido no leído. | ACTIVO |
| `app/lib/data.ts` | Types + `loadWebData()` (`app/lib/data.ts:54-58`) | ACTIVO |
| `app/lib/papers.ts` | Referenciado desde `research/page.tsx:3` (`getAllPapers`). **No determinable:** contenido no leído. | ACTIVO |
| `public/web_data.json` | Bundle publicado por el pipeline; consumido en runtime | ACTIVO (data artifact) |
| `package.json` | Next 16.2.4 + React 19.2.4 + Tailwind 4 (`package.json:11-27`) | — |

**Disonancia de tipos frontend/backend:** `app/lib/data.ts:19-51` declara un `WebData` que incluye `tecnicos`, `performance`, `invalidadores_tecnicos`, `confianza_macro`, `confianza_tecnica`. Ninguno de esos campos está en el shape que arma `web_exporter.py:342-369`. La página home usa un tipo distinto redeclarado en `app/page.tsx:8-28` que **sí** matchea lo que produce el backend. `data.ts` está desincronizado — riesgo de refactor futuro.

---

## 3. Qué corre dónde

### GitHub Actions — `.github/workflows/daily_pipeline.yml`

- **Cron:** `30 10 * * 1-5` (`daily_pipeline.yml:9`) → 10:30 UTC = 07:30 AR, lunes a viernes.
- **Manual trigger:** `workflow_dispatch` (`daily_pipeline.yml:10`).
- **Runner:** ubuntu-latest, timeout 30 min (`daily_pipeline.yml:15-16`).
- **Permisos:** `contents: write` para commitear `data/` al mismo repo (`daily_pipeline.yml:18-19`).
- **Secrets requeridos:** `ANTHROPIC_API_KEY`, `FRED_API_KEY`, `EIA_API_KEY`, `NEWS_API_KEY`, `WEB_REPO_PAT` (`daily_pipeline.yml:50-53, 129`).
- **Pasos (resumen):**
  1. Checkout `fearnot-research` (`daily_pipeline.yml:25-26`)
  2. Setup Python 3.11 con caché pip (`daily_pipeline.yml:31-35`)
  3. `pip install -r requirements.txt` (`daily_pipeline.yml:41-43`)
  4. Colectores y agentes en orden: macro→news→og→tech→options→macro agent→tech agent→og agent→(lunes) synthesizer→tracker.evaluar_convicciones_vencidas→web_exporter (`daily_pipeline.yml:54-97`)
  5. Commit `data/*.json` + `data/macro.db` al mismo repo (`daily_pipeline.yml:101-119`)
  6. Checkout `leomattiolipa88/fearnot-web` con PAT (`daily_pipeline.yml:124-129`)
  7. Copiar `data/web_data.json` a `fearnot-web/public/`, commit + push (`daily_pipeline.yml:134-159`)
  8. Summary + `health_check.py` con `if: always()` (`daily_pipeline.yml:164-181`)

### Vercel

- Deploy del repo `fearnot-web` es implícito: el `if: always()` mode del step 7 pushea `public/web_data.json`; Vercel redeploya en 30-60s (`daily_pipeline.yml:158`, `README.md:41-45`).
- **No determinable:** configuración exacta de Vercel (branch, build command custom) — no hay `vercel.json` verificado.

### Local

- `update_web.sh` duplica el pipeline local. Hardcodea paths `~/Desktop/macro_agent` y `~/Desktop/fearnot-web` (`update_web.sh:32, 43, 87, 93`). Documentado como deuda en `TECHNICAL_DEBT.md#2` (líneas 73-81).
- Los agentes leen `.env` con parser ad-hoc (ej. `og_agent.py:26-33`, `technical_agent.py:42-46`, `synthesizer.py:28-34`) — deuda `TECHNICAL_DEBT.md#1`.
- El colector macro toma la key de env directamente (`collector.py:609`), sin `.env`. Inconsistente con los agentes.

### Manual

- Todo lo del workstream bancos/SEC (`banking_collector*.py`, `banking_agent*.py`, `financials_extractor*.py`). Nadie los llama; corren desde CLI si el usuario lo pide.
- `tracker.py reporte` (CLI, `tracker.py:610-615`).
- `debug_sec.py`, `test_cik.py`, `test_financials.py`, `test_sec.py`, `limpiar_duplicados.py`: scripts sueltos.
- `patch_agent_options.py`, `patch_options_flow.py`: ya aplicados (los patches viven ya en `technical_agent.py`/`technical_collector.py`). No deberían volver a correrse.
- Tests en `tests/`: no hay wiring de CI (`daily_pipeline.yml` no invoca pytest).

---

## 4. Workstream Bancos / SEC — estado exacto

**Diagnóstico corto:** este workstream está construido y documentado con profundidad, pero **totalmente desconectado del pipeline diario**. Es la mitad del sistema que quedó a medio hacer.

### 4.1 Estado por archivo

- `financials_extractor_v2.py` (`financials_extractor_v2.py:1-45`)
  - Descarga SEC EDGAR companyfacts JSON, mapea concepto→tag vía `gaap_taxonomy.py`/`ifrs_taxonomy.py` con dispatch por sector (`sector_router.py`).
  - Reemplaza `financials_extractor.py` v1 (yfinance-based, `financials_extractor.py:1-15`). El coexistir de v1+v2 es deuda `TECHNICAL_DEBT.md#9`.
  - **Auditoría 2026-06-08:** un audit de Opus 4.7 declaró que el extractor trimestral estaba "estructuralmente roto"; verificación contra JSON crudo refutó tres de sus hallazgos más severos (`TECHNICAL_DEBT.md:212-238`). El core no fue tocado.
  - Bug latente #1: `unidad="USD"` hardcodeado en toda la cadena trimestral (`TECHNICAL_DEBT.md:247-258`) — no dispara hoy porque NU reporta en USD; latente si se agrega EPS/shares o filer IFRS no-USD.
  - Bug latente #2: dedup por `filed desc` puede preferir restated sobre original (`TECHNICAL_DEBT.md:260-269`).
  - Bug latente #3: `is_flow` decide de `records[0]` solamente (`TECHNICAL_DEBT.md:272-278`).
  - Problema real pendiente #1: cobertura de OCF/capex quarterly desigual — hay que derivar Q = YTD_n − YTD_(n−1) para varios tickers tech (`TECHNICAL_DEBT.md:281-293`). Es la piedra en el zapato para FCF.

- `banking_collector.py` (`banking_collector.py:1-58`)
  - Anual. Extrae 6 conceptos crudos (`banking_collector.py:29-36`) para 7 bancos (`banking_collector.py:19`), calcula 3 métricas derivadas via `calculated_metrics.py`, persiste en `banking_financials` (long format, `banking_collector.py:44-56`).
  - **No corre en producción.**

- `banking_collector_q.py` (`banking_collector_q.py:1-56`)
  - Trimestral. Mismos 6 conceptos, usa `extraer_serie_trimestral` con reconstrucción Q4 (`banking_collector_q.py:9-15`).
  - Tabla `banking_financials_q` con `period` TEXT (`banking_collector_q.py:40-53`) — puede convivir con anual.
  - **No corre en producción.**

- `banking_agent.py` (`banking_agent.py:1-73`)
  - Analista Claude (Marks + Mayo) del ciclo de crédito. Lee `banking_financials` anual + tesis macro/tecnica de disco.
  - Output: `data/tesis_banking_{fecha}.json` (`banking_agent.py:353`). `health_check.py:19-38` **no lo valida** (sólo valida `tesis_`, `tesis_tecnica_`, `tesis_og_`).
  - Tiene `adaptar_para_tracker` que asigna horizonte TRIMESTRAL + fuente `banking_desk` (`banking_agent.py:319-342`), pero el `__main__` (`banking_agent.py:345-357`) sólo hace print + save — **no llama al tracker**. Es huérfano incluso a nivel de tracker.
  - Recibe el fix de este mes: `from config import MODEL, extract_text` (`banking_agent.py:23`), `model=MODEL` (`banking_agent.py:272`), `extract_text(response)` (`banking_agent.py:277`).

- `banking_agent_q.py` (`banking_agent_q.py:1-16`)
  - Evolución trimestral: lee la SERIE de trimestres y le da al modelo la tendencia pre-procesada por `tendencia.py` (`banking_agent_q.py:135-138`), no valores sueltos.
  - Mismo destino: `data/tesis_banking_q_{fecha}.json` (`banking_agent_q.py:389`). `adaptar_para_tracker` con fuente `banking_desk_q` (`banking_agent_q.py:337-353`). `__main__` (`banking_agent_q.py:381-393`) no llama al tracker.
  - Fix de este mes aplicado (`banking_agent_q.py:26`, `banking_agent_q.py:309`, `banking_agent_q.py:314`).

- `tendencia.py` (`tendencia.py:4-88`): utilidad pura sin efectos. Usada solo por `banking_agent_q.py:27`.

- `sector_mappings/banking.py` (`sector_mappings/banking.py:1-27`): descripción de sub-tipos + métricas. **El import está comentado** en `sector_router.py:25` (`# TODO: agregar cuando se implemente`) — el router no lo carga. Existe pero es descriptivo/documental hoy.

- `gaap_taxonomy.py` (`gaap_taxonomy.py:1-17`), `ifrs_taxonomy.py` (`ifrs_taxonomy.py:1-15`): mapeos activos usados por `sector_router.py` + v2.

- `calculated_metrics.py` (`calculated_metrics.py:1-16`): reconstrucciones (ej. shares diluidas XOM). Import citado por `banking_collector.py:11`.

- `sector_mappings/tech.py`, `sector_mappings/energy.py`: overrides GAAP tech/energy usados por `sector_router.py:24,27`. **Energy overrides no se usan en el pipeline** porque el pipeline no hace extracciones SEC; sólo los usaría si se corre `financials_extractor_v2.py` manualmente sobre tickers energy.

### 4.2 TODOs, deuda y código comentado

- `sector_router.py:25-29`: 4 `# TODO` sin resolver (banking, insurance, industrial, utilities).
- `TECHNICAL_DEBT.md` (documento completo): 11 ítems abiertos + sección post-audit SEC + 2 latentes + 1 real pendiente (coverage OCF/capex quarterly).
- `LIMITATIONS.md` documenta 17 limitaciones estructurales (`LIMITATIONS.md:222-240`), varias con status "10-K parse family" que requieren un parser aparte que no existe (`LIMITATIONS.md:218`).
- `AUDIT_REPORT.md` está en el repo (`AUDIT_REPORT.md:1-10`) — la refutación vive en `TECHNICAL_DEBT.md:212-238` (deberían mergearse, o el AUDIT debería marcarse como "REFUTED").
- Scripts patch ya aplicados que siguen en repo (`patch_agent_options.py`, `patch_options_flow.py`) — visualmente sugieren código no aplicado, pero ya lo está.

### 4.3 Qué falta para conectar bancos al pipeline

1. Agregar `python banking_collector.py` + `python banking_collector_q.py` a `daily_pipeline.yml` (o hacerlos trimestrales, dado que los 10-K/10-Q no cambian a diario).
2. Agregar `python banking_agent.py` + `_q.py` con schedule realista (trimestral/mensual, no diario).
3. Extender `health_check.py:19-38` con `tesis_banking` y `tesis_banking_q`.
4. Hacer que `banking_agent*.py.__main__` llame al tracker (`registrar_senales(adaptar_para_tracker(output))`) — hoy no lo hacen.
5. Extender `web_exporter.py` para incluir el memo bancario. Hoy no lo mira (`web_exporter.py:24-48` sólo conoce `"macro"`, `"tecnica"`, `"og"`).
6. Descomentar `from sector_mappings import banking` en `sector_router.py:25` cuando esté listo para producción.

---

## 5. Calidad de datos por fuente

### FRED (Federal Reserve Economic Data)
- **Series consumidas:** `DGS10`, `DTB3`, `DFII10`, `T5YIFR`, `BAMLH0A0HYM2`, `ICSA`, `UNRATE`, `SAHMREALTIME`, `CPIAUCSL`, `PCEPILFE`, `MICH` (`collector.py:472-519`, orden real de fetch).
- **Frecuencia real:** diaria (yields, spreads), semanal (jobless_claims), mensual (unemployment, sahm, CPI, PCE, michigan).
- **Validación:**
  - Rango histórico por serie (`collector.py:34-57`).
  - Cambio máximo diario absoluto/relativo (`collector.py:212-238`).
  - Verificación cruzada FRED vs yfinance para `yield_10y` (30 bps) y `usdjpy` (1 yen) (`collector.py:561-564`).
- **Freshness (fix 2026-08-01):** `verificar_freshness` (`collector.py`) compara `(hoy − fecha_publicacion)` contra `FRESHNESS_MAX_DIAS`. Antes usaba `fecha_descarga` y hacía aparecer datos vencidos como frescos (`TECHNICAL_DEBT.md:295-303`, caso `michigan_inflation_exp` de 2026-05-01). La columna `fecha_publicacion` ya existía NOT NULL en la tabla `indicadores` (`collector.py:104`); no hizo falta migración de schema. Fallback defensivo a `fecha_descarga` + WARNING si por algún motivo la columna llega vacía.
- **`FRESHNESS_MAX_DIAS` (fix 2026-08-01):** toda serie fetched por `correr_colector()` tiene entrada explícita — el default 5 pasa a ser sólo red de seguridad. Bandas:
  - Diarios (yfinance / FRED daily): 1 día.
  - FRED con rezago típico: 2 días (`hy_spread`, `tips_yield_10y`, `breakeven_5y5y`).
  - Semanales (`jobless_claims`): 8 días.
  - Mensuales (`unemployment`, `sahm_rule`, `cpi`, `pce_core`, `michigan_inflation_exp`): 40 días para cubrir el rezago normal de publicación (~1 mes desde el mes observado).
  - Duplicado de `breakeven_5y5y` eliminado.

### EIA (Energy Information Administration)
- **Series consumidas:** inventarios crude/gasoline/distillate/propane, refining utilization, natgas storage — descriptas en `og_collector.py:1-15` (docstring). **No determinable en detalle:** no llegué a leer el fetch loop completo por longitud del archivo.
- **Frecuencia real:** semanal (Wednesday EIA reports).
- **Validación:** persiste en `indicadores_eia` (leída por `og_agent.py:184-195`). El agente recibe fecha de publicación y descripción — puede razonar sobre frescura textualmente, no hay flag `es_fresco`.

### yfinance
- **Series:** FX (DXY, USDJPY, EURUSD, USDCNY, USDBRL, USDMXN), equities (SPY, QQQ, TLT, GLD, VIX), yield_10y_mkt, usdjpy_mkt (`collector.py:524-557`); técnicos (200DMA, momentum 12M) para 6 activos + muestra de 50 tickers para breadth (`technical_collector.py:38-63`); OG futures + equities (`og_collector.py:39-53`); options flow (VIX9D/6M, put/call) (`options_flow_collector.py:1-15`); tracker (precios entrada/salida de señales y convicciones, `tracker.py:143-146, 205-209`); banking N/A (SEC).
- **Validación:** rango + cambio diario (`collector.py:192-240`) sólo en `collector.py`. `technical_collector.py`, `og_collector.py`, `options_flow_collector.py` no aplican el mismo framework — validación implícita ("si empty, log warning").
- **Riesgo típico:** yfinance devuelve NaN silenciosamente en fines de semana/holidays; el DXY tiene gaps (`technical_collector.py:107-108` compensa con más días de descarga).

### NewsAPI (news_collector.py + og_news_collector.py)
- **Endpoint:** `/v2/top-headlines` free-tier (`news_collector.py:14`).
- **Categorías (query):** business, technology, general (`news_collector.py:17`).
- **Filtro de inclusión:** keyword-based sobre título+descripción (`news_collector.py:27-43, 73-74`) — decide si la noticia pasa el umbral de relevancia macro.
- **Clasificación (fix 2026-08-01):** matching con word boundary (`re.search(r"\b<kw>\b", texto)`) contra la constante `_CATEGORIAS_KEYWORDS` a nivel módulo. Default `OTROS` explícito cuando ningún keyword calza como palabra completa (antes: `MACRO GLOBAL`). Corta el caso "fed" ⊂ "federation" que llevaba titulares tipo "FIFA federation boycott" a POLÍTICA MONETARIA (`TECHNICAL_DEBT.md:305-314`).
- **Cache:** 30 min (`news_collector.py:203`).
- **Tiering:** hardcoded (`news_collector.py:20-24`).
- **Freshness:** no explícita; se descarga fresh o cache <30 min.

### SEC EDGAR (workstream banking/SEC, hoy dormido)
- Ver §4. Contrato de calidad por concepto en `LIMITATIONS.md` (17 casos documentados).
- Cada valor extraído lleva `quality` flag: `direct`, `calculated_from_*`, `not_found`, `approximation_with_known_bias` (`banking_agent.py:51`, `LIMITATIONS.md:16-19`).

---

## 6. Higiene — evaluación

Escala 1-10 donde 5 = "aceptable para prototipo personal", 8+ = "mantenible por un tercero sin pain".

| Área | Nota | Justificación (con cita) |
|---|---:|---|
| Documentación de decisiones | **8** | `README.md` + `LIMITATIONS.md` (253 líneas, 17 casos) + `TECHNICAL_DEBT.md` (306 líneas, 11 ítems + post-audit) + docstrings largos por módulo. El why está registrado. Falla: `CLAUDE.md` no existe. |
| Arquitectura del pipeline | **7** | Cada agente hace una cosa, contratos claros (JSON de disco), health_check al final (`health_check.py:19-38`). Costos: el orquestador es un `.yml` con `if [ ... ]` en bash (`daily_pipeline.yml:85-90`) — no hay DAG. |
| Configuración | **4** | `.env` parseado con mini-parsers duplicados en 4 agentes (`TECHNICAL_DEBT.md#1`); `update_web.sh` con paths hardcodeados (`TECHNICAL_DEBT.md#2`); `collector.py:609` toma la key sin `.env`. Recién ahora se centralizó `MODEL` en `config.py`. |
| Duplicación / dead code | **3** | Root tiene 7 archivos muertos declarados (`TECHNICAL_DEBT.md#8`); v1+v2 de extractor conviven (`TECHNICAL_DEBT.md#9`); `sector_overrides` duplicado entre `gaap_taxonomy.py` y `sector_mappings/*` (`TECHNICAL_DEBT.md#4`); `FRESHNESS_MAX_DIAS` tiene `breakeven_5y5y` dos veces (`collector.py:74, 79`); `data.ts` desincronizado con el output real de `web_exporter`. |
| Tests | **2** | Sólo `tests/test_collector.py` y `tests/test_tech_coverage.py`. Ninguno se corre en Actions (`daily_pipeline.yml` sin pytest). El sistema depende del `health_check.py` como único guardián en prod. Documentado como deuda (`TECHNICAL_DEBT.md#3, #7`). |
| Observabilidad / operational | **6** | `health_check.py` con `if: always()` (`daily_pipeline.yml:180`) da email de fallo. Cada agente valida su output (ver `agent.py:129-194`, `technical_agent.py:181-224`, `og_agent.py:280-334`, `synthesizer.py:289-327`). No hay métricas agregadas persistidas por run (hit rate del pipeline en sí, no de las tesis). |
| Seguridad / secrets | **7** | `.env` en `.gitignore` (`.gitignore:3`); secrets vía GitHub Actions (`daily_pipeline.yml:50-53, 129`). `.env.example` publicado (`.env.example:1-19`). Falla: `og_agent.py:26-33` (y análogos) parsean `.env` de forma naive — un valor con `=` interno se rompe (`line.split("=", 1)` lo mitiga en parte). |
| Manejo de errores en agentes | **7** | `validar_*` en cada agente descarta señales malformadas antes del tracker (ej. `agent.py:265-282`, `technical_agent.py:308-322`, `og_agent.py:388-402`). Reintentos ×2 en la llamada a Claude. |
| Frontend consistency | **5** | `page.tsx:8-28` y `data.ts:19-51` declaran shapes distintos. Vive porque `page.tsx` no importa `data.ts`. Rompe cuando se refactorice. |
| Data lineage | **8** | `data/macro.db` versionado en el repo (`.gitignore:43-45` con explicación); cada tesis y `web_data.json` timestampeadas y auditables (`README.md:52-59`). Zero backfills prometidos. |

**Promedio global (media aritmética): 5.7.** Prototipo personal maduro; le falta pasar a "sistema mantenible por un tercero".

---

## 7. Backlog priorizado

Ordenado por *impacto × urgencia*. Cada ítem cita el ancla en el código o en la deuda existente.

1. ~~**Arreglar `verificar_freshness` para usar `fecha_publicacion`.**~~ **RESUELTO 2026-08-01** — `collector.py:verificar_freshness` ahora compara contra `fecha_publicacion` con fallback defensivo a `fecha_descarga` + WARNING (`TECHNICAL_DEBT.md:295-303`).

2. **Wirear el workstream bancos al pipeline o marcarlo `DEPRECATED`.** Hoy `banking_collector*.py` y `banking_agent*.py` están dormidos (§4). O agregar steps a `daily_pipeline.yml` (probablemente con schedule trimestral aparte, no diario) + extender `health_check.py:19-38` + hacer que `banking_agent*.__main__` llame al tracker; o mover todo a `scripts/deferred/`.

3. **Eliminar `banking_agent.py` no-tracker gap.** Los `__main__` de banking_agent y banking_agent_q **no** llaman al tracker (contraste con `agent.py:365-371`, `technical_agent.py:385-388`, `og_agent.py:494-497`). Cualquier ejecución manual pierde las señales.

4. **Unificar la carga de `.env`.** `TECHNICAL_DEBT.md#1`: reemplazar los mini-parsers en `agent.py`, `technical_agent.py:42-46`, `og_agent.py:26-33`, `synthesizer.py:28-34`, `og_collector.py:29-35`, `og_news_collector.py:24-30`, `banking_agent*.py` por `python-dotenv`. Además hoy `collector.py:609` no usa `.env` — inconsistente.

5. ~~**Corregir el clasificador de noticias.**~~ **RESUELTO 2026-08-01** — `news_collector.py:clasificar` usa word-boundary regex + default `OTROS` explícito (`TECHNICAL_DEBT.md:305-314`). Clasificación por LLM barato queda pendiente como iteración futura si el default honesto no basta.

6. **Limpiar dead code del root.** `debug_sec.py`, `patch_agent_options.py`, `patch_options_flow.py`, `test_cik.py`, `test_financials.py`, `test_sec.py`, `limpiar_duplicados.py` a `scripts/legacy/` (`TECHNICAL_DEBT.md#8`). Además decidir entre `financials_extractor.py` v1 y v2 (`TECHNICAL_DEBT.md#9`).

7. ~~**Corregir `FRESHNESS_MAX_DIAS` duplicado.**~~ **RESUELTO 2026-08-01** — dict re-escrito con toda serie fetched declarada explícitamente; duplicado eliminado; monthlies con `max_dias=40` (`collector.py:63-102`, `TECHNICAL_DEBT.md:295-303`).

8. **Cobertura de OCF/capex quarterly en tech.** `TECHNICAL_DEBT.md:281-293`. Bloquea FCF, que es la métrica de verificación de "growth real vs SBC/acct". Derivar Q_n = YTD_n − YTD_(n-1) por ticker; cuidado con non-calendar filers (mismo trap que produjo el -30.2 en NVDA Q4 según la nota).

9. **Sincronizar `app/lib/data.ts` con el output real de `web_exporter.py`.** Hoy tiene campos fantasma (`tecnicos`, `performance`, `invalidadores_tecnicos`) que no existen. `app/page.tsx` esquiva el problema declarando su propio type. Rompe al primer refactor.

10. **CI para tests + validación de `requirements.txt`.** `TECHNICAL_DEBT.md#3, #7`. Agregar step de `pytest` a `daily_pipeline.yml` y `pipreqs`/`pip-check` para catch de imports huérfanos. Hoy `health_check.py` es el único guardián en prod, y sólo mira los outputs finales — no la lógica.

---

## Cosas que no pude verificar

- Contenido de `app/research/DailyPulseCard.tsx`, `EnergyPulseSection.tsx`, `components/Header.tsx`, `lib/papers.ts`, `globals.css` — sé que existen (importados desde archivos que sí leí) pero no revisé su cuerpo.
- `.py` fuera de las carpetas listadas (raíz, `sector_mappings/`, `tests/`). Sin `find`/`grep` no puedo enumerar exhaustivamente.
- Cronograma real de commits al repo `fearnot-web` desde Vercel (no revisé `.vercel/`).
- Contenido de `data/` (tesis históricas, tamaño de la DB).
- Si `AUDIT_REPORT.md` (referenciado en `TECHNICAL_DEBT.md:216`) tiene contexto adicional que no leí más allá del header — sólo leí sus primeras 10 líneas.
- Nada de contenido dinámico de `data/macro.db` (schemas los inferí de los `CREATE TABLE` en los colectores).
