# FearNot Research — Technical Debt

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
