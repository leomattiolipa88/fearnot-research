"""
Technology Sector — Sector-Specific Metrics & Validation
=========================================================

Universo: Big Tech / Hyperscalers, SaaS pure-play, Semiconductors.

Tres sub-grupos con dinamicas distintas:
- BIG TECH (META, GOOGL, AMZN, MSFT): Hyperscalers integrados.
  AI capex regime change (10% -> 25-30% revenue) desde 2024.
- SaaS (CRM, NOW): Subscription model, GAAP vs Non-GAAP gap grande
  por SBC. Rule of 40 como North Star. NDR/ARR no en XBRL (MD&A only).
- SEMIS (NVDA, MU): Ciclicos extremos. NVDA es excepcion AI 2023-2026.
  MU clasico DRAM cycle. Book-to-bill, inventory days criticos.

Decisiones arquitecturales:
- NO hay TECH_GAAP_OVERRIDES: los tags universales (revenue, OpInc,
  R&D, SBC) viven en gaap_taxonomy.py. Tech no requiere overrides.
- Solo METRICAS calculadas + VALIDATION RULES viven aqui.
- Custom extensions (ej: amzn:FulfillmentExpense) se agregaran si
  la validacion empirica muestra que mejoran cobertura.

Fuente: SECTOR_RESEARCH_OVERVIEW.md, validacion mayo 2026 con
8 tickers (META/GOOGL/AMZN/MSFT/NVDA/MU 18/18, CRM/NOW 17/18).
"""


# ============================================================
# UNIVERSO DE TICKERS — sub-clasificacion interna
# ============================================================

BIG_TECH_TICKERS = {
    "META",   # Meta Platforms - Internet/advertising
    "GOOGL",  # Alphabet - Internet/search/cloud
    "AMZN",   # Amazon - E-commerce + AWS
    "MSFT",   # Microsoft - Software/cloud/AI (FY ends June)
}

SAAS_TICKERS = {
    "CRM",    # Salesforce - CRM SaaS (FY ends late January)
    "NOW",    # ServiceNow - Workflow SaaS
}

SEMIS_TICKERS = {
    "NVDA",   # NVIDIA - AI accelerators (FY ends late January)
    "MU",     # Micron - DRAM/NAND memory (FY ends late August)
}

# Union completa: todos los tickers Tech
TECH_TICKERS = BIG_TECH_TICKERS | SAAS_TICKERS | SEMIS_TICKERS


# ============================================================
# TECH-SPECIFIC CONCEPTS (vacio por ahora)
# ============================================================
# Conceptos GAAP que SOLO existen en Tech y no en otros sectores.
# Por ahora vacio - los conceptos universales (R&D, SBC, deferred_revenue,
# goodwill) viven en gaap_taxonomy.py general.
#
# Futuro:
# - Custom extensions de AMZN (amzn:FulfillmentExpense, etc) si validamos
#   que mejoran cobertura vs los tags estandar.
# - SubscriptionRevenue / ProfessionalServicesRevenue como sub-componentes
#   de NOW/CRM si necesitamos desagregar.

TECH_SPECIFIC_CONCEPTS = {}


# ============================================================
# METRICAS TECH-SPECIFIC (formulas + healthy ranges)
# ============================================================
# Algunas son universales (FCF margin, Capex intensity) pero con
# ranges Tech-especificos. Otras son genuinamente Tech-only (Rule of 40).

TECH_SPECIFIC_METRICS = {
    "rule_of_40": {
        "description": "Revenue growth % + FCF margin % (SaaS health metric)",
        "formula": "(revenue_growth_yoy_pct) + (fcf_margin_pct)",
        "applies_to": ["CRM", "NOW"],  # SaaS pure-play
        "healthy_range": (40, 100),
        "industry_median_2024": 34,  # Meritech Aug 2024
        "industry_median_2025q1": 12,  # CloudZero Q1 2025 (deteriorando)
        "notes": "Top quartile >40. Below 20 sustained = product-market fit deterioration.",
        "calculable_from_xbrl": True,
    },
    "sbc_to_revenue": {
        "description": "Stock-based compensation as % of revenue (dilution proxy)",
        "formula": "stock_based_compensation / revenue",
        "applies_to": "ALL_TECH",
        "healthy_range": {
            "big_tech": (0.05, 0.15),    # Mature mega-cap ~10% (META ~10%)
            "saas": (0.15, 0.25),         # SaaS typical 15-25%
            "semis": (0.05, 0.15),        # Semis typical 5-15%
        },
        "notes": "Sustained >25% = dilution risk. >50% of op income = non-GAAP earnings fictional.",
        "calculable_from_xbrl": True,
    },
    "rd_to_revenue": {
        "description": "R&D expense as % of revenue (innovation intensity)",
        "formula": "research_and_development / revenue",
        "applies_to": "ALL_TECH",
        "healthy_range": {
            "big_tech": (0.10, 0.30),    # META FY23 ~28%, GOOGL ~15%
            "saas": (0.15, 0.30),         # SaaS heavy R&D
            "semis": (0.15, 0.30),        # NVDA, MU heavy R&D
        },
        "notes": "Sustained >40% = pre-revenue or over-investment. <10% in Tech = competitive risk.",
        "calculable_from_xbrl": True,
    },
    "fcf_margin": {
        "description": "Free cash flow margin (cash generation quality)",
        "formula": "(operating_cash_flow - capex) / revenue",
        "applies_to": "ALL_TECH",
        "healthy_range": {
            "big_tech": (0.20, 0.40),    # META 33% FY23
            "saas": (0.20, 0.35),         # Mature SaaS 25-35%
            "semis": (0.10, 0.30),        # Cyclical, lower in downturns
        },
        "notes": "Primary valuation metric for mature Tech. >40% = premium asset.",
        "calculable_from_xbrl": True,
    },
    "capex_intensity": {
        "description": "Capex as % of revenue (AI infra regime change indicator)",
        "formula": "capex / revenue",
        "applies_to": "ALL_TECH",
        "healthy_range": {
            "big_tech": (0.10, 0.30),    # AI era: META FY24 ~22%, regimen cambio desde 10%
            "saas": (0.02, 0.08),         # Asset-light tipicamente
            "semis": (0.10, 0.30),        # Capital intensive (NVDA cliente de TSMC, MU propio fab)
        },
        "notes": "Big Tech 2024-2026 en regimen capex elevado por AI. Recalibrar modelos.",
        "calculable_from_xbrl": True,
    },
}


# ============================================================
# VALIDATION RULES — Rangos esperables por sub-grupo
# ============================================================

TECH_VALIDATION_RULES = {
    "operating_margin": {
        "big_tech": {"min": 0.15, "max": 0.50, "notes": "META 35%, GOOGL 30%, MSFT 40%. <15% = problema operacional."},
        "saas": {"min": -0.05, "max": 0.20, "notes": "GAAP op margin SaaS bajo por SBC. CRM/NOW ~7-15% GAAP."},
        "semis": {"min": -0.10, "max": 0.55, "notes": "Ciclico extremo. NVDA AI era >50%. MU downcycle puede negativo."},
    },
    "gross_margin": {
        "big_tech": {"min": 0.40, "max": 0.85, "notes": "AMZN ~45% (mix retail+AWS), META/GOOGL ~80%."},
        "saas": {"min": 0.65, "max": 0.85, "notes": "SaaS target 70-85%."},
        "semis": {"min": 0.30, "max": 0.80, "notes": "NVDA AI margins ~75%. MU DRAM downcycle ~20-30%."},
    },
    "rd_to_revenue": {
        "max": 0.40,
        "notes": "Sustained >40% = pre-revenue o over-investment. Flag.",
    },
    "sbc_to_revenue": {
        "max": 0.30,
        "notes": "Sustained >30% = dilution materially destroying GAAP earnings.",
    },
    "current_ratio": {
        "saas": {"min": 1.5, "notes": "SaaS healthy >2x. Deferred revenue infla CL pero asset side mas grande."},
    },
}


# ============================================================
# KNOWN LIMITATIONS (descubiertas en validacion mayo 2026)
# ============================================================

KNOWN_LIMITATIONS = {
    "saas_interest_expense": {
        "affects": ["CRM", "NOW"],
        "issue": "SaaS net cash positive companies no reportan interest_expense como line item separado.",
        "workaround": "Sistema acepta NOT_FOUND. Para analisis, asumir interest_expense ~= 0.",
        "documented_in": "SECTOR_RESEARCH_OVERVIEW.md - Universal Fixes May 18 2026",
    },
    "ndr_arr_not_in_xbrl": {
        "affects": ["CRM", "NOW"],
        "issue": "Net Dollar Retention y Annual Recurring Revenue NO estan en XBRL.",
        "workaround": "Parse MD&A o earnings releases. Out of scope para extractor base.",
        "documented_in": "SECTOR_RESEARCH_OVERVIEW.md - Iteration 1 Tech",
    },
    "amzn_custom_extensions": {
        "affects": ["AMZN"],
        "issue": "Amazon usa custom GAAP extensions (amzn:FulfillmentExpense, etc.) para algunos line items.",
        "workaround": "Por ahora extractor logra 18/18 con tags estandar. Si aparece concept que falla, evaluar agregar custom tags a TECH_SPECIFIC_CONCEPTS.",
        "documented_in": "SECTOR_RESEARCH_OVERVIEW.md - Iteration 1 Tech",
    },
}


# ============================================================
# HELPERS
# ============================================================

def is_tech_ticker(ticker: str) -> bool:
    """Returns True if ticker belongs to Technology sector."""
    return ticker.upper() in TECH_TICKERS


def get_tech_subsector(ticker: str) -> str:
    """
    Returns the Tech sub-sector for a ticker.

    Returns:
        "big_tech", "saas", or "semis"
        None if ticker not in Tech universe
    """
    ticker_upper = ticker.upper()
    if ticker_upper in BIG_TECH_TICKERS:
        return "big_tech"
    if ticker_upper in SAAS_TICKERS:
        return "saas"
    if ticker_upper in SEMIS_TICKERS:
        return "semis"
    return None


def get_tech_gaap_names(concept: str) -> list:
    """
    Returns GAAP names for a Tech-specific concept (if exists).

    For universal concepts (revenue, operating_income, R&D, SBC, etc.),
    use gaap_taxonomy.get_names_for_concept() instead - Tech does NOT
    require GAAP overrides for those.

    Returns empty list if concept not in TECH_SPECIFIC_CONCEPTS.
    """
    if concept not in TECH_SPECIFIC_CONCEPTS:
        return []
    return TECH_SPECIFIC_CONCEPTS[concept].get("names", [])


if __name__ == "__main__":
    print("Technology sector module loaded.")
    print(f"  Total Tech tickers: {len(TECH_TICKERS)}")
    print(f"    Big Tech: {sorted(BIG_TECH_TICKERS)}")
    print(f"    SaaS:     {sorted(SAAS_TICKERS)}")
    print(f"    Semis:    {sorted(SEMIS_TICKERS)}")
    print(f"  Tech-specific metrics: {list(TECH_SPECIFIC_METRICS.keys())}")
    print(f"  Validation rules: {list(TECH_VALIDATION_RULES.keys())}")
    print(f"  Known limitations: {list(KNOWN_LIMITATIONS.keys())}")
    print()
    print("Quick test:")
    print(f"  is_tech_ticker('META')  = {is_tech_ticker('META')}")
    print(f"  is_tech_ticker('XOM')   = {is_tech_ticker('XOM')}")
    print(f"  get_tech_subsector('META') = {get_tech_subsector('META')}")
    print(f"  get_tech_subsector('NOW')  = {get_tech_subsector('NOW')}")
    print(f"  get_tech_subsector('NVDA') = {get_tech_subsector('NVDA')}")
