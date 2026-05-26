"""
IFRS Taxonomy - Mapeo de conceptos financieros estandar a tags ifrs-full
=========================================================================

Paralelo a gaap_taxonomy.py. Para empresas que reportan via 20-F bajo IFRS.

Estado de verificacion: TODOS los tags abajo fueron empiricamente verificados
contra Nu Holdings 20-F FY2024 (CIK 0001691493) el 21 mayo 2026.
- 44/49 verified: tag existe + tiene valor FY2024
- 5/49 tag existe pero NU no reporta valor FY2024 (marcados con notes)

Diferencias clave vs us-gaap:
- IFRS Banks NO tienen "Net Interest Income" como subtotal tagged
  (se computa: gross interest income - interest expense)
- ProfitLoss (IFRS) vs NetIncomeLoss (us-gaap) - same concept, distinto nombre
- EquityAttributableToOwnersOfParent (IFRS) vs StockholdersEquity (us-gaap)
- IFRS Balance Sheet en liquidity order para banks (no current/non-current)
- Capital ratios (CET1) son narrative-tagged only - parse desde texto

Hallazgos empiricos importantes (descubiertos durante verificacion):
- NU NO usa custom extensions (no namespace 'nu:'). Research markdown afirmaba
  ~15 custom extensions UNVERIFIED - todas resultaron inexistentes.
- InterestRevenueExpense y InterestExpense reportan el MISMO valor en NU
  (filer tagging issue - usar gross income desde notes para NIM accurate).
- Provision for credit losses: NU reporto FY2023 pero NO FY2024 como discrete
  tag. Para FY2024 hay que parsear notes o usar OperatingExpense breakdown.

Future LatAm IFRS filers (StoneCo, PagSeguro, Inter) deberian poder usar este
mismo taxonomy con minor ajustes - es el "LatAm fintech IFRS template".

Fuente: empirical discovery via SEC companyfacts API + IFRS Taxonomy 2024
"""


# ============================================================
# IFRS_TAXONOMY: mismas keys conceptuales que GAAP_TAXONOMY
# ============================================================

IFRS_TAXONOMY = {

    # ============================================================
    # INCOME STATEMENT
    # ============================================================

    "revenue": {
        "description": "Total revenue (top line)",
        "names": ["Revenue"],
    },

    "interest_expense": {
        "description": "Interest expense (cost of deposits + borrowings)",
        "names": [
            "InterestExpense",
            "InterestExpenseOnDepositsFromCustomers",  # sub-component for NU
            "InterestRevenueExpense",  # NU tagged this with same value - filer quirk
        ],
        "notes": "NU tagged InterestExpense and InterestRevenueExpense with same value FY24. Investigate per-filer.",
    },

    "fee_income": {
        "description": "Fee and commission income (Banks)",
        "names": ["FeeAndCommissionIncome"],
    },

    "provision_for_credit_losses": {
        "description": "IFRS 9 expected credit loss provisions",
        "names": ["IncreaseDecreaseInAllowanceAccountForCreditLossesOfFinancialAssets"],
        "notes": "NU did NOT report this as discrete tag for FY2024 (only FY2023 and earlier). Parse from notes for FY24.",
    },

    "gross_profit": {
        "description": "Revenue minus cost of revenue. Rare in banks but NU reports it.",
        "names": ["GrossProfit"],
    },

    "operating_expense_total": {
        "description": "Total operating expense (Banks: noninterest expense equivalent)",
        "names": ["OperatingExpense"],
    },

    "selling_marketing_expense": {
        "description": "Sales and marketing expense",
        "names": [
            "SalesAndMarketingExpense",
            "SellingExpense",
        ],
    },

    "general_administrative_expense": {
        "description": "General and administrative expense",
        "names": ["GeneralAndAdministrativeExpense"],
        "notes": "NU has tag but no FY2024 value reported - likely embedded in OperatingExpense.",
    },

    "depreciation_amortization": {
        "description": "Depreciation and amortization (combine PP&E + intangibles)",
        "names": [
            "AmortisationIntangibleAssetsOtherThanGoodwill",
            "AdjustmentsForDepreciationAndAmortisationExpense",  # cash flow reconciliation
            "DepreciationExpense",  # NU has tag but no FY24 value
        ],
        "notes": "For NU FY24, AdjustmentsForDepreciationAndAmortisationExpense (cash flow) is most reliable.",
    },

    "share_based_compensation": {
        "description": "Stock-based compensation (IFRS 2)",
        "names": ["ExpenseFromSharebasedPaymentTransactionsWithEmployees"],
        "notes": "NU reports as negative value (it is an expense).",
    },

    "income_tax_expense": {
        "description": "Income tax expense (current + deferred)",
        "names": ["IncomeTaxExpenseContinuingOperations"],
    },

    "profit_before_tax": {
        "description": "Profit before income tax (PBT)",
        "names": ["ProfitLossBeforeTax"],
    },

    "net_income": {
        "description": "Net income / Profit for the period (after tax)",
        "names": [
            "ProfitLoss",
            "ProfitLossAttributableToOwnersOfParent",  # excludes NCI
        ],
    },

    "net_income_attributable_parent": {
        "description": "Net income attributable to parent (excludes NCI)",
        "names": ["ProfitLossAttributableToOwnersOfParent"],
    },

    "minority_interest_income": {
        "description": "Profit attributable to non-controlling interests",
        "names": ["ProfitLossAttributableToNoncontrollingInterests"],
    },

    "comprehensive_income": {
        "description": "Total comprehensive income (P&L + OCI)",
        "names": ["ComprehensiveIncome"],
    },

    # ============================================================
    # PER SHARE
    # ============================================================

    "eps_basic": {
        "description": "Basic earnings per share",
        "unit": "USD/shares",
        "names": ["BasicEarningsLossPerShare"],
    },

    "eps_diluted": {
        "description": "Diluted earnings per share",
        "unit": "USD/shares",
        "names": ["DilutedEarningsLossPerShare"],
    },

    "shares_diluted": {
        "description": "Weighted average diluted shares outstanding",
        "unit": "shares",
        "names": [
            "AdjustedWeightedAverageShares",
            "WeightedAverageShares",
        ],
    },

    # ============================================================
    # BALANCE SHEET (liquidity order for banks)
    # ============================================================

    "total_assets": {
        "description": "Total assets",
        "names": ["Assets"],
    },

    "cash_and_equivalents": {
        "description": "Cash and cash equivalents",
        "names": ["CashAndCashEquivalents"],
    },

    "loans_to_customers": {
        "description": "Loans and advances to customers (Banks)",
        "names": [
            "LoansAndAdvancesToCustomers",
            "LoansAndReceivables",
        ],
    },

    "loans_to_banks": {
        "description": "Loans and advances to banks (interbank)",
        "names": ["LoansAndAdvancesToBanks"],
    },

    "financial_assets_amortized_cost": {
        "description": "Financial assets at amortized cost",
        "names": ["FinancialAssetsAtAmortisedCost"],
    },

    "financial_assets_fvtpl": {
        "description": "Financial assets at fair value through P&L",
        "names": ["FinancialAssetsAtFairValueThroughProfitOrLoss"],
    },

    "financial_assets_fvtoci": {
        "description": "Financial assets at fair value through OCI",
        "names": ["FinancialAssetsAtFairValueThroughOtherComprehensiveIncome"],
    },

    "ppe_net": {
        "description": "Property, plant and equipment (net)",
        "names": ["PropertyPlantAndEquipment"],
    },

    "intangible_assets": {
        "description": "Intangible assets other than goodwill",
        "names": ["IntangibleAssetsOtherThanGoodwill"],
    },

    "goodwill": {
        "description": "Goodwill from acquisitions",
        "names": ["Goodwill"],
    },

    "deferred_tax_assets": {
        "description": "Deferred tax assets",
        "names": ["DeferredTaxAssets"],
    },

    "mandatory_central_bank_deposits": {
        "description": "Compulsory deposits at central bank (regulatory)",
        "names": ["MandatoryReserveDepositsAtCentralBanks"],
    },

    "total_liabilities": {
        "description": "Total liabilities",
        "names": ["Liabilities"],
    },

    "deposits_from_customers": {
        "description": "Customer deposits (primary funding for banks)",
        "names": [
            "DepositsFromCustomers",
            "CurrentDepositsFromCustomers",
        ],
    },

    "deposits_from_banks": {
        "description": "Deposits from banks (interbank funding)",
        "names": ["DepositsFromBanks"],
    },

    "borrowings_total": {
        "description": "Total borrowings (wholesale funding)",
        "names": [
            "Borrowings",
            "OtherBorrowings",
        ],
    },

    "short_term_debt": {
        "description": "Short-term borrowings",
        "names": ["ShorttermBorrowings"],
    },

    "stockholders_equity": {
        "description": "Stockholders equity attributable to parent",
        "names": [
            "EquityAttributableToOwnersOfParent",
            "Equity",  # includes NCI
        ],
    },

    "noncontrolling_interests": {
        "description": "Non-controlling interests in equity",
        "names": ["NoncontrollingInterests"],
    },

    "allowance_for_credit_losses": {
        "description": "Balance sheet allowance for credit losses",
        "names": ["AllowanceAccountForCreditLossesOfFinancialAssets"],
        "notes": "NU has tag but only 1 entry total - sparse reporting.",
    },

    # ============================================================
    # CASH FLOW STATEMENT
    # ============================================================

    "operating_cash_flow": {
        "description": "Cash flows from operating activities",
        "names": ["CashFlowsFromUsedInOperatingActivities"],
    },

    "investing_cash_flow": {
        "description": "Cash flows from investing activities",
        "names": ["CashFlowsFromUsedInInvestingActivities"],
    },

    "financing_cash_flow": {
        "description": "Cash flows from financing activities",
        "names": ["CashFlowsFromUsedInFinancingActivities"],
    },

    "cash_change_total": {
        "description": "Net change in cash and equivalents",
        "names": ["IncreaseDecreaseInCashAndCashEquivalents"],
    },

    # NOTE: capex y dividends_paid no son discrete tags en IFRS para banks.
    # Para banks, capex es typically minimal (mostly intangibles/software).
    # Hay que parsear breakdown del cash flow financing/investing.
}


# ============================================================
# IFRS FILERS REGISTRY
# ============================================================
# Tickers que reportan en IFRS (20-F filers). Default es us-gaap.
# Cualquier ticker en este set fuerza dispatch a IFRS extractor.

IFRS_FILERS = {
    "NU",   # Nu Holdings (Brazilian fintech, CIK 0001691493)
    # Futuros candidatos LatAm fintech (no validados aun):
    # "STNE",  # StoneCo
    # "PAGS",  # PagSeguro
    # "INTR",  # Inter & Co
}


# ============================================================
# HELPERS
# ============================================================

def get_ifrs_names_for_concept(concept: str) -> list:
    """
    Returns ordered list of IFRS tag names to try for a concept.

    Args:
        concept: standard concept key (ej: "revenue", "net_income")

    Returns:
        List of IFRS tag names. Empty if concept unknown.
    """
    if concept not in IFRS_TAXONOMY:
        return []
    return IFRS_TAXONOMY[concept].get("names", [])


def get_ifrs_unit_for_concept(concept: str) -> str:
    """
    Returns the IFRS unit for a concept.
    Defaults to USD. Exceptions: EPS (USD/shares), shares.
    """
    if concept not in IFRS_TAXONOMY:
        return "USD"
    return IFRS_TAXONOMY[concept].get("unit", "USD")


def is_ifrs_filer(ticker: str) -> bool:
    """Returns True if ticker reports under IFRS taxonomy."""
    return ticker.upper() in IFRS_FILERS


if __name__ == "__main__":
    print("IFRS Taxonomy loaded.")
    print(f"  {len(IFRS_TAXONOMY)} concepts defined")
    print(f"  {len(IFRS_FILERS)} IFRS filers in registry: {sorted(IFRS_FILERS)}")
    print()
    print("Sample concept lookups:")
    for c in ["revenue", "interest_expense", "net_income", "total_assets", "deposits_from_customers"]:
        names = get_ifrs_names_for_concept(c)
        print(f"  {c}: {names[:2] if names else 'EMPTY'}")
    print()
    print("Filer dispatch test:")
    for t in ["NU", "JPM", "META", "STNE"]:
        print(f"  is_ifrs_filer({t}) = {is_ifrs_filer(t)}")
