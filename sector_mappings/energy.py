"""
Energy Sector — Sector-Specific GAAP Mapping & Metrics
========================================================

Universo: Integrated Oil & Gas (XOM, CVX), E&P (OXY, EOG, VIST), Refining (VLO).

Caracteristicas del sector que justifican overrides:
- Revenue puede usar nombres distintos: "Revenues" agregado (XOM, CVX)
  vs "OilAndGasRevenue" desagregado (E&P puros como EOG).
- Operating Income SI lo reportan directo via OperatingIncomeLoss
  (verificado en research: todos los reference names lo reportan).
  XOM lo reporta pero en su 10-K usa "CostsAndExpenses" agregado
  que requiere validacion contra valor reportado.
- DD&A se reporta como "DepreciationDepletionAndAmortization"
  (energy-specific: incluye Depletion para reservas).
- Exploration expense es energy-only (E&P con "successful efforts").

Fuente: SECTOR_RESEARCH_OVERVIEW.md, iteracion 1.
"""

# ============================================================
# UNIVERSO DE TICKERS EN EL SECTOR
# ============================================================
ENERGY_TICKERS = {
    "XOM",   # Exxon Mobil — Integrated Major
    "CVX",   # Chevron — Integrated Major
    "OXY",   # Occidental Petroleum — E&P
    "EOG",   # EOG Resources — E&P (premium, low F&D cost)
    "VLO",   # Valero Energy — Pure Refiner
    "VIST",  # Vista Energy — E&P internacional (Vaca Muerta)
}


# ============================================================
# GAAP OVERRIDES — Conceptos donde Energy difiere del general
# ============================================================
# Lista en orden de preferencia. Probar uno a uno hasta encontrar match.
# Los nombres ya estan en GAAP_TAXONOMY general, pero acá reforzamos
# y priorizamos los energy-specific.

ENERGY_GAAP_OVERRIDES = {
    "revenue": [
        "Revenues",                                                    # XOM, CVX agregado
        "OilAndGasRevenue",                                            # EOG, E&P puros (puede tener axis de oil/gas/NGL)
        "RevenueFromContractWithCustomerExcludingAssessedTax",         # VLO refiner post-2018
        "SalesRevenueNet",                                             # Legacy pre-2018
    ],
    "operating_income": [
        "OperatingIncomeLoss",                                         # Verificado: todos los reference reportan
    ],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",                        # Energy-specific (incluye Depletion)
        "DepreciationAndAmortization",                                 # Fallback general
    ],
    "cost_of_revenue": [
        "CostOfRevenue",                                               # Refiners (VLO)
        "CostsAndExpenses",                                            # XOM agrupado
        "OilAndGasProductionExpense",                                  # E&P specific
    ],
}


# ============================================================
# CONCEPTOS ENERGY-SPECIFIC (no existen en otros sectores)
# ============================================================
# Estos van a requerir lookups separados en facts SEC.
# Algunos estan en us-gaap, otros requieren parseo de MD&A.

ENERGY_SPECIFIC_CONCEPTS = {
    "exploration_expense": {
        "description": "Exploration costs (successful efforts method)",
        "names": ["ExplorationExpense", "ExplorationExpenseMining"],
        "applies_to": ["OXY", "EOG", "VIST"],  # E&P puros, no integrated
        "notes": "EOG uses successful efforts; XOM/CVX have it but aggregated.",
    },
    "oil_gas_property_impairment": {
        "description": "Impairments of oil & gas properties (cyclical)",
        "names": ["ImpairmentOfOilAndGasProperties"],
        "applies_to": ["XOM", "CVX", "OXY", "EOG", "VIST"],
        "notes": "Large in 2015 and 2020 downturns. Flag if >5% of total assets.",
    },
    "proved_reserves": {
        "description": "Total proved reserves (boe)",
        "names": None,  # No esta en XBRL standard facts
        "applies_to": ["XOM", "CVX", "OXY", "EOG", "VIST"],
        "notes": "FASB ASC 932 supplemental disclosure. Requires parsing supplemental schedules, NOT in standard companyfacts API.",
    },
}


# ============================================================
# METRICAS SECTOR-SPECIFIC (las que SOLO importan en energy)
# ============================================================
ENERGY_SPECIFIC_METRICS = {
    "finding_development_cost": {
        "description": "Finding & Development cost per boe",
        "formula": "(Exploration + Development + Acquisition costs of proved props) / Reserves added",
        "calculable_from_xbrl": False,  # Requiere parseo de FASB ASC 932 supplemental
        "healthy_range_usd_per_boe": (5, 15),
        "notes": "EOG historically ~$8-10/boe. Pure XBRL extraction NOT possible.",
    },
    "reserve_replacement_ratio": {
        "description": "Reserves added / Annual production",
        "formula": "(Extensions + Revisions + Acquisitions) / Production",
        "calculable_from_xbrl": False,
        "healthy_range": (1.0, 1.5),  # 100% replace o mas
        "notes": "BP dropped RRR as KPI 2020. Below 80% = concerning.",
    },
    "lifting_cost": {
        "description": "Production expense per boe lifted",
        "formula": "OilAndGasProductionExpense / Production volumes (boe)",
        "calculable_from_xbrl": False,  # Production volumes en MD&A, no XBRL
        "healthy_range_usd_per_boe": (5, 25),  # Shale 5-10, deepwater 15-25
        "notes": "Critical en downturns. Above $20/boe en US shale = bandera roja.",
    },
    "refining_margin": {
        "description": "Gross margin per barrel refined (crack spread)",
        "formula": "Gross profit / Throughput volumes",
        "calculable_from_xbrl": False,
        "healthy_range_usd_per_bbl": (10, 25),
        "applies_to": ["VLO"],
        "notes": "Crack spread Gulf Coast 3:2:1 typico $10-25/bbl.",
    },
}


# ============================================================
# VALIDATION RULES — Rangos esperables, flag si fuera
# ============================================================
ENERGY_VALIDATION_RULES = {
    "operating_margin": {
        "min": -0.10,  # -10%
        "max": 0.35,   # 35%
        "notes": "Sustained outside this range = data error or massive impairment year",
    },
    "fcf_margin": {
        "max": 0.30,   # 30%
        "notes": "Above 30% likely peak-cycle (Brent >$100). Do not project forward.",
    },
    "capex_to_dda": {
        "min": 0.7,
        "notes": "Below 0.7x for 2+ years = liquidating reserves, bearish.",
    },
    "lifting_cost_usd_per_boe": {
        "max": 20,
        "notes": "Above $20/boe in US shale = asset quality / mature decline flag.",
    },
}


# ============================================================
# HELPERS
# ============================================================
def is_energy_ticker(ticker: str) -> bool:
    """Returns True if ticker belongs to Energy sector."""
    return ticker.upper() in ENERGY_TICKERS


def get_energy_gaap_names(concept: str) -> list:
    """
    Returns GAAP names for a concept, applying energy overrides if exist.
    Falls back to empty list if concept not in overrides (caller should
    use general GAAP_TAXONOMY then).
    """
    return ENERGY_GAAP_OVERRIDES.get(concept, [])


if __name__ == "__main__":
    print("Energy sector module loaded.")
    print(f"  Tickers in universe: {sorted(ENERGY_TICKERS)}")
    print(f"  GAAP overrides defined for: {list(ENERGY_GAAP_OVERRIDES.keys())}")
    print(f"  Energy-specific concepts: {list(ENERGY_SPECIFIC_CONCEPTS.keys())}")
    print(f"  Energy-specific metrics: {list(ENERGY_SPECIFIC_METRICS.keys())}")
    print(f"  Validation rules: {list(ENERGY_VALIDATION_RULES.keys())}")
    print()
    print("Quick test:")
    print(f"  is_energy_ticker('XOM') = {is_energy_ticker('XOM')}")
    print(f"  is_energy_ticker('META') = {is_energy_ticker('META')}")
    print(f"  Revenue names for energy: {get_energy_gaap_names('revenue')[:3]}...")
