"""
Calculated Metrics — Calculos derivados de facts SEC EDGAR.
============================================================

Algunas metricas no estan directas en XBRL y hay que calcularlas
desde otros facts. Este modulo centraliza esos calculos.

Tipos:
- Reconstrucciones: cuando un fact existe en el 10-K pero no en
  companyfacts (ej: shares diluted en XOM).
- Sector-specific: cuando una metrica requiere componentes
  sector-dependent (ej: operating income para integrated oil).

Cada funcion devuelve un dict con value + quality flag:
    {"value": float, "quality": "calculated_from_X_and_Y"}
"""

from typing import Optional


def calcular_shares_diluted(net_income: Optional[float], eps_diluted: Optional[float]) -> dict:
    """
    Calcula shares diluidas weighted-average desde NetIncome / EPS.

    Aplicacion: empresas como XOM que no reportan
    WeightedAverageNumberOfDilutedSharesOutstanding directo en XBRL,
    pero si reportan NetIncomeLoss y EarningsPerShareDiluted.

    Math: EPS = NI / Shares  =>  Shares = NI / EPS

    Args:
        net_income: NetIncomeLoss en USD (ej: 33_680_000_000)
        eps_diluted: EarningsPerShareDiluted en USD/share (ej: 7.84)

    Returns:
        dict con value (en shares, float) y quality flag.
        value = None si los inputs no permiten calculo.
    """
    if net_income is None or eps_diluted is None:
        return {"value": None, "quality": "missing_inputs"}

    if eps_diluted == 0:
        return {"value": None, "quality": "eps_is_zero"}

    shares = net_income / eps_diluted
    return {
        "value": shares,
        "quality": "calculated_from_ni_and_eps"
    }


if __name__ == "__main__":
    # Test con datos reales de XOM 2024
    print("Test calcular_shares_diluted con datos XOM 2024:")
    result = calcular_shares_diluted(
        net_income=33_680_000_000,  # $33.68B
        eps_diluted=7.84
    )
    print(f"  Resultado: {result['value']/1e9:.3f}B shares")
    print(f"  Quality: {result['quality']}")
    print(f"  Esperado (yfinance reporta): ~4.30B shares")


def calcular_operating_income_aproximado(
    income_before_tax: float,
    interest_expense: float,
) -> dict:
    """
    Aproxima Operating Income para empresas que NO exponen sus componentes
    individuales en XBRL (ej: XOM, CVX, OXY).

    Formula: IncomeBeforeTax + InterestExpense

    LIMITACION CONOCIDA: incluye non-operating income (equity affiliates,
    other income) que no se pueden separar via XBRL companyfacts API.
    Para XOM, esto infla Operating Income ~20-25% sobre el valor real.

    Para Operating Income exacto, parsear el 10-K HTML directamente.

    Returns:
        dict con value (USD), quality flag, y bias_warning.
    """
    if income_before_tax is None:
        return {"value": None, "quality": "missing_inputs"}

    interest = interest_expense if interest_expense is not None else 0
    approx = income_before_tax + interest

    return {
        "value": approx,
        "quality": "approximation_with_known_bias",
        "bias_warning": (
            "Inflated by non-operating income (equity affiliates, other income) "
            "not separable from XBRL. Typical bias +15-25% for integrated oil "
            "majors. Use 10-K HTML for exact value."
        )
    }


def calcular_total_liabilities(total_assets: float, stockholders_equity: float) -> dict:
    """
    Calcula Total Liabilities cuando no esta expuesto directo.

    Identidad contable: Total Assets = Total Liabilities + Stockholders Equity
    Por tanto: Total Liabilities = Total Assets - Stockholders Equity

    Aplicacion: empresas como AMZN que exponen LiabilitiesAndStockholdersEquity
    (el agregado) pero no Liabilities como fact independiente.

    Args:
        total_assets: en USD
        stockholders_equity: en USD

    Returns:
        dict con value (USD) y quality flag.
        value = None si los inputs faltan.
    """
    if total_assets is None or stockholders_equity is None:
        return {"value": None, "quality": "missing_inputs"}

    return {
        "value": total_assets - stockholders_equity,
        "quality": "calculated_from_assets_minus_equity"
    }


def calcular_loan_to_deposit(loans_held_for_investment, deposits) -> dict:
    """
    Loan-to-Deposit Ratio = prestamos / depositos.
    Banking-specific. Mide cuanto del funding (depositos) esta prestado.
    WFC/GS no calculable (loans not_found en XBRL, LIMITATIONS #9).
    Args:
        loans_held_for_investment: en USD
        deposits: en USD
    Returns:
        dict con value (ratio) y quality flag. value = None si falta input.
    """
    if loans_held_for_investment is None or deposits is None:
        return {"value": None, "quality": "missing_inputs"}
    if deposits == 0:
        return {"value": None, "quality": "missing_inputs"}
    return {
        "value": loans_held_for_investment / deposits,
        "quality": "calculated_from_loans_and_deposits"
    }


def calcular_cost_of_risk(provision_for_credit_losses, loans_held_for_investment) -> dict:
    """
    Cost of Risk = provisiones / prestamos.
    Banking-specific. Proxy del riesgo crediticio del ciclo de credito.
    Provisiones son forward-looking (CECL), NO charge-offs realizados
    (LIMITATIONS pitfall #1). NU no calculable FY2024 (provisions not_found, #10).
    Args:
        provision_for_credit_losses: en USD
        loans_held_for_investment: en USD
    Returns:
        dict con value (ratio) y quality flag. value = None si falta input.
    """
    if provision_for_credit_losses is None or loans_held_for_investment is None:
        return {"value": None, "quality": "missing_inputs"}
    if loans_held_for_investment == 0:
        return {"value": None, "quality": "missing_inputs"}
    return {
        "value": provision_for_credit_losses / loans_held_for_investment,
        "quality": "calculated_from_provisions_and_loans"
    }


def calcular_loan_to_deposit(loans_held_for_investment, deposits) -> dict:
    """
    Loan-to-Deposit Ratio = prestamos / depositos.
    Banking-specific. Mide cuanto del funding (depositos) esta prestado.
    WFC/GS no calculable (loans not_found en XBRL, LIMITATIONS #9).
    Args:
        loans_held_for_investment: en USD
        deposits: en USD
    Returns:
        dict con value (ratio) y quality flag. value = None si falta input.
    """
    if loans_held_for_investment is None or deposits is None:
        return {"value": None, "quality": "missing_inputs"}
    if deposits == 0:
        return {"value": None, "quality": "missing_inputs"}
    return {
        "value": loans_held_for_investment / deposits,
        "quality": "calculated_from_loans_and_deposits"
    }


def calcular_cost_of_risk(provision_for_credit_losses, loans_held_for_investment) -> dict:
    """
    Cost of Risk = provisiones / prestamos.
    Banking-specific. Proxy del riesgo crediticio del ciclo de credito.
    Provisiones son forward-looking (CECL), NO charge-offs realizados
    (LIMITATIONS pitfall #1). NU no calculable FY2024 (provisions not_found, #10).
    Args:
        provision_for_credit_losses: en USD
        loans_held_for_investment: en USD
    Returns:
        dict con value (ratio) y quality flag. value = None si falta input.
    """
    if provision_for_credit_losses is None or loans_held_for_investment is None:
        return {"value": None, "quality": "missing_inputs"}
    if loans_held_for_investment == 0:
        return {"value": None, "quality": "missing_inputs"}
    return {
        "value": provision_for_credit_losses / loans_held_for_investment,
        "quality": "calculated_from_provisions_and_loans"
    }
