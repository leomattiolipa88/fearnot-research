"""
FearNot - Financial Statements Extractor v2 (SEC EDGAR)

Versión 2 del extractor de financials usando SEC EDGAR API en lugar de yfinance.

Ventajas vs v1 (yfinance):
- Datos auditados directamente de SEC filings (fuente primaria)
- Granularidad mayor (~400-600 facts disponibles vs ~30-40 en yfinance)
- Histórico desde 2009 típicamente
- Datos trimestrales sin límite (yfinance solo da últimos 4)
- Diferencias importantes en algunos campos (Revenue de Exxon: $332B real vs $324B yfinance)

Limitaciones:
- Solo empresas listadas en USA exchanges (NYSE, NASDAQ)
- Nombres de "facts" varían entre empresas (taxonomía GAAP)
- Más complejo de parsear (JSON anidado con miles de períodos)
- Requiere User-Agent identificado

Uso:
    python3 financials_extractor_v2.py XOM
    python3 financials_extractor_v2.py portfolio
"""

import requests
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


# ============================================================
# CONFIG
# ============================================================
USER_AGENT = "FearNot Research boschibasilio@gmail.com"
HEADERS = {"User-Agent": USER_AGENT}

PORTFOLIO_PATH = "my_portfolio.json"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# Cache simple para evitar re-descargar la tabla de tickers en cada call
_ticker_cache = None


# ============================================================
# 1. OBTENER CIK DESDE TICKER
# ============================================================
def obtener_cik(ticker: str) -> Optional[str]:
    """
    Convierte un ticker (ej: 'XOM') al CIK formateado con 10 digitos.
    
    Returns:
        CIK como string de 10 digitos (ej: '0000034088') o None si no encuentra.
    """
    global _ticker_cache
    
    # Cache: descargar la tabla solo una vez por sesion
    if _ticker_cache is None:
        try:
            response = requests.get(SEC_TICKERS_URL, headers=HEADERS, timeout=15)
            response.raise_for_status()
            _ticker_cache = response.json()
        except Exception as e:
            print(f"   ERROR descargando tabla de tickers SEC: {e}")
            return None
    
    # Buscar el ticker (case-insensitive)
    ticker_upper = ticker.upper()
    for entry in _ticker_cache.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            cik_num = entry["cik_str"]
            # SEC requiere CIK con padding a 10 digitos
            return str(cik_num).zfill(10)
    
    return None


# ============================================================
# 2. DESCARGAR FACTS DE SEC EDGAR
# ============================================================
def obtener_facts(cik: str) -> Optional[dict]:
    """
    Descarga todos los "company facts" de una empresa desde SEC EDGAR.
    
    Args:
        cik: CIK formateado a 10 digitos (ej: '0000034088')
    
    Returns:
        Dict con la estructura {entityName, cik, facts: {dei: {...}, us-gaap: {...}}}
        o None si falla.
    """
    url = SEC_FACTS_URL_TEMPLATE.format(cik=cik)
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            print(f"   ERROR: CIK {cik} no tiene facts disponibles en SEC")
            return None
        else:
            print(f"   ERROR SEC EDGAR: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"   ERROR descargando facts: {e}")
        return None


# ============================================================
# 3. EXTRAER UN FACT ESPECIFICO CON DEDUPLICACION
# ============================================================
def extraer_fact_anual(
    facts: dict,
    posibles_nombres: list,
    fiscal_year: int,
    taxonomia: str = "us-gaap",
    unidad: str = "USD"
) -> Optional[float]:
    """
    Extrae el valor de un fact para un fiscal year dado.

    USA fp=FY + fy=fiscal_year (no calendar dates).
    Esto funciona automaticamente para empresas con FY non-calendar:
    - MSFT (fiscal year ends June)
    - NVDA (fiscal year ends late January)
    - CRM (fiscal year ends late January)
    - MU (fiscal year ends late August)

    Maneja dos tipos de facts:
    - Income Statement / Cash Flow: tienen start y end (rango).
      Filtra por fp=FY + fy + duracion ~365 dias.
    - Balance Sheet: solo end (snapshot).
      Filtra por fp=FY + fy.

    Tambien:
    - Prefiere 10-K sobre 10-Q
    - Para duplicados (mismo fy reportado en 10-K original y en
      comparativo del 10-K siguiente), prefiere el que tiene end
      en el fiscal_year correcto.

    Args:
        facts: dict completo de SEC EDGAR
        posibles_nombres: lista de nombres GAAP a probar en orden
        fiscal_year: integer (ej: 2024)
        taxonomia: "us-gaap" por defecto
        unidad: "USD" tipicamente, "USD/shares" para EPS, "shares" para shares

    Returns:
        Valor numerico (float) o None si no encuentra.
    """
    from datetime import date

    if not facts or "facts" not in facts:
        return None

    taxonomia_facts = facts["facts"].get(taxonomia, {})

    for nombre in posibles_nombres:
        if nombre not in taxonomia_facts:
            continue
        fact = taxonomia_facts[nombre]
        if unidad not in fact.get("units", {}):
            continue
        records = fact["units"][unidad]

        # Detectar tipo: IS/CF (tiene "start") vs Balance Sheet (solo "end")
        is_flow = bool(records) and "start" in records[0]

        if is_flow:
            # IS/CF: filtrar por fp=FY + fy + duracion ~365 dias
            matching = []
            for r in records:
                if r.get("fp") != "FY" or r.get("fy") != fiscal_year:
                    continue
                try:
                    s = date.fromisoformat(r["start"])
                    e = date.fromisoformat(r["end"])
                    duracion = (e - s).days
                    if 350 <= duracion <= 380:
                        matching.append(r)
                except (ValueError, KeyError):
                    continue
        else:
            # Balance Sheet: filtrar por fp=FY + fy
            matching = [
                r for r in records
                if r.get("fp") == "FY" and r.get("fy") == fiscal_year
            ]

        if not matching:
            continue

        # Preferir 10-K sobre 10-Q
        ten_k = [r for r in matching if r.get("form") == "10-K"]
        candidates = ten_k if ten_k else matching

        # Deduplicacion: mismo fy puede aparecer en multiples 10-Ks
        # (el original + comparativo en filings posteriores).
        # Preferir el que tiene end en el fiscal_year buscado.
        if is_flow:
            clean = [c for c in candidates if c.get("end", "").startswith(str(fiscal_year))]
            if clean:
                candidates = clean
        else:
            # Balance Sheet: end debe estar en el fiscal_year o el siguiente
            # (porque BS de FY2024 termina en 2024 si calendar, o 2024-06 si MSFT)
            clean = [
                c for c in candidates
                if c.get("end", "").startswith(str(fiscal_year))
                or c.get("end", "").startswith(str(fiscal_year + 1))
            ]
            if clean:
                candidates = clean

        # Tomar el filing mas reciente
        candidates.sort(key=lambda r: r.get("filed", ""), reverse=True)
        return float(candidates[0]["val"])

    return None



# ============================================================
# 4. TEST: probar las funciones con XOM
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("TEST de funciones SEC EDGAR")
    print("=" * 60)
    
    # Test 1: obtener CIK
    ticker = "XOM"
    print(f"\n[1] Obteniendo CIK para {ticker}...")
    cik = obtener_cik(ticker)
    print(f"    CIK: {cik}")
    
    if not cik:
        print("    Falla obteniendo CIK, abortando.")
        sys.exit(1)
    
    # Test 2: obtener facts
    print(f"\n[2] Descargando facts para CIK {cik}...")
    facts = obtener_facts(cik)
    if facts:
        print(f"    Entity: {facts.get('entityName')}")
        gaap_count = len(facts['facts'].get('us-gaap', {}))
        print(f"    US-GAAP facts disponibles: {gaap_count}")
    else:
        print("    Falla descargando facts, abortando.")
        sys.exit(1)
    
    # Test 3: extraer Revenue 2025
    print(f"\n[3] Extrayendo Revenue 2025...")
    revenue_2025 = extraer_fact_anual(
        facts, 
        ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        fiscal_year=2025
    )
    print(f"    Revenue 2025: ${revenue_2025/1e9:.1f}B" if revenue_2025 else "    NO ENCONTRADO")
    
    # Test 4: extraer Revenue 2024
    print(f"\n[4] Extrayendo Revenue 2024...")
    revenue_2024 = extraer_fact_anual(
        facts, 
        ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        fiscal_year=2024
    )
    print(f"    Revenue 2024: ${revenue_2024/1e9:.1f}B" if revenue_2024 else "    NO ENCONTRADO")
    
    # Test 5: extraer Net Income 2025
    print(f"\n[5] Extrayendo Net Income 2025...")
    ni_2025 = extraer_fact_anual(
        facts,
        ["NetIncomeLoss", "ProfitLoss"],
        fiscal_year=2025
    )
    print(f"    Net Income 2025: ${ni_2025/1e9:.1f}B" if ni_2025 else "    NO ENCONTRADO")
    
    print("\n" + "=" * 60)
    print("Si todo funciona, el match esperado con el 10-K de XOM 2025 es:")
    print("  Revenue 2025: $332.2B")
    print("  Net Income 2025: $28.8B (attributable to XOM) o $29.8B (consolidado)")
    print("=" * 60)


# ============================================================
# CONCEPTOS ESTANDAR (los 18 que extraemos siempre)
# ============================================================
CONCEPTOS_ESTANDAR = [
    # Income Statement
    "revenue",
    "cost_of_revenue",
    "operating_income",
    "interest_expense",
    "depreciation_amortization",
    "net_income",
    # Banking - income statement (added 2026-05-30, Phase 2 nucleo)
    "net_interest_income",
    "provision_for_credit_losses",
    "noninterest_income",
    "noninterest_expense",
    # Income Statement - Tech/SaaS relevant (added May 2026)
    "research_and_development",
    "stock_based_compensation",
    "selling_marketing_expense",
    "general_administrative_expense",
    # Balance Sheet
    "total_assets",
    "current_assets",
    "cash_and_equivalents",
    "current_liabilities",
    "total_liabilities",
    "long_term_debt",
    "stockholders_equity",
    # Balance Sheet - additional (added May 2026)
    "deferred_revenue",
    "goodwill",
    # Banking - balance sheet (added 2026-05-30, Phase 2 nucleo)
    # Solo se pueblan para tickers bank; no-bancarias dan not_found (esperado).
    "deposits",
    "loans_held_for_investment",
    # Cash Flow
    "operating_cash_flow",
    "capex",
    "dividends_paid",
    # Per Share
    "eps_diluted",
    "shares_diluted",
]


# ============================================================
# ORQUESTADOR PRINCIPAL
# ============================================================
def extraer_financials_v2(ticker: str, fiscal_year: int) -> dict:
    """
    Extrae financials de un ticker para un fiscal year usando SEC EDGAR.

    Flow:
    1. Detectar sector via router
    2. Descargar facts de SEC
    3. Extraer cada concepto estandar (router decide nombres GAAP)
    4. Aplicar calculos derivados si faltan facts directos
    5. Aplicar aproximaciones sector-specific cuando aplique
    6. Devolver dict plano con valores + quality flags

    Args:
        ticker: ej "XOM", "META"
        fiscal_year: ej 2024, 2025

    Returns:
        dict con 18 conceptos + sus quality flags + metadata.
        Si el ticker o facts no existen, devuelve dict con error.
    """
    # Imports tardios para evitar problemas de orden
    from sector_router import detect_sector, get_names_for_concept
    from gaap_taxonomy import get_unit_for_concept
    from ifrs_taxonomy import (
        is_ifrs_filer,
        get_ifrs_names_for_concept,
        get_ifrs_unit_for_concept,
    )
    from calculated_metrics import (
        calcular_shares_diluted,
        calcular_operating_income_aproximado,
    )

    resultado = {
        "ticker": ticker.upper(),
        "fiscal_year": fiscal_year,
    }

    # ===== Step 1: Setup =====
    cik = obtener_cik(ticker)
    if cik is None:
        resultado["error"] = f"CIK no encontrado para ticker {ticker}"
        return resultado

    facts = obtener_facts(cik)
    if facts is None:
        resultado["error"] = f"No se pudieron descargar facts para CIK {cik}"
        return resultado

    resultado["entity_name"] = facts.get("entityName", "Unknown")
    resultado["cik"] = cik
    resultado["sector"] = detect_sector(ticker) or "unclassified"

    # Detectar taxonomia del filer (us-gaap default, ifrs-full para 20-F filers)
    taxonomia = "ifrs-full" if is_ifrs_filer(ticker) else "us-gaap"
    resultado["taxonomia"] = taxonomia

    # ===== Step 2: Extraer conceptos estandar =====
    for concepto in CONCEPTOS_ESTANDAR:
        # Dispatch nombres GAAP segun taxonomy
        if taxonomia == "ifrs-full":
            names = get_ifrs_names_for_concept(concepto)
            unit = get_ifrs_unit_for_concept(concepto)
        else:
            names = get_names_for_concept(concepto, ticker)
            unit = get_unit_for_concept(concepto)

        valor = extraer_fact_anual(facts, names, fiscal_year, taxonomia=taxonomia, unidad=unit)

        if valor is not None:
            resultado[concepto] = valor
            resultado[f"{concepto}_quality"] = "direct"
        else:
            resultado[concepto] = None
            resultado[f"{concepto}_quality"] = "not_found"

    # ===== Step 3: Calculos derivados (fallbacks) =====

    # 3a: Shares diluted - si falta, calcular desde NI/EPS
    if resultado["shares_diluted"] is None:
        result = calcular_shares_diluted(
            net_income=resultado.get("net_income"),
            eps_diluted=resultado.get("eps_diluted"),
        )
        if result["value"] is not None:
            resultado["shares_diluted"] = result["value"]
            resultado["shares_diluted_quality"] = result["quality"]

    # 3b: Total liabilities - si falta, calcular desde TotalAssets - Equity
    if resultado["total_liabilities"] is None:
        from calculated_metrics import calcular_total_liabilities
        result = calcular_total_liabilities(
            total_assets=resultado.get("total_assets"),
            stockholders_equity=resultado.get("stockholders_equity"),
        )
        if result["value"] is not None:
            resultado["total_liabilities"] = result["value"]
            resultado["total_liabilities_quality"] = result["quality"]

    # 3c: Dividends paid - si falta pero el resto de cash flow existe,
    #     asumir que la empresa no paga dividendos (= 0)
    if (resultado["dividends_paid"] is None
            and resultado.get("operating_cash_flow") is not None):
        # Empresa tiene cash flow data pero no encontramos dividends.
        # Conclusion: no paga dividendos.
        resultado["dividends_paid"] = 0
        resultado["dividends_paid_quality"] = "confirmed_no_dividend"

    # ===== Step 4: Aproximaciones sector-specific =====

    # 4a: Operating Income para Energy (sector que no expone componentes)
    if (resultado["operating_income"] is None
            and resultado["sector"] == "energy"):

        # Buscar IncomeBeforeTax con nombres XOM/integrated
        income_before_tax = extraer_fact_anual(
            facts,
            [
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",  # XOM
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",  # CVX
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
            ],
            fiscal_year
        )

        result = calcular_operating_income_aproximado(
            income_before_tax=income_before_tax,
            interest_expense=resultado.get("interest_expense"),
        )

        if result["value"] is not None:
            resultado["operating_income"] = result["value"]
            resultado["operating_income_quality"] = result["quality"]
            if result.get("bias_warning"):
                resultado["operating_income_warning"] = result["bias_warning"]

    return resultado


# ============================================================
# TEST DEL ORQUESTADOR
# ============================================================
def _print_resultado(resultado: dict):
    """Helper para imprimir resultado bonito."""
    print(f"\n{'='*70}")
    print(f"  {resultado.get('ticker')} | {resultado.get('entity_name')}")
    print(f"  FY {resultado.get('fiscal_year')} | Sector: {resultado.get('sector')}")
    print(f"{'='*70}")

    if "error" in resultado:
        print(f"  ERROR: {resultado['error']}")
        return

    for concepto in CONCEPTOS_ESTANDAR:
        valor = resultado.get(concepto)
        quality = resultado.get(f"{concepto}_quality", "?")

        if valor is None:
            print(f"  {concepto:30s} {'N/A':>15s}  [{quality}]")
        elif "shares" in concepto and quality != "direct":
            print(f"  {concepto:30s} {valor/1e9:>12.2f}B sh  [{quality}]")
        elif concepto == "eps_diluted":
            print(f"  {concepto:30s} {'$' + format(valor, '.2f'):>15s}  [{quality}]")
        elif "shares" in concepto:
            print(f"  {concepto:30s} {valor/1e9:>12.2f}B sh  [{quality}]")
        else:
            display = f"${valor/1e9:.2f}B"
            print(f"  {concepto:30s} {display:>15s}  [{quality}]")


if __name__ == "__main__":
    import sys

    # Test con XOM (energy, tiene approximation) y META (tech, todo direct)
    for ticker in ["XOM", "META"]:
        resultado = extraer_financials_v2(ticker, 2024)
        _print_resultado(resultado)

    print()


# ============================================================
# EXTRACCION TRIMESTRAL (aditivo - no toca el camino anual)
# ============================================================

def extraer_fact_trimestral(
    facts: dict,
    posibles_nombres: list,
    frame: str,
    taxonomia: str = "us-gaap",
    unidad: str = "USD"
) -> Optional[float]:
    """
    Extrae el valor de un fact para un trimestre dado, identificado por su 'frame'.
    Flujos: "CY2024Q2" (periodo discreto). Stocks: "CY2024Q2I" (I = Instant).
    Los YTD no tienen frame, asi que filtrar por frame da el trimestre puro.
    Generica: cualquier sector. Aditiva: no toca extraer_fact_anual.
    """
    if not facts or "facts" not in facts:
        return None
    taxonomia_facts = facts["facts"].get(taxonomia, {})
    for nombre in posibles_nombres:
        if nombre not in taxonomia_facts:
            continue
        fact = taxonomia_facts[nombre]
        if unidad not in fact.get("units", {}):
            continue
        records = fact["units"][unidad]
        matching = [r for r in records if r.get("frame") == frame]
        if not matching:
            continue
        matching.sort(key=lambda r: r.get("filed", ""), reverse=True)
        return float(matching[0]["val"])
    return None


def extraer_fact_trimestral_auto(
    facts: dict,
    posibles_nombres: list,
    anio: int,
    quarter: int,
    taxonomia: str = "us-gaap",
    unidad: str = "USD"
) -> tuple:
    """
    Prueba ambos frames (flujo "CYxxxxQn" y stock "CYxxxxQnI"), usa el que traiga
    dato. No necesitas saber de antemano si el concepto es stock o flujo.
    Returns: (valor, es_stock) o (None, None).
    """
    frame_flujo = f"CY{anio}Q{quarter}"
    frame_stock = f"CY{anio}Q{quarter}I"
    val = extraer_fact_trimestral(facts, posibles_nombres, frame_flujo, taxonomia, unidad)
    if val is not None:
        return val, False
    val = extraer_fact_trimestral(facts, posibles_nombres, frame_stock, taxonomia, unidad)
    if val is not None:
        return val, True
    return None, None
