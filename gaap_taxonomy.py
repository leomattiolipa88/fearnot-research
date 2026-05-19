"""
GAAP Taxonomy Mapping
---------------------
Mapea conceptos contables a sus posibles nombres GAAP en SEC EDGAR.

Cada empresa puede usar nombres ligeramente distintos para el mismo concepto:
- XOM usa "Revenues"
- META usa "RevenueFromContractWithCustomerExcludingAssessedTax"
- NU (banco) usa "InterestAndDividendIncomeOperating"

Estructura: lista de nombres en orden de preferencia. Probamos uno a uno
hasta encontrar match. El primer match gana.

Coverage target: ~90% de empresas USA-listed. Si una empresa no matchea,
agregar el nombre nuevo a la lista correspondiente.
"""

GAAP_TAXONOMY = {

    # =========================================================
    # INCOME STATEMENT — Top Line
    # =========================================================
    "revenue": {
        "description": "Total revenue from operations (top line)",
        "names": [
            "Revenues",                                                    # XOM, NOW (older), insurance
            "RevenueFromContractWithCustomerExcludingAssessedTax",         # Most tech post-2018 GAAP (META, NOW newer)
            "RevenueFromContractWithCustomerIncludingAssessedTax",         # Some retail with sales tax included
            "SalesRevenueNet",                                             # Pre-2018, some legacy filers
            "SalesRevenueGoodsNet",                                        # Companies that split goods vs services
            "Revenue",                                                     # Rare singular form
            "TotalRevenuesAndOtherIncome",                                 # XOM in some years (incluye equity affiliates)
        ],
        "sector_overrides": {
            "bank": [
                "InterestAndDividendIncomeOperating",                      # Most banks
                "InterestIncomeOperating",                                 # Some banks
                "Revenues",                                                # Some bank holding cos
            ],
            "insurance": [
                "Revenues",
                "PremiumsEarnedNet",
            ]
        }
    },

    # =========================================================
    # INCOME STATEMENT — Costs and Operating
    # =========================================================
    "cost_of_revenue": {
        "description": "Direct cost of producing revenue (COGS)",
        "names": [
            "CostOfRevenue",                                               # Most common
            "CostOfGoodsAndServicesSold",                                  # Industrial, mixed
            "CostOfGoodsSold",                                             # Pure goods
            "CostOfServices",                                              # Pure services
            "CostsAndExpenses",                                            # Some integrated
        ]
    },

    "gross_profit": {
        "description": "Revenue minus cost of revenue",
        "names": [
            "GrossProfit",
        ]
    },

    "operating_income": {
        "description": "Operating Income reported directly. NIVEL 1 only.",
        "names": [
            "OperatingIncomeLoss",                                         # META, NOW, AMCR
            "IncomeLossFromOperations",                                    # Rare variant
        ]
    },

    "operating_income_approximation": {
        "description": "Income Before Tax — fallback approximation when OperatingIncomeLoss not reported. Use with quality flag.",
        "names": [
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",  # XOM
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",         # Variant
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesNoncontrollingInterest",
        ]
    },

    "interest_expense": {
        "description": "Interest paid on debt",
        "names": [
            "InterestExpense",                                             # Most common
            "InterestExpenseDebt",                                         # When split between debt types
            "InterestAndDebtExpense",                                      # Combined
            "InterestExpenseOperating",                                    # Some industrials
            "InterestExpenseNonoperating",                                 # AMZN and similar
        ]
    },

    "depreciation_amortization": {
        "description": "D&A — non-cash expense for asset wear",
        "names": [
            "DepreciationDepletionAndAmortization",                        # Energy/mining (XOM, EOG)
            "DepreciationAndAmortization",                                 # General industry
            "Depreciation",                                                # Only depreciation
            "DepreciationAmortizationAndAccretion",                        # Some utilities
            "DepreciationNonproduction",                                   # Rare
        ]
    },

    "income_tax_expense": {
        "description": "Provision for income taxes",
        "names": [
            "IncomeTaxExpenseBenefit",                                     # Most common
            "CurrentIncomeTaxExpenseBenefit",                              # When split current/deferred
        ]
    },

    "net_income": {
        "description": "Bottom line — income attributable to parent company",
        "names": [
            "NetIncomeLoss",                                               # Standard, attributable to parent (XOM, META, NOW)
            "ProfitLoss",                                                  # Some IFRS-style filers (mainly foreign)
            "NetIncomeLossAttributableToParent",                           # When explicitly broken out
        ]
    },

    "minority_interest_income": {
        "description": "Income attributable to non-controlling interests",
        "names": [
            "NetIncomeLossAttributableToNoncontrollingInterest",
            "MinorityInterestInNetIncomeLossOfConsolidatedEntities",       # Older filings
        ]
    },

    # =========================================================
    # INCOME STATEMENT — Per Share
    # =========================================================
    "eps_basic": {
        "description": "Earnings per share, basic",
        "unit": "USD/shares",
        "names": [
            "EarningsPerShareBasic",
        ]
    },

    "eps_diluted": {
        "description": "Earnings per share, diluted (preferred for analysis)",
        "unit": "USD/shares",
        "names": [
            "EarningsPerShareDiluted",
        ]
    },

    "shares_diluted": {
        "description": "Weighted average diluted shares outstanding",
        "unit": "shares",
        "names": [
            "WeightedAverageNumberOfDilutedSharesOutstanding",
            "WeightedAverageNumberOfSharesOutstandingDiluted",             # Slight variant
        ]
    },

    # =========================================================
    # BALANCE SHEET — Assets
    # =========================================================
    "cash_and_equivalents": {
        "description": "Cash plus highly liquid investments",
        "names": [
            "CashAndCashEquivalentsAtCarryingValue",                       # Most common
            "Cash",                                                        # Rare, only cash
            "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", # Some banks
        ]
    },

    "current_assets": {
        "description": "Assets convertible to cash within 12 months",
        "names": [
            "AssetsCurrent",                                               # Standard
        ]
    },

    "total_assets": {
        "description": "Total assets on balance sheet",
        "names": [
            "Assets",                                                      # Standard for everyone
        ]
    },

    "ppe_net": {
        "description": "Property, plant and equipment, net of depreciation",
        "names": [
            "PropertyPlantAndEquipmentNet",                                # Standard
        ]
    },

    # =========================================================
    # BALANCE SHEET — Liabilities & Equity
    # =========================================================
    "current_liabilities": {
        "description": "Liabilities due within 12 months",
        "names": [
            "LiabilitiesCurrent",
        ]
    },

    "total_liabilities": {
        "description": "Total liabilities",
        "names": [
            "Liabilities",
        ]
    },

    "long_term_debt": {
        "description": "Debt due in >12 months",
        "names": [
            "LongTermDebt",                                                # Standard
            "LongTermDebtNoncurrent",                                      # When excluding current portion explicit
            "LongTermDebtAndCapitalLeaseObligations",                      # Some industrials,
            "ConvertibleLongTermNotesPayable",                            # SaaS like NOW
        ]
    },

    "short_term_debt": {
        "description": "Debt due within 12 months",
        "names": [
            "ShortTermBorrowings",                                         # Most common
            "DebtCurrent",                                                 # Some banks
            "LongTermDebtCurrent",                                         # Current portion of LT debt
            "CommercialPaper",                                             # Companies using CP financing
            "NotesPayableCurrent",                                         # Older
        ]
    },

    "stockholders_equity": {
        "description": "Total equity attributable to parent company",
        "names": [
            "StockholdersEquity",                                          # Standard, attributable to parent
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", # When includes minority
        ]
    },

    # =========================================================
    # CASH FLOW STATEMENT
    # =========================================================
    "operating_cash_flow": {
        "description": "Cash from operating activities",
        "names": [
            "NetCashProvidedByUsedInOperatingActivities",                  # Standard
            "NetCashProvidedByOperatingActivities",                        # Slight variant
        ]
    },

    "capex": {
        "description": "Capital expenditures (purchases of PP&E)",
        "names": [
            "PaymentsToAcquirePropertyPlantAndEquipment",                  # Most common
            "PaymentsToAcquireProductiveAssets",                           # Energy (XOM uses this sometimes)
            "PaymentsForCapitalImprovements",                              # Utilities, REITs
            "PaymentsToAcquireOilAndGasProperty",                          # Pure E&P
            "PaymentsToAcquireOilAndGasPropertyAndEquipment",
            "CapitalExpenditures",                                         # Rare modern filers
        ]
    },

    "dividends_paid": {
        "description": "Total dividends paid to shareholders",
        "names": [
            "PaymentsOfDividends",                                         # Standard
            "PaymentsOfDividendsCommonStock",                              # When split common vs preferred
        ]
    },

    "stock_repurchases": {
        "description": "Cash used for stock buybacks",
        "names": [
            "PaymentsForRepurchaseOfCommonStock",
            "TreasuryStockValueAcquiredCostMethod",                        # Sometimes reported balance-sheet-side
        ]
    },
}


# =========================================================
# SECTOR CLASSIFICATION
# =========================================================
# Maps tickers to sectors for applying sector_overrides above.
# This is manual for now — automated sector detection is Phase 2.

SECTOR_BY_TICKER = {
    # Banks (use bank overrides)
    "NU": "bank",
    "JPM": "bank",
    "BAC": "bank",
    "WFC": "bank",
    "C": "bank",
    "GS": "bank",
    "MS": "bank",

    # Insurance
    "BRK-B": "insurance",   # Berkshire is technically a holding but reports insurance-heavy
    "AIG": "insurance",
    "MET": "insurance",
    "PRU": "insurance",

    # Everything else defaults to "general" (uses standard names)
    # XOM, META, NOW, VST, AMCR, PENG, MELI all default to general
}


def get_names_for_concept(concept: str, ticker: str = None) -> list:
    """
    Returns ordered list of GAAP names to try for a given concept.

    If ticker is provided and maps to a sector with overrides,
    sector-specific names are prepended.

    Args:
        concept: key in GAAP_TAXONOMY (e.g., "revenue")
        ticker: optional ticker for sector-specific lookup

    Returns:
        List of GAAP names to try in order. Empty list if concept unknown.
    """
    if concept not in GAAP_TAXONOMY:
        return []

    entry = GAAP_TAXONOMY[concept]
    default_names = entry.get("names", [])

    # If ticker has sector override, prepend sector-specific names
    if ticker and "sector_overrides" in entry:
        sector = SECTOR_BY_TICKER.get(ticker.upper(), "general")
        if sector in entry["sector_overrides"]:
            return entry["sector_overrides"][sector] + default_names

    return default_names




def get_unit_for_concept(concept: str) -> str:
    """
    Returns the SEC EDGAR unit for a given concept.
    Defaults to USD. Exceptions: EPS (USD/shares), shares (shares).
    """
    if concept not in GAAP_TAXONOMY:
        return "USD"
    return GAAP_TAXONOMY[concept].get("unit", "USD")

if __name__ == "__main__":
    # Quick test
    print("GAAP Taxonomy loaded.")
    print(f"  {len(GAAP_TAXONOMY)} concepts defined")
    print(f"  {len(SECTOR_BY_TICKER)} tickers with sector classification")

    # Example: get names for revenue (XOM vs NU vs default)
    print("\nExample lookups:")
    print(f"  Revenue (XOM):  {get_names_for_concept('revenue', 'XOM')[:3]}")
    print(f"  Revenue (NU):   {get_names_for_concept('revenue', 'NU')[:3]}")
    print(f"  Revenue (META): {get_names_for_concept('revenue', 'META')[:3]}")
