"""
Banking Sector — Sector-Specific Metrics & Validation
======================================================

Universo: Bancos comerciales US (universal + investment) + 1 digital EM.

Tres sub-tipos con dinamicas distintas:
- UNIVERSAL BANKS (JPM, BAC, WFC, C): banca comercial diversificada.
  NIM-driven, deposits masivos, cartera de prestamos grande.
- INVESTMENT BANKS (GS, MS): ingresos por trading/fees, no por spread.
  NII chico, loans menores. NIM/loan-to-deposit menos relevantes.
- DIGITAL EM (NU): banco digital brasileno (IFRS filer). NIM altisimo
  (Brasil + credito unsecured), escala chica vs US.

Decisiones arquitecturales:
- NO hay tags XBRL aca: viven en gaap_taxonomy.py (sector_overrides "bank")
  e ifrs_taxonomy.py (NU). Ver TECHNICAL_DEBT.md #4.
- Este modulo DESCRIBE metricas (formula-texto + rangos + calculable flag).
  El CALCULO real vive en calculated_metrics.py (su rol oficial).
- Patron identico a sector_mappings/tech.py para consistencia.

Conceptos del nucleo verificados empiricamente contra SEC EDGAR FY2024
(2026-05-30): net_interest_income, deposits, loans_held_for_investment,
provision_for_credit_losses. 24 valores reales, not_found documentados.

Fuente: SECTOR_RESEARCH_OVERVIEW.md Sector 2 + LIMITATIONS.md #7,#9,#10,#11,#12.
"""


# ============================================================
# UNIVERSO DE TICKERS — sub-clasificacion interna
# ============================================================

UNIVERSAL_BANKS = {
    "JPM",   # JPMorgan Chase
    "BAC",   # Bank of America
    "WFC",   # Wells Fargo
    "C",     # Citigroup
}

INVESTMENT_BANKS = {
    "GS",    # Goldman Sachs
    "MS",    # Morgan Stanley
}

DIGITAL_EM_BANKS = {
    "NU",    # Nu Holdings (Brazilian fintech, IFRS filer)
}

# Union completa: todos los tickers del universo bancario
BANKING_TICKERS = UNIVERSAL_BANKS | INVESTMENT_BANKS | DIGITAL_EM_BANKS


# ============================================================
# BANKING-SPECIFIC CONCEPTS (vacio — los tags viven en taxonomy)
# ============================================================
# Los 4 conceptos del nucleo (NII, deposits, loans, provisions) NO viven
# aca: estan en gaap_taxonomy.py:sector_overrides["bank"] (US-GAAP) y en
# ifrs_taxonomy.py (NU). Ver TECHNICAL_DEBT.md #4 (single source of truth).
# Este dict queda vacio a proposito, igual que TECH_SPECIFIC_CONCEPTS.

BANKING_SPECIFIC_CONCEPTS = {}


# ============================================================
# METRICAS BANKING-SPECIFIC (formula-texto + rangos + calculable)
# ============================================================
# DESCRIPTIVAS. El calculo real esta en calculated_metrics.py.
# calculable_from_xbrl indica si HOY tenemos los datos para computarla.

BANKING_SPECIFIC_METRICS = {
    "loan_to_deposit": {
        "description": "Loan-to-Deposit Ratio = prestamos / depositos. Mide cuanto del funding se presta.",
        "formula": "loans_held_for_investment / deposits",
        "applies_to": ["JPM", "BAC", "WFC", "C", "NU"],  # los que tienen ambos facts
        "healthy_range": {
            "universal_banks": (0.60, 0.90),  # comercial tipico
            "digital_em": (0.20, 0.70),       # NU mas bajo (mucho deposito, credito unsecured selectivo)
        },
        "notes": "WFC/GS no calculable (loans not_found, LIMITATIONS #9). GS estructuralmente irrelevante (i-bank).",
        "calculable_from_xbrl": True,
    },
    "cost_of_risk": {
        "description": "Cost of Risk = provisiones / prestamos. Proxy del riesgo crediticio del ciclo.",
        "formula": "provision_for_credit_losses / loans_held_for_investment",
        "applies_to": ["JPM", "BAC", "C", "MS"],  # tienen provisions Y loans
        "healthy_range": {
            "universal_banks": (0.003, 0.015),  # 0.3%-1.5% para banca prime US
        },
        "notes": "Provisions es forward-looking (CECL), NO charge-offs realizados (LIMITATIONS pitfall #1). WFC: provisions si pero loans no.",
        "calculable_from_xbrl": True,
    },
    "nim": {
        "description": "Net Interest Margin = NII / avg interest-earning assets. Rentabilidad del spread.",
        "formula": "net_interest_income / avg_interest_earning_assets",
        "applies_to": ["JPM", "BAC", "WFC", "C", "NU"],
        "healthy_range": {
            "universal_banks": (0.025, 0.035),  # 2.5%-3.5% comercial US
            "digital_em": (0.08, 0.20),         # NU 8-20% (Brasil + unsecured)
        },
        "notes": "PENDIENTE: requiere avg interest-earning assets, que aun no extraemos. Agregar concepto para habilitar.",
        "calculable_from_xbrl": False,
    },
    "efficiency_ratio": {
        "description": "Efficiency Ratio = gasto no-financiero / (NII + ingreso no-financiero). Menor = mejor.",
        "formula": "noninterest_expense / (net_interest_income + noninterest_income)",
        "applies_to": ["JPM", "BAC", "WFC", "C", "GS", "MS", "NU"],
        "healthy_range": {
            "universal_banks": (0.55, 0.65),    # JPM ~55, BAC ~65
            "digital_em": (0.25, 0.45),         # NU Q3'25 ~27.7%
        },
        "notes": "PENDIENTE: requiere noninterest_income y noninterest_expense, aun no extraidos (parte del 2do batch de conceptos).",
        "calculable_from_xbrl": False,
    },
    "rotce": {
        "description": "Return on Tangible Common Equity = net income / avg tangible common equity. Reemplaza ROIC en banca.",
        "formula": "net_income / avg_tangible_common_equity",
        "applies_to": ["JPM", "BAC", "WFC", "C", "GS", "MS"],
        "healthy_range": {
            "universal_banks": (0.12, 0.22),    # JPM 2023 ROTCE 21%
        },
        "notes": "PENDIENTE: requiere tangible common equity (equity - goodwill - intangibles). Goodwill ya se extrae; falta intangibles.",
        "calculable_from_xbrl": False,
    },
}


# ============================================================
# VALIDATION RULES — rangos esperables por sub-tipo
# ============================================================

BANKING_VALIDATION_RULES = {
    "nim": {
        "universal_banks": {"min": 0.015, "max": 0.05, "notes": "US commercial 2.5-3.5%. <1.5% o >5% = flag."},
        "digital_em": {"min": 0.08, "max": 0.20, "notes": "NU range 8-20% por Brasil + unsecured."},
    },
    "efficiency_ratio": {
        "all": {"min": 0.40, "max": 0.85, "notes": "Fuera de 40-85% = error o one-off (ej: FDIC special assessment)."},
    },
    "cost_of_risk": {
        "universal_banks": {"min": 0.0, "max": 0.03, "notes": ">3% sostenido = deterioro crediticio severo."},
    },
    "loan_to_deposit": {
        "universal_banks": {"min": 0.40, "max": 1.10, "notes": ">110% = dependencia de wholesale funding."},
    },
}


# ============================================================
# KNOWN LIMITATIONS (cross-ref LIMITATIONS.md)
# ============================================================

KNOWN_LIMITATIONS = {
    "wfc_gs_loans_missing": {
        "affects": ["WFC", "GS"],
        "issue": "No reportan cartera total de prestamos como fact XBRL discreto.",
        "workaround": "Extractor devuelve not_found. loan_to_deposit no calculable para estos. GS estructuralmente irrelevante (i-bank).",
        "documented_in": "LIMITATIONS.md #9",
    },
    "nu_provisions_nii_fy24": {
        "affects": ["NU"],
        "issue": "NII sin tag canonico (filer quirk); provisions sin valor FY2024 (solo FY2023).",
        "workaround": "NII not_found; provisions FY24 requiere parse de notes del 20-F. cost_of_risk NU no calculable hasta entonces.",
        "documented_in": "LIMITATIONS.md #10 + ifrs_taxonomy.py notes",
    },
    "gs_trading_revenue": {
        "affects": ["GS"],
        "issue": "Trading revenue (la linea mas grande de GS) no esta como fact XBRL discreto.",
        "workaround": "not_found. Para GS, parsear seccion 'Trading Results' del 10-K.",
        "documented_in": "LIMITATIONS.md #11",
    },
    "fee_income_fragmented": {
        "affects": ["JPM", "BAC", "WFC", "C", "GS", "MS"],
        "issue": "Fee/commission income fragmentado en muchos tags, no agregado.",
        "workaround": "Usar NoninterestIncome como proxy de ingreso no-financiero.",
        "documented_in": "LIMITATIONS.md #12",
    },
}


# ============================================================
# HELPERS
# ============================================================

def is_banking_ticker(ticker: str) -> bool:
    """Returns True if ticker belongs to Banking sector."""
    return ticker.upper() in BANKING_TICKERS


def get_banking_subtype(ticker: str) -> str:
    """
    Returns the Banking sub-type for a ticker.

    Returns:
        "universal_banks", "investment_banks", or "digital_em"
        None if ticker not in Banking universe.
    """
    ticker_upper = ticker.upper()
    if ticker_upper in UNIVERSAL_BANKS:
        return "universal_banks"
    if ticker_upper in INVESTMENT_BANKS:
        return "investment_banks"
    if ticker_upper in DIGITAL_EM_BANKS:
        return "digital_em"
    return None


def get_calculable_metrics(ticker: str) -> list:
    """
    Returns the list of metric names that are calculable TODAY for this ticker
    (calculable_from_xbrl=True AND ticker in applies_to).

    Util para que el banking_agent sepa que puede computar de verdad,
    sin pedir metricas que devolverian None.
    """
    ticker_upper = ticker.upper()
    if not is_banking_ticker(ticker_upper):
        return []
    out = []
    for nombre, meta in BANKING_SPECIFIC_METRICS.items():
        if not meta.get("calculable_from_xbrl"):
            continue
        aplica = meta.get("applies_to", [])
        if aplica == "ALL_BANKING" or ticker_upper in aplica:
            out.append(nombre)
    return out


def get_banking_gaap_names(concept: str) -> list:
    """
    Banking NO define tags propios aca (viven en gaap_taxonomy.py).
    Existe por consistencia de interfaz con el router. Siempre [].
    """
    if concept not in BANKING_SPECIFIC_CONCEPTS:
        return []
    return BANKING_SPECIFIC_CONCEPTS[concept].get("names", [])


if __name__ == "__main__":
    print("Banking sector module loaded.")
    print(f"  Total banking tickers: {len(BANKING_TICKERS)}")
    print(f"    Universal:   {sorted(UNIVERSAL_BANKS)}")
    print(f"    Investment:  {sorted(INVESTMENT_BANKS)}")
    print(f"    Digital EM:  {sorted(DIGITAL_EM_BANKS)}")
    print(f"  Metrics: {list(BANKING_SPECIFIC_METRICS.keys())}")
    calc = [m for m, meta in BANKING_SPECIFIC_METRICS.items() if meta.get('calculable_from_xbrl')]
    pend = [m for m, meta in BANKING_SPECIFIC_METRICS.items() if not meta.get('calculable_from_xbrl')]
    print(f"    Calculables hoy: {calc}")
    print(f"    Pendientes:      {pend}")
    print()
    print("Quick test helpers:")
    for t in ["JPM", "GS", "NU", "XOM"]:
        print(f"  {t:5s}: is_bank={is_banking_ticker(t)!s:5s} "
              f"subtype={get_banking_subtype(t)!s:18s} "
              f"calculable={get_calculable_metrics(t)}")
