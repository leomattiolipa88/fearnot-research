# FearNot Research — Known Limitations

This document tracks **structural limitations** of the extraction system caused by external factors (filer reporting choices, taxonomy gaps, regulatory disclosure rules). These are NOT bugs — they describe how reality limits what XBRL extraction can achieve.

For internal code debt and improvement opportunities, see `TECHNICAL_DEBT.md`.

---

## Format

Each limitation entry includes:

- **Affects:** Which tickers/sectors hit this
- **Concept:** Which financial concept can't be extracted
- **Root cause:** Why (filer choice, taxonomy gap, etc.)
- **Workaround:** What the system does instead
- **Validation:** How to verify (10-K reference if available)
- **Discovered:** When this was confirmed

---

## Sector: Technology

### 1. AMZN — Research and Development not reported separately

- **Affects:** AMZN (Amazon)
- **Concept:** `research_and_development`
- **Root cause:** Amazon does not report a standalone "Research and Development" line in its income statement. R&D costs are bundled inside `"Technology and Infrastructure"` (formerly `"Technology and Content"` pre-2022), which combines R&D + AWS infrastructure + content creation costs.
- **Workaround:** Extractor returns `not_found`. No fallback applied because the combined number would introduce significant upward bias (~2-3x true R&D).
- **Validation:** Amazon 10-K FY2024, Income Statement page. The closest tag is `us-gaap:TechnologyAndContentExpense` but it's not pure R&D.
- **Discovered:** May 20, 2026 (Tech sector validation)

### 2. NVDA, MU — Selling & Marketing combined with G&A

- **Affects:** NVDA (NVIDIA), MU (Micron)
- **Concept:** `selling_marketing_expense`
- **Root cause:** Semiconductor companies typically report `SellingGeneralAndAdministrativeExpense` as a combined line. This is industry-standard practice for semis given B2B sales channels with concentrated customers (no consumer marketing spend to separate).
- **Workaround:** Extractor returns `not_found` for `selling_marketing_expense`. The combined value gets captured in `general_administrative_expense` via the taxonomy fallback (which includes `SellingGeneralAndAdministrativeExpense` as one of its names).
- **Validation:** NVIDIA 10-K FY2024 reports `"Selling, general and administrative"` as single line $2.7B. Micron 10-K FY2024 similar.
- **Discovered:** May 20, 2026 (Tech sector validation)

### 3. CRM, NOW — Interest Expense not reported as separate line

- **Affects:** CRM (Salesforce), NOW (ServiceNow)
- **Concept:** `interest_expense`
- **Root cause:** SaaS pure-play companies that are net cash positive don't report `interest_expense` as a separate line item on the income statement. Interest income exceeds interest expense, so they report net (e.g., `"Other income, net"` that includes both).
- **Workaround:** Extractor returns `not_found`. For analysis purposes, `interest_expense ≈ 0` is a reasonable approximation since gross interest expense is structurally minimal for these companies.
- **Validation:** CRM 10-K FY2024, NOW 10-K FY2024. Both have positive net interest income.
- **Discovered:** May 18, 2026 (Universal Fixes session)

### 4. SaaS — NDR and ARR not in XBRL

- **Affects:** CRM, NOW, all SaaS pure-play
- **Concept:** Net Dollar Retention (NDR/NRR), Annual Recurring Revenue (ARR)
- **Root cause:** These are non-GAAP managerial metrics disclosed in MD&A, earnings presentations, or IR releases — NOT in standard XBRL facts. Ordway research found 30 different names for NDR across 97 SaaS companies, confirming the lack of standardization.
- **Workaround:** Out of scope for XBRL extractor. Would require MD&A scraping or earnings release parsing — separate project.
- **Validation:** Any SaaS earnings release vs. their 10-K XBRL exhibit.
- **Discovered:** Iteration 1 Tech research (May 2026)

---

## Sector: Energy

### 5. XOM — Operating Income components not exposed in XBRL

- **Affects:** XOM (Exxon Mobil), likely CVX, OXY, EOG, VLO (pending verification)
- **Concept:** `operating_income` (exact value)
- **Root cause:** Integrated oil majors aggregate many cost lines into `CostsAndExpenses` rather than exposing individual components (Sales operating revenue separated, crude purchases, production expense, etc.). Without components, exact Operating Income cannot be reconstructed from XBRL facts alone.
- **Workaround:** `calcular_operating_income_aproximado()` in `calculated_metrics.py` uses formula `IncomeBeforeTax + InterestExpense` with quality flag `approximation_with_known_bias`. For XOM 2025: approximation $41.87B vs reported $33.54B (bias +21%, typical for integrated majors). Future option: HTML parser of 10-K for exact line items.
- **Validation:** XOM 10-K FY2024 + comparison with reported Operating Income in earnings release.
- **Discovered:** May 18, 2026 (Energy sector deep-dive)

### 6. VIST — Reports in IFRS, not US-GAAP

- **Affects:** VIST (Vista Energy)
- **Concept:** All concepts (entire extraction pipeline)
- **Root cause:** Vista Energy is an Argentine company (Vaca Muerta E&P) that files 20-F with IFRS taxonomy (`ifrs-full`), not 10-K with us-gaap. The current extractor only handles us-gaap.
- **Workaround:** VIST extraction will fail entirely until IFRS support is added (similar to what's planned for NU Holdings).
- **Validation:** Vista Energy SEC filings — search by CIK 1671933.
- **Discovered:** Iteration 1 Energy research

---

## Sector: Banking

### 7. JPM, BAC — CECL provision tags use custom extensions

- **Affects:** JPM, BAC, and most large US banks post-2020
- **Concept:** `provision_for_credit_losses`
- **Root cause:** When CECL (Current Expected Credit Loss) accounting standard took effect in 2020, banks adopted custom XBRL extensions for the new provision concept rather than using the legacy `us-gaap:ProvisionForLoanLeaseLosses`. Each bank's exact tag differs slightly.
- **Workaround:** Banking sector module (`sector_mappings/banking.py`) not yet implemented. When built, taxonomy will include multiple CECL-era fallbacks.
- **Validation:** JPM FY2023 10-K XBRL exhibit.
- **Discovered:** Iteration 1 Banking research

### 8. NU — Custom IFRS extensions throughout

- **Affects:** NU (Nu Holdings)
- **Concepts:** Most concepts (interest income, transactional expenses, credit loss allowance, deposits, etc.)
- **Root cause:** Nu Holdings uses extensive custom IFRS extensions (`nu:` prefix) because the standard IFRS taxonomy doesn't have elements specific to Brazilian digital banking conventions. Their P&L combines IFRS 9 effective-interest revenue with FVTPL gains/losses in a single custom line.
- **Workaround:** Requires dedicated IFRS extension parser. Out of scope for v2 extractor.
- **Validation:** Nu Holdings 20-F FY2024, SEC accession 0001292814-25-001517.
- **Discovered:** Iteration 2 NU IFRS deep-dive

---

## Sector: Utilities

### 9. VST — Adjusted EBITDA not in XBRL

- **Affects:** VST (Vistra Corp), all merchant power generators
- **Concept:** `adjusted_ebitda` (the operating KPI for merchant power)
- **Root cause:** Adjusted EBITDA is a non-GAAP measure defined by the filer's CODM (Chief Operating Decision Maker). It strips unrealized commodity MTM, impairments, restructuring, etc. Each company's definition differs slightly, and it's reported only in MD&A and earnings releases — not as a standard XBRL fact.
- **Workaround:** Out of scope for XBRL extractor. Vistra reports it by segment (Texas, East, West, etc.) which adds further complexity.
- **Validation:** VST FY2023 10-K, accession 0001692819-24-000012.
- **Discovered:** Iteration 1 Utilities research

---

## Cross-cutting: Capital Adequacy (CET1, Tier 1)

### 10. Bank capital ratios are narrative-tagged only

- **Affects:** All banks (JPM, BAC, NU's Brazilian regulated subsidiaries)
- **Concepts:** `cet1_ratio`, `tier_1_capital_ratio`, `total_capital_ratio`
- **Root cause:** Both us-gaap and ifrs-full only have generic capital-disclosure block-tags (e.g., `ifrs-full:DisclosureOfCapitalRequirementsExplanatory`). The actual ratio numbers are embedded in the disclosure text, not tagged as discrete numerical facts.
- **Workaround:** Parse from Capital management note text-blocks (requires NLP), or supplement from regulator databases (BACEN IF.DATA for NU's Brazilian subs, FDIC Call Reports for US banks).
- **Validation:** Any bank 10-K Capital Management note.
- **Discovered:** Iteration 2 NU IFRS deep-dive

---

## Summary Table

| # | Sector | Concept | Affects | Severity | Workaround |
|---|--------|---------|---------|----------|------------|
| 1 | Tech | research_and_development | AMZN | Medium | Accept not_found |
| 2 | Tech | selling_marketing_expense | NVDA, MU | Low | Captured in G&A |
| 3 | Tech | interest_expense | CRM, NOW | Low | Accept not_found, treat as ~0 |
| 4 | Tech | NDR, ARR | All SaaS | High | Out of scope (MD&A only) |
| 5 | Energy | operating_income exact | XOM (likely others) | Medium | Approximation with bias flag |
| 6 | Energy | All concepts | VIST | High | IFRS support needed |
| 7 | Banking | CECL provision | JPM, BAC | Medium | Sector module pending |
| 8 | Banking | All concepts | NU | High | Custom IFRS parser needed |
| 9 | Utilities | Adjusted EBITDA | VST | High | Out of scope (non-GAAP) |
| 10 | Banking | CET1, Tier 1 | All banks | Medium | Parse text-blocks or external data |

---

## Adding a new limitation

When you discover a new limitation:

1. Add an entry to the appropriate sector section above (or create new section)
2. Include all 6 fields (Affects, Concept, Root cause, Workaround, Validation, Discovered)
3. Update the Summary Table
4. If it's truly fixable with code, move it to `TECHNICAL_DEBT.md` instead
5. Commit with message like: `docs: add limitation [SECTOR] [CONCEPT] discovered [DATE]`
