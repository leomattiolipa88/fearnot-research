"""
Regression Test: Tech Sector Coverage
======================================

Validates that extraer_financials_v2() still extracts the expected
coverage for all 8 Tech tickers against the known baseline (May 2026).

Baseline: 18 legacy concepts in CONCEPTOS_ESTANDAR.

Usage:
    python3 -m tests.test_tech_coverage

Exit codes:
    0 = all tickers match expected baseline
    1 = at least one regression detected
"""
import sys
from financials_extractor_v2 import extraer_financials_v2


# ============================================================
# BASELINE ESPERADO (mayo 2026)
# ============================================================
# Cada ticker: cobertura esperada de los 18 conceptos legacy
# (cuántos deberían venir != None, sin contar quality flags)

BASELINE_FY2024 = {
    "META":  {"expected_coverage": 18, "notes": "Big Tech, clean extraction"},
    "GOOGL": {"expected_coverage": 18, "notes": "Big Tech, clean extraction"},
    "AMZN":  {"expected_coverage": 18, "notes": "Custom total_liab calc + confirmed_no_dividend"},
    "MSFT":  {"expected_coverage": 18, "notes": "FY ends June, validated"},
    "NVDA":  {"expected_coverage": 18, "notes": "Semis, FY ends late January"},
    "MU":    {"expected_coverage": 18, "notes": "Semis, FY ends late August"},
    "CRM":   {"expected_coverage": 17, "notes": "SaaS, missing interest_expense (net cash positive)"},
    "NOW":   {"expected_coverage": 17, "notes": "SaaS, missing interest_expense (net cash positive)"},
}

# Lista de los 18 conceptos esperados
LEGACY_CONCEPTS = [
    "revenue", "cost_of_revenue", "operating_income", "interest_expense",
    "depreciation_amortization", "net_income",
    "total_assets", "current_assets", "cash_and_equivalents", "current_liabilities",
    "total_liabilities", "long_term_debt", "stockholders_equity",
    "operating_cash_flow", "capex", "dividends_paid",
    "eps_diluted", "shares_diluted",
]


def contar_cobertura(resultado: dict, conceptos: list) -> tuple:
    """
    Returns (count_extracted, count_not_found, missing_list)
    """
    extracted = 0
    missing = []
    for c in conceptos:
        if resultado.get(c) is not None:
            extracted += 1
        else:
            missing.append(c)
    return extracted, len(missing), missing


def main():
    print("=" * 70)
    print("REGRESSION TEST: Tech Sector Coverage (FY2024, 18 legacy concepts)")
    print("=" * 70)
    print()

    total_tickers = len(BASELINE_FY2024)
    pass_count = 0
    fail_count = 0
    results = []

    for ticker, baseline in BASELINE_FY2024.items():
        expected = baseline["expected_coverage"]
        notes = baseline["notes"]

        print(f"  Testing {ticker}...", end=" ", flush=True)

        try:
            resultado = extraer_financials_v2(ticker, fiscal_year=2024)
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "ticker": ticker,
                "status": "ERROR",
                "actual": 0,
                "expected": expected,
                "missing": [],
                "error": str(e),
            })
            fail_count += 1
            continue

        if resultado.get("error"):
            print(f"ERROR: {resultado['error']}")
            results.append({
                "ticker": ticker,
                "status": "ERROR",
                "actual": 0,
                "expected": expected,
                "missing": [],
                "error": resultado["error"],
            })
            fail_count += 1
            continue

        actual, _, missing = contar_cobertura(resultado, LEGACY_CONCEPTS)

        if actual >= expected:
            status = "PASS"
            pass_count += 1
            print(f"PASS ({actual}/{len(LEGACY_CONCEPTS)})")
        else:
            status = "FAIL"
            fail_count += 1
            print(f"FAIL ({actual}/{len(LEGACY_CONCEPTS)}, expected {expected})")

        results.append({
            "ticker": ticker,
            "status": status,
            "actual": actual,
            "expected": expected,
            "missing": missing,
            "notes": notes,
        })

    # ============ REPORTE DETALLADO ============
    print()
    print("=" * 70)
    print("REPORTE DETALLADO")
    print("=" * 70)
    print(f"{'Ticker':<8} {'Status':<8} {'Coverage':<12} {'Expected':<10} {'Missing'}")
    print("-" * 70)
    for r in results:
        ticker = r["ticker"]
        status = r["status"]
        actual = r["actual"]
        expected = r["expected"]
        missing = ", ".join(r["missing"]) if r["missing"] else "-"
        print(f"{ticker:<8} {status:<8} {actual}/18{'':<8} {expected}{'':<8} {missing}")

    print()
    print("=" * 70)
    if fail_count == 0:
        print(f"RESULT: ALL PASS ({pass_count}/{total_tickers} tickers)")
        print("=" * 70)
        return 0
    else:
        print(f"RESULT: REGRESSION DETECTED ({fail_count}/{total_tickers} tickers failed)")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
