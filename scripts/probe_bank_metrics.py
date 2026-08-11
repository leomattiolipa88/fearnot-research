#!/usr/bin/env python3
"""
scripts/probe_bank_metrics.py — Probe de cobertura SEC EDGAR (fase 1).

Objetivo: para los 7 tickers del universo bancario, reportar cuantos periodos
anuales (fp=FY) y trimestrales (frame=CY####Q#) hay en companyfacts SEC para
cada concepto us-gaap candidato del rediseno de metricas bancarias nativas.

No toca DB, collectors ni agentes. Solo lectura de SEC. Reusa el fetch y los
headers del extractor (financials_extractor_v2).

Uso:
    python3 scripts/probe_bank_metrics.py

Output:
    - Dos tablas (anual, trimestral): filas=conceptos, columnas=tickers,
      celda = cantidad de periodos disponibles (0 = '—', IFRS filer = 'IFRS').
    - Columna resumen por concepto: 'cobertura >=5/7: SI/no'.
    - Bloque final con la variante us-gaap que dio hit por (concepto, ticker),
      util para saber que tag adoptar cuando se promuevan a taxonomy.
"""

import sys
from pathlib import Path

# Permitir imports desde repo root (script vive en scripts/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from financials_extractor_v2 import obtener_cik, obtener_facts
from sector_mappings.banking import BANKING_TICKERS
from ifrs_taxonomy import is_ifrs_filer


# ============================================================
# Universo de conceptos a probar
# ============================================================
# Cada entrada: (nombre_corto, [variantes us-gaap en orden de preferencia], tag)
# tag = "nuevo" | "ya-colectado" — para el reporte.
#
# NOTA sobre IFRS: NU es 20-F IFRS filer. El probe es us-gaap only, asi que
# para NU todas estas variantes daran cero. Se marca IFRS en la celda para
# distinguir "estructural" de "ausente".

PROBE_CONCEPTS = [
    # ---------- 1. ACL (allowance for credit losses) ----------
    ("acl", [
        "FinancingReceivableAllowanceForCreditLosses",
        "FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest",
        "AllowanceForLoanAndLeaseLossesFinancingReceivable",
        "LoansAndLeasesReceivableAllowance",
    ], "nuevo"),

    # ---------- 2. Charge-offs ----------
    ("charge_offs", [
        "FinancingReceivableAllowanceForCreditLossesWriteOffs",
        "FinancingReceivableAllowanceForCreditLossWriteoff",
        "AllowanceForLoanAndLeaseLossesWriteOffs",
    ], "nuevo"),

    # ---------- 3. Nonaccrual / NPL ----------
    ("nonaccrual", [
        "FinancingReceivableRecordedInvestmentNonaccrualStatus",
        "FinancingReceivableNonaccrualNoAllowance",
        "FinancingReceivableNonaccrualWithAllowance",
        "ImpairedFinancingReceivableWithRelatedAllowanceRecordedInvestment",
        "ImpairedFinancingReceivableRecordedInvestment",
    ], "nuevo"),

    # ---------- 4. Capital regulatorio (CET1) ----------
    ("cet1_ratio", [
        "CommonEquityTier1CapitalRatio",
        "CapitalToRiskWeightedAssetsCommonEquityTierOne",
        "TierOneRiskBasedCapitalRatio",
        "CapitalToRiskWeightedAssets",
    ], "nuevo"),

    # ---------- 5. Interest expense on deposits ----------
    ("interest_expense_deposits", [
        "InterestExpenseDeposits",
        "InterestExpenseDepositsInsuredDomestic",
        "InterestExpenseTimeDeposits",
        "InterestExpenseSavingsDeposits",
    ], "nuevo"),

    # ---------- 6. Componentes de ROTCE ----------
    # (goodwill/net_income/stockholders_equity YA se recolectan hoy en el
    # camino anual — CONCEPTOS_ESTANDAR de financials_extractor_v2.py.
    # Los medimos igual para tener el mapa completo de tags/periodos.)
    ("goodwill", [
        "Goodwill",
    ], "ya-colectado"),

    ("intangibles_ex_goodwill", [
        "IntangibleAssetsNetExcludingGoodwill",
        "FiniteLivedIntangibleAssetsNet",
    ], "nuevo"),

    ("net_income", [
        "NetIncomeLoss",
        "ProfitLoss",
    ], "ya-colectado"),

    ("stockholders_equity", [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ], "ya-colectado"),
]

COBERTURA_MINIMA = 5


# ============================================================
# Coverage counting
# ============================================================

def contar_periodos(facts: dict, variantes: list) -> tuple:
    """Devuelve (n_fy, n_q, nombre_matcheado) para la PRIMERA variante que
    tenga registros en cualquier unidad. Contadores:
      - n_fy:  cardinalidad de {fy : record.fp == 'FY' y fy is not None}
      - n_q:   cardinalidad de {frame : frame.startswith('CY') and 'Q' in frame}
                (matchea 'CY2024Q3' — flujo — y 'CY2024Q3I' — stock)
    us-gaap unicamente. Si ninguna variante matchea, (0, 0, None)."""
    if not facts or "facts" not in facts:
        return (0, 0, None)
    gaap = facts["facts"].get("us-gaap", {})
    for nombre in variantes:
        if nombre not in gaap:
            continue
        fact = gaap[nombre]
        fy_years = set()
        q_frames = set()
        for _unidad, records in fact.get("units", {}).items():
            for r in records:
                if r.get("fp") == "FY" and r.get("fy") is not None:
                    fy_years.add(r["fy"])
                frame = r.get("frame", "")
                if frame.startswith("CY") and "Q" in frame:
                    q_frames.add(frame)
        if fy_years or q_frames:
            return (len(fy_years), len(q_frames), nombre)
    return (0, 0, None)


# ============================================================
# Render helpers
# ============================================================

_ANCHO_CONCEPT = max(len(c) for c, _, _ in PROBE_CONCEPTS) + 2
_ANCHO_COL = 6


def _celda(valor: int, nombre: str) -> str:
    if nombre == "IFRS-filer":
        return "IFRS"
    if valor == 0:
        return "—"
    return str(valor)


def _imprimir_tabla(titulo: str, tickers: list, resultados: dict, kind: str):
    """kind = 'fy' (anual) o 'q' (trimestral). Cobertura por fila = cuantos
    tickers tienen >0 en esa columna (IFRS y '—' no cuentan)."""
    print("=" * 80)
    print(titulo)
    print("=" * 80)
    header = "concepto".ljust(_ANCHO_CONCEPT) + "".join(
        t.rjust(_ANCHO_COL) for t in tickers) + "  cob>=5/7"
    print(header)
    print("-" * len(header))

    for (concept, _variantes, tag) in PROBE_CONCEPTS:
        fila = concept.ljust(_ANCHO_CONCEPT)
        cobertura = 0
        for t in tickers:
            fy, q, nombre = resultados[concept][t]
            valor = fy if kind == "fy" else q
            celda = _celda(valor, nombre)
            if celda not in ("—", "IFRS"):
                cobertura += 1
            fila += celda.rjust(_ANCHO_COL)
        pass_min = "SI" if cobertura >= COBERTURA_MINIMA else "no"
        fila += f"  {cobertura}/7 -> {pass_min}"
        if tag == "ya-colectado":
            fila += "  (YA)"
        print(fila)
    print()


def _imprimir_variantes(tickers: list, resultados: dict):
    """Que tag us-gaap gano en cada (concepto, ticker). Fuente para taxonomy."""
    print("=" * 80)
    print("VARIANTE MATCHEADA (primer nombre us-gaap con hit)")
    print("=" * 80)
    for (concept, _variantes, _tag) in PROBE_CONCEPTS:
        print(f"\n{concept}:")
        for t in tickers:
            fy, q, nombre = resultados[concept][t]
            if nombre is None:
                print(f"  {t:5s} —")
            elif nombre == "IFRS-filer":
                print(f"  {t:5s} IFRS filer (probe us-gaap no aplica)")
            else:
                print(f"  {t:5s} {nombre}  (fy={fy}, q={q})")


# ============================================================
# Main
# ============================================================

def main():
    tickers = sorted(BANKING_TICKERS)
    print(f"Probe cobertura SEC EDGAR — {len(tickers)} bancos: {', '.join(tickers)}")
    print()

    # 1) Descargar facts una vez por ticker (2-30 MB por banco).
    facts_por_ticker = {}
    for ticker in tickers:
        cik = obtener_cik(ticker)
        if cik is None:
            print(f"  {ticker}: CIK no encontrado — salteado")
            continue
        facts = obtener_facts(cik)
        if facts is None:
            print(f"  {ticker}: facts no disponibles — salteado")
            continue
        facts_por_ticker[ticker] = facts
        taxonomia = "ifrs-full" if is_ifrs_filer(ticker) else "us-gaap"
        print(f"  {ticker}: {facts.get('entityName', '?')} ({taxonomia})")
    print()

    # 2) Para cada concepto, contar cobertura en cada ticker.
    resultados = {}  # concept -> ticker -> (n_fy, n_q, nombre|None|"IFRS-filer")
    for (concept, variantes, _tag) in PROBE_CONCEPTS:
        resultados[concept] = {}
        for ticker in tickers:
            if ticker not in facts_por_ticker:
                resultados[concept][ticker] = (0, 0, None)
                continue
            if is_ifrs_filer(ticker):
                # us-gaap probe no aplica a IFRS filers.
                resultados[concept][ticker] = (0, 0, "IFRS-filer")
                continue
            resultados[concept][ticker] = contar_periodos(
                facts_por_ticker[ticker], variantes
            )

    # 3) Tablas.
    _imprimir_tabla(
        "COBERTURA ANUAL (# fiscal years con fp=FY)",
        tickers, resultados, kind="fy",
    )
    _imprimir_tabla(
        "COBERTURA TRIMESTRAL (# frames CY####Q# con dato)",
        tickers, resultados, kind="q",
    )
    _imprimir_variantes(tickers, resultados)


if __name__ == "__main__":
    main()
