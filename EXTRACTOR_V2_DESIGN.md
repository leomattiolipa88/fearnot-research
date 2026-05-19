# Financials Extractor V2 — Design Document

**Status:** Sub-paso 4 — implementación pendiente
**Date:** 2026-05-16
**Source:** SEC EDGAR API (us-gaap taxonomy)
**Author:** Basilio Boschi

## Objective

Extractor de financials usando SEC EDGAR como fuente primaria (vs yfinance en v1). Mismas 16 métricas, datos verificados, soporta empresas con fiscal years non-calendar.

## Scope

**Phase 1 (esta implementación):** 9 empresas del portfolio personal
- XOM (Exxon Mobil) — CIK 0000034088
- META (Meta Platforms) — CIK 0001326801
- NOW (ServiceNow) — CIK 0001373715
- VST (Vistra) — CIK 0001692819
- AMCR (Amcor) — CIK 0001748790
- PENG (Penguin Solutions) — CIK 0001616533 — *non-calendar fiscal year (Aug)*
- MELI (MercadoLibre) — CIK 0001099590 — *ADR*
- NU (Nu Holdings) — CIK 0001691493 — *banco, taxonomía especial*
- BRK-B (Berkshire Hathaway) — CIK 0001067983 — *holding*

**Phase 2 (futuro):** watchlist extendida (~30 empresas)
**Phase 3 (futuro):** S&P 500
**Phase 4 (largo plazo):** todas las USA listed

## Architecture

### Modular by category (Decision 3)

```python
def extraer_financials_v2(ticker, fiscal_year):
    cik = obtener_cik(ticker)
    facts = obtener_facts(cik)
    fy_period = detectar_fiscal_year_period(facts, fiscal_year)

    raw = extraer_raw_numbers(facts, fy_period)
    raw_prev = extraer_raw_numbers(facts, fy_period_anterior)
    market_data = obtener_market_data(ticker)  # yfinance

    return {
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        **raw,
        **calcular_profitability(raw),
        **calcular_growth(raw, raw_prev),
        **calcular_leverage(raw),
        **calcular_quality(raw),
        **calcular_valuation(raw, market_data),
        "metadata": {...}
    }
```

### Files

- `financials_extractor_v2.py` — main module
- `gaap_taxonomy.py` — mapping GAAP names → conceptual metrics
- `test_financials_v2.py` — validación contra v1

## Key design decisions

1. **Universe:** portfolio (9 companies)
2. **Fiscal years:** flexible filter (detect period from start/end, not just calendar)
3. **Code structure:** modular by category
4. **GAAP mapping:** global dict of "possible names" per metric
5. **Market data:** hybrid — SEC for fundamentals, yfinance for price/shares
6. **Validation:** v1 (yfinance) as ground truth, flag discrepancies >5%
7. **Storage:** same DB, new table `financials_sec`

## The 16 metrics

### Profitability (4)
- Operating Margin = Operating Income / Revenue
- Net Profit Margin = Net Income / Revenue
- ROE = Net Income / Stockholders Equity
- ROIC = NOPAT / Invested Capital

### Growth (3)
- Revenue Growth YoY
- Net Income Growth YoY
- FCF Growth YoY

### Leverage (4)
- Debt / Equity
- Interest Coverage = Operating Income / Interest Expense
- Current Ratio = Current Assets / Current Liabilities
- Net Debt / EBITDA

### Quality (3)
- FCF / Net Income
- CapEx / Depreciation
- Asset Turnover = Revenue / Total Assets

### Valuation (3)
- P/E Ratio = Price / EPS
- EV / EBITDA
- FCF Yield = FCF / Market Cap

## Special cases

### Non-calendar fiscal years
- PENG: ends last Friday of August
- Solution: detect fiscal_year_end_month from facts, build start/end dynamically

### Banks (NU)
- No "Operating Margin" tradicional
- Revenue ≠ Revenues — uses "InterestAndDividendIncomeOperating"
- Solution: per-sector mapping override (TBD)

### ADRs (MELI)
- May have limited facts in SEC EDGAR
- Solution: fallback to yfinance if SEC returns <80% of expected facts

### Holdings (BRK-B)
- Reports consolidated, no specific operating income
- Solution: best-effort, flag low confidence

## Output schema

```json
{
  "ticker": "XOM",
  "fiscal_year": 2025,
  "raw": {
    "revenue": 332238000000,
    "net_income": 28844000000,
    ...
  },
  "metrics": {
    "operating_margin": 0.102,
    "roe": 0.111,
    ...
  },
  "metadata": {
    "source": "sec_edgar",
    "fiscal_year_end": "2025-12-31",
    "filed_date": "2026-02-18",
    "validation_against_v1": {
      "matched": true,
      "discrepancies": []
    }
  }
}
```
