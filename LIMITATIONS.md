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

### 8. NU — IFRS-full taxonomy (no custom extensions)

- **Affects:** NU (Nu Holdings)
- **Concept:** All concepts (IFRS taxonomy dispatch)
- **Root cause:** Nu Holdings reports under IFRS via 20-F. All facts are in standard `ifrs-full` namespace - no custom `nu:` extensions exist. SEC EDGAR companyfacts API exposes 151 IFRS concepts.
- **Workaround:** Resolved via dual taxonomy infrastructure (`ifrs_taxonomy.py` + `is_ifrs_filer()` dispatch in `financials_extractor_v2.py`). Phase 1 of Banking module complete as of May 21, 2026.
- **Validation:** NU CIK 0001691493 companyfacts API direct query. FY2024: Revenue \$11.5B, Net Income \$1.97B, Total Assets \$49.9B - all match published 20-F.
- **Discovered:** May 21, 2026 (empirical discovery contradicted prior research markdown which inferred ~15 UNVERIFIED `nu:` custom tags that proved non-existent)
- **Lesson:** Research markdown that lists XBRL tags as "UNVERIFIED" requires empirical verification before code commitment. Inferred PascalCase tag names are systematically unreliable.

### 9. WFC, GS — Total loan portfolio not reported as XBRL discrete fact

- **Affects:** WFC (Wells Fargo), GS (Goldman Sachs)
- **Concept:** `loans_held_for_investment`
- **Root cause:** WFC and GS do not tag a single aggregate "total loans" value in their XBRL filings. Loan portfolio is broken down by category (commercial, residential, consumer, etc.) in MD&A notes but no roll-up XBRL fact exists. JPM, BAC, C, MS all report the aggregate via `FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss` (~\$1.3T JPM, \$1.1T BAC, \$676B C, \$226B MS verified FY2024). WFC and GS only expose securities lending tags, individual loan categories, and fair value subsets - top tag is `SecuritiesLoaned...` (\$149B WFC, \$67B GS) which is NOT loans-to-customers.
- **Workaround:** Extractor returns `not_found` for WFC and GS. Banking analysis affected: Loan-to-Deposit Ratio not calculable. Note that LDR for GS is structurally irrelevant (i-bank model, not NIM-driven) but for WFC it is a material metric.
- **Future resolution path:** Two options when this becomes priority:
  1. Compose total loans from sub-category tags (residential + commercial + consumer). Risk: double-counting if categories overlap. Requires per-bank verification.
  2. MD&A scraping from 10-K. Universal solution but adds NLP dependency.
- **Priority:** Medium. WFC LDR is the only material analytical gap. GS does not need this metric.
- **Validation:** Empirical discovery via companyfacts API on May 26, 2026. WFC FY2024 10-K MD&A reports total loans \$910B; GS FY2024 10-K reports total loans \$190B - neither value available as discrete XBRL fact.
- **Discovered:** May 26, 2026 (Banking US-GAAP empirical discovery)

### 10. NU — Five banking concepts have tags but no FY2024 values

- **Affects:** NU (Nu Holdings)
- **Concepts:** `provision_for_credit_losses`, `general_administrative_expense`, `depreciation`, `allowance_for_credit_losses`, `expected_credit_loss_rate`
- **Root cause:** These tags exist in NU's IFRS taxonomy (verified via companyfacts) but NU did not report FY2024 values as discrete XBRL facts. Most likely embedded inside `OperatingExpense` aggregate or only disclosed in 20-F notes (not XBRL-tagged). NU did report `IncreaseDecreaseInAllowanceAccountForCreditLossesOfFinancialAssets` for FY2023 (\$2.3B) and earlier years - the FY2024 absence is a recent disclosure change.
- **Workaround:** Extractor returns `not_found` for these concepts on NU. Documented in `ifrs_taxonomy.py` notes per-concept. NU coverage stands at 14/24 universal concepts; Banking-specific concepts will be added in Phase 2.
- **Future resolution path:** Parse NU 20-F notes for FY2024 specifically. Required for accurate NIM and Cost of Risk calculations on NU.
- **Priority:** High for NIM analysis. NU is a digital bank where Cost of Risk (provisions / avg loans) is a key thesis driver.
- **Validation:** Empirical verification via NU companyfacts API May 21, 2026. Tags present in taxonomy keys but FY2024 entries absent or zero.
- **Discovered:** May 21, 2026 (Banking Phase 1 IFRS verification)

### 11. GS — Trading revenue not reported as discrete XBRL fact

- **Affects:** GS (Goldman Sachs)
- **Concept:** `trading_revenue`
- **Root cause:** Goldman Sachs has the largest trading operation among US banks (~\$25B annual trading revenue per disclosures) but does not tag this in standard XBRL fact namespace. Other banks report `PrincipalTransactionsRevenue` (JPM: \$24.8B, C: \$11.6B) or `TradingGainsLosses` (BAC: \$13B, WFC: \$5.3B, MS: \$16.8B). GS exposes the tags in facts but with no FY2024 value.
- **Workaround:** Extractor returns `not_found` for GS trading revenue. For GS analysis, parse 10-K Form 10-K "Trading Results" section directly.
- **Future resolution path:** Custom GS-specific parser, or accept that GS analysis requires manual data input.
- **Priority:** High for GS analysis. Trading is GS's largest revenue line and core to thesis.
- **Validation:** Empirical via companyfacts API May 26, 2026.
- **Discovered:** May 26, 2026 (Banking US-GAAP empirical discovery)

### 12. Banking — `fee_and_commission_income` not aggregated in XBRL

- **Affects:** All 6 US banks (JPM, BAC, WFC, C, MS, GS) to varying degrees
- **Concept:** `fee_and_commission_income`
- **Root cause:** XBRL us-gaap taxonomy fragments fee income across many specific tags (`InvestmentBankingAdvisoryBrokerageAndUnderwritingFeesAndCommissions`, individual product fees, etc.) rather than one aggregate. Only Citigroup reports a sizeable aggregate via the IB-specific tag. JPM and MS have `FeesAndCommissions` tag in facts but no FY2024 value. BAC, WFC, GS don't expose any aggregate.
- **Workaround:** Use `NoninterestIncome` (universal: \$85B JPM, \$46B BAC, \$35B WFC, \$27B C, \$53B MS, \$45B GS) as proxy for "non-interest revenue." Fee income is a major sub-component but not isolatable.
- **Future resolution path:** When needed for fee-income trend analysis: compose from product-specific tags per bank (requires per-bank tag mapping), or parse income statement breakdown from 10-K.
- **Priority:** Low. `NoninterestIncome` aggregate is sufficient for most analytical use cases.
- **Validation:** Empirical via companyfacts API May 26, 2026.
- **Discovered:** May 26, 2026 (Banking US-GAAP empirical discovery)

---

## Sector: Utilities

### 13. VST — Adjusted EBITDA not in XBRL

- **Affects:** VST (Vistra Corp), all merchant power generators
- **Concept:** `adjusted_ebitda` (the operating KPI for merchant power)
- **Root cause:** Adjusted EBITDA is a non-GAAP measure defined by the filer's CODM (Chief Operating Decision Maker). It strips unrealized commodity MTM, impairments, restructuring, etc. Each company's definition differs slightly, and it's reported only in MD&A and earnings releases — not as a standard XBRL fact.
- **Workaround:** Out of scope for XBRL extractor. Vistra reports it by segment (Texas, East, West, etc.) which adds further complexity.
- **Validation:** VST FY2023 10-K, accession 0001692819-24-000012.
- **Discovered:** Iteration 1 Utilities research

---

## Cross-cutting: Capital Adequacy (CET1, Tier 1)

### 14. Bank capital ratios are narrative-tagged only

- **Affects:** All banks (JPM, BAC, NU's Brazilian regulated subsidiaries)
- **Concepts:** `cet1_ratio`, `tier_1_capital_ratio`, `total_capital_ratio`
- **Root cause:** Both us-gaap and ifrs-full only have generic capital-disclosure block-tags (e.g., `ifrs-full:DisclosureOfCapitalRequirementsExplanatory`). The actual ratio numbers are embedded in the disclosure text, not tagged as discrete numerical facts.
- **Workaround:** Parse from Capital management note text-blocks (requires NLP), or supplement from regulator databases (BACEN IF.DATA for NU's Brazilian subs, FDIC Call Reports for US banks).
- **Validation:** Any bank 10-K Capital Management note.
- **Discovered:** Iteration 2 NU IFRS deep-dive

---

### 15. NU — Noninterest income/expense not comparable under IFRS

- **Affects:** NU (Nu Holdings), and future IFRS-filer banks.
- **Concepts:** `noninterest_income`, `noninterest_expense`
- **Root cause:** US-GAAP banks report aggregate `NoninterestIncome` (all non-interest revenue: fees + trading + commissions + investments) and `NoninterestExpense`. IFRS has no equivalent aggregate. NU exposes `FeeAndCommissionIncome` ($1.9B FY2024) — a sub-component, NOT the total — and `OperatingExpense` ($2.5B) which uses a different scope than the US-GAAP noninterest definition.
- **Workaround:** Extractor returns `not_found` for NU on both concepts. Forcing FeeAndCommissionIncome as noninterest_income would inflate efficiency_ratio (smaller denominator) and produce a false value inconsistent with NU IR reported efficiency (~27.7% Q3'25).
- **Impact:** `efficiency_ratio` calculable for 6 US banks (JPM 51.7%, BAC/GS 63%, WFC/C ~66%, MS 71% FY2024), NOT for NU.
- **Future resolution path:** Parse NU 20-F income statement breakdown directly, or build IFRS-specific efficiency proxy with documented non-comparability.
- **Priority:** Medium. NU efficiency is a thesis driver for the digital bank.
- **Validation:** Empirical verification via companyfacts API May 30, 2026.
- **Discovered:** May 30, 2026 (Banking Phase 2, noninterest batch)



## Summary Table

| # | Sector | Concept | Affects | Severity | Status / Workaround |
|---|--------|---------|---------|----------|---------------------|
| 1 | Tech | research_and_development | AMZN | Medium | Accept not_found |
| 2 | Tech | selling_marketing_expense | NVDA, MU | Low | Captured in G&A |
| 3 | Tech | interest_expense | CRM, NOW | Low | Accept not_found, treat as ~0 |
| 4 | Tech | NDR, ARR | All SaaS | High | Out of scope (MD&A only) |
| 5 | Energy | operating_income exact | XOM (likely others) | Medium | Approximation with bias flag |
| 6 | Energy | All concepts | VIST | High | IFRS support needed |
| 7 | Banking | CECL provision | JPM, BAC | RESOLVED | Phase 2 - verified FY2024, both CECL tags wired May 30 |
| 8 | Banking | IFRS dispatch | NU | RESOLVED | Phase 1 complete - May 21, 2026 |
| 9 | Banking | loans_held_for_investment | WFC, GS | Medium | Accept not_found; LDR not calculable |
| 10 | Banking | provisions, G&A, depreciation (FY24) | NU | High | Parse 20-F notes (pending) |
| 11 | Banking | trading_revenue | GS | High | Accept not_found; parse 10-K trading section |
| 12 | Banking | fee_and_commission_income | All US banks | Low | Use NoninterestIncome as proxy |
| 13 | Utilities | Adjusted EBITDA | VST | High | Out of scope (non-GAAP) |
| 14 | Cross-cutting | CET1, Tier 1 | All banks | Medium | Parse text-blocks or external data |
| 15 | Banking | noninterest income/expense | NU | Medium | Accept not_found; efficiency_ratio not calculable for NU |

---

## Adding a new limitation

When you discover a new limitation:

1. Add an entry to the appropriate sector section above (or create new section)
2. Include all 6 fields (Affects, Concept, Root cause, Workaround, Validation, Discovered)
3. Update the Summary Table
4. If it's truly fixable with code, move it to `TECHNICAL_DEBT.md` instead
5. Commit with message like: `docs: add limitation [SECTOR] [CONCEPT] discovered [DATE]`
