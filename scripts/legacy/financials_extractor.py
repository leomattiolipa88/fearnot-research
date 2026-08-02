"""
FearNot - Financial Statements Extractor

Extrae financial statements (income, balance, cashflow) de cualquier ticker
publico y calcula 16 metricas fundamentales en 5 categorias:
- Profitability (4): Op Margin, Net Margin, ROE, ROIC
- Growth (3): Revenue, NI, FCF YoY
- Leverage (4): D/E, Interest Coverage, Current Ratio, Net Debt/EBITDA
- Quality (3): FCF/NI, CapEx/Depreciation, Asset Turnover
- Valuation (3): P/E, EV/EBITDA, FCF Yield

Universal: funciona para cualquier ticker (no asume sector).
Opcionalmente lee my_portfolio.json para mostrar tu posicion personal.

Uso:
    python3 financials_extractor.py AAPL
    python3 financials_extractor.py PENG MELI NU
    python3 financials_extractor.py portfolio  # lee my_portfolio.json
"""

import sys
import json
import sqlite3
import yfinance as yf
from pathlib import Path
from datetime import datetime
from typing import Optional


DB_PATH = "data/macro.db"
PORTFOLIO_PATH = "my_portfolio.json"


# ============================================================
# 1. SETUP DE DB
# ============================================================
def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Crea la tabla financials si no existe."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS financials (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker            TEXT NOT NULL,
            fecha             TEXT NOT NULL,
            company_name      TEXT,
            sector            TEXT,
            -- Raw numbers (los basicos)
            revenue           REAL,
            net_income        REAL,
            operating_income  REAL,
            ebitda            REAL,
            fcf               REAL,
            total_assets      REAL,
            total_debt        REAL,
            cash              REAL,
            equity            REAL,
            market_cap        REAL,
            -- Metricas
            operating_margin  REAL,
            net_margin        REAL,
            roe               REAL,
            roic              REAL,
            revenue_growth    REAL,
            ni_growth         REAL,
            fcf_growth        REAL,
            debt_to_equity    REAL,
            interest_coverage REAL,
            current_ratio     REAL,
            net_debt_ebitda   REAL,
            fcf_to_ni         REAL,
            capex_to_depr     REAL,
            asset_turnover    REAL,
            pe_ratio          REAL,
            ev_to_ebitda      REAL,
            fcf_yield         REAL,
            UNIQUE(ticker, fecha)
        )
    """)
    conn.commit()
    return conn


# ============================================================
# 2. HELPERS
# ============================================================
def obtener_valor(df, posibles_nombres: list, columna_idx: int = 0):
    """
    Busca un valor en un DataFrame probando multiples nombres posibles.
    yfinance a veces nombra las cosas distinto, esto da resiliencia.

    Args:
        df: DataFrame de yfinance (income_stmt, balance_sheet, cashflow)
        posibles_nombres: lista de nombres que podrian matchear
        columna_idx: 0 = año mas reciente, 1 = año anterior, etc.

    Returns:
        float o None si no encuentra nada
    """
    if df is None or df.empty:
        return None

    for nombre in posibles_nombres:
        if nombre in df.index:
            try:
                valor = df.loc[nombre].iloc[columna_idx]
                # Filtrar NaN
                if valor == valor:  # NaN != NaN en Python
                    return float(valor)
            except (IndexError, KeyError):
                continue
    return None


def calcular_growth(actual, anterior):
    """Calcula crecimiento YoY como decimal (0.10 = 10%)."""
    if actual is None or anterior is None or anterior == 0:
        return None
    return (actual - anterior) / abs(anterior)


def cargar_portfolio() -> dict:
    """Lee my_portfolio.json si existe."""
    try:
        with open(PORTFOLIO_PATH) as f:
            return json.load(f).get("positions", {})
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"   Aviso: error leyendo portfolio: {e}")
        return {}


# ============================================================
# 3. EXTRACTOR PRINCIPAL
# ============================================================
def extraer_financials(ticker: str) -> Optional[dict]:
    """
    Extrae financial statements y calcula 16 metricas para un ticker.

    Returns:
        dict con todos los numeros y metricas, o None si falla.
    """
    print(f"\n[{ticker}] Descargando datos...")

    try:
        t = yf.Ticker(ticker)
        income = t.income_stmt
        balance = t.balance_sheet
        cashflow = t.cashflow
        info = t.info
    except Exception as e:
        print(f"   ERROR: no se pudo descargar {ticker}: {e}")
        return None

    # Si el ticker no tiene datos (ej: ETF, ticker invalido), abortar
    if income is None or income.empty:
        print(f"   ERROR: {ticker} no tiene income statement (puede ser ETF o invalido)")
        return None

    # ---------- RAW NUMBERS ----------
    # Income statement (año actual y previo para growth)
    revenue = obtener_valor(income, ["Total Revenue", "Operating Revenue"])
    revenue_prev = obtener_valor(income, ["Total Revenue", "Operating Revenue"], 1)
    operating_income = obtener_valor(income, ["Operating Income"])
    net_income = obtener_valor(income, ["Net Income", "Net Income Common Stockholders"])
    net_income_prev = obtener_valor(income, ["Net Income", "Net Income Common Stockholders"], 1)
    depreciation = obtener_valor(income, ["Reconciled Depreciation", "Depreciation"])
    interest_expense = obtener_valor(income, ["Interest Expense"])
    pretax_income = obtener_valor(income, ["Pretax Income"])
    tax_expense = obtener_valor(income, ["Tax Provision", "Income Tax Expense"])

    # EBITDA: calculamos desde piezas (mas transparente que el EBITDA de yfinance)
    ebitda = None
    if operating_income is not None and depreciation is not None:
        ebitda = operating_income + depreciation

    # Balance sheet
    total_assets = obtener_valor(balance, ["Total Assets"])
    current_assets = obtener_valor(balance, ["Current Assets"])
    current_liabilities = obtener_valor(balance, ["Current Liabilities"])
    total_debt = obtener_valor(balance, ["Total Debt"])
    cash = obtener_valor(balance, ["Cash And Cash Equivalents", "Cash"])
    equity = obtener_valor(balance, ["Stockholders Equity", "Total Equity Gross Minority Interest"])

    # Cash flow
    operating_cf = obtener_valor(cashflow, ["Operating Cash Flow", "Cash Flow From Operating Activities"])
    capex = obtener_valor(cashflow, ["Capital Expenditure"])
    if capex is not None:
        capex = abs(capex)  # yfinance lo da negativo, lo dejamos positivo

    fcf = obtener_valor(cashflow, ["Free Cash Flow"])
    fcf_prev = obtener_valor(cashflow, ["Free Cash Flow"], 1)

    # Si yfinance no da FCF, calcularlo nosotros
    if fcf is None and operating_cf is not None and capex is not None:
        fcf = operating_cf - capex

    # Market data (real-time desde info)
    market_cap = info.get("marketCap")
    company_name = info.get("longName", ticker)
    sector = info.get("sector", "Unknown")

    # ---------- METRICAS ----------
    metricas = {
        "ticker": ticker,
        "company_name": company_name,
        "sector": sector,
        "fecha": datetime.now().strftime("%Y-%m-%d"),

        # Raw numbers (en miles de millones para display)
        "revenue": revenue,
        "net_income": net_income,
        "operating_income": operating_income,
        "ebitda": ebitda,
        "fcf": fcf,
        "total_assets": total_assets,
        "total_debt": total_debt,
        "cash": cash,
        "equity": equity,
        "market_cap": market_cap,
    }

    # PROFITABILITY
    metricas["operating_margin"] = (operating_income / revenue) if (operating_income and revenue) else None
    metricas["net_margin"] = (net_income / revenue) if (net_income and revenue) else None
    metricas["roe"] = (net_income / equity) if (net_income and equity) else None

    # ROIC = NOPAT / Invested Capital
    # NOPAT = Operating Income * (1 - tax_rate)
    roic = None
    if operating_income and pretax_income and tax_expense and total_debt is not None and equity and cash is not None:
        tax_rate = tax_expense / pretax_income if pretax_income else 0.21
        nopat = operating_income * (1 - tax_rate)
        invested_capital = total_debt + equity - cash
        if invested_capital > 0:
            roic = nopat / invested_capital
    metricas["roic"] = roic

    # GROWTH
    metricas["revenue_growth"] = calcular_growth(revenue, revenue_prev)
    metricas["ni_growth"] = calcular_growth(net_income, net_income_prev)
    metricas["fcf_growth"] = calcular_growth(fcf, fcf_prev)

    # LEVERAGE
    metricas["debt_to_equity"] = (total_debt / equity) if (total_debt and equity) else None
    metricas["interest_coverage"] = (operating_income / interest_expense) if (operating_income and interest_expense) else None
    metricas["current_ratio"] = (current_assets / current_liabilities) if (current_assets and current_liabilities) else None
    metricas["net_debt_ebitda"] = ((total_debt - (cash or 0)) / ebitda) if (total_debt and ebitda and ebitda > 0) else None

    # QUALITY
    metricas["fcf_to_ni"] = (fcf / net_income) if (fcf and net_income) else None
    metricas["capex_to_depr"] = (capex / depreciation) if (capex and depreciation) else None
    metricas["asset_turnover"] = (revenue / total_assets) if (revenue and total_assets) else None

    # VALUATION
    metricas["pe_ratio"] = (market_cap / net_income) if (market_cap and net_income) else None
    ev = (market_cap + (total_debt or 0) - (cash or 0)) if market_cap else None
    metricas["ev_to_ebitda"] = (ev / ebitda) if (ev and ebitda and ebitda > 0) else None
    metricas["fcf_yield"] = (fcf / market_cap) if (fcf and market_cap) else None

    return metricas


# ============================================================
# 4. FORMATEO Y DISPLAY
# ============================================================
def fmt_dollars(value, billions=True):
    """Formatea un numero como dolares en billions."""
    if value is None:
        return "N/A"
    if billions:
        return f"${value/1e9:.1f}B"
    return f"${value:,.0f}"


def fmt_pct(value, decimals=1):
    """Formatea como porcentaje."""
    if value is None:
        return "N/A"
    return f"{value*100:.{decimals}f}%"


def fmt_ratio(value, decimals=2):
    """Formatea como ratio numerico."""
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}x"


def imprimir_resultado(metricas: dict, portfolio: dict = None):
    """Imprime el output formateado de una empresa."""
    if metricas is None:
        return

    ticker = metricas["ticker"]
    print()
    print("=" * 70)
    print(f"  {ticker} - {metricas['company_name']}")
    print(f"  Sector: {metricas['sector']}")
    print("=" * 70)

    # Si esta en el portfolio, mostrar tu posicion
    if portfolio and ticker in portfolio:
        pos = portfolio[ticker]
        shares = pos["shares"]
        avg_cost = pos["avg_cost"]
        invested = shares * avg_cost
        # Precio actual desde info
        try:
            current_price = yf.Ticker(ticker).info.get("currentPrice") or yf.Ticker(ticker).info.get("regularMarketPrice")
            if current_price:
                actual_value = shares * current_price
                pl = actual_value - invested
                pl_pct = (pl / invested) * 100
                print(f"\n  TU POSICION: {shares} shares @ ${avg_cost:.2f}")
                print(f"     Invertido: ${invested:.2f} | Actual: ${actual_value:.2f}")
                print(f"     P&L: ${pl:+.2f} ({pl_pct:+.1f}%)")
        except Exception:
            pass

    # Raw numbers
    print(f"\n  REVENUE:    {fmt_dollars(metricas['revenue'])}")
    print(f"  NET INCOME: {fmt_dollars(metricas['net_income'])}")
    print(f"  FCF:        {fmt_dollars(metricas['fcf'])}")
    print(f"  TOTAL DEBT: {fmt_dollars(metricas['total_debt'])}")
    print(f"  MARKET CAP: {fmt_dollars(metricas['market_cap'])}")

    # Profitability
    print(f"\n  PROFITABILITY:")
    print(f"     Op Margin:  {fmt_pct(metricas['operating_margin'])}")
    print(f"     Net Margin: {fmt_pct(metricas['net_margin'])}")
    print(f"     ROE:        {fmt_pct(metricas['roe'])}")
    print(f"     ROIC:       {fmt_pct(metricas['roic'])}")

    # Growth
    print(f"\n  GROWTH (YoY):")
    print(f"     Revenue:    {fmt_pct(metricas['revenue_growth'])}")
    print(f"     Net Income: {fmt_pct(metricas['ni_growth'])}")
    print(f"     FCF:        {fmt_pct(metricas['fcf_growth'])}")

    # Leverage
    print(f"\n  LEVERAGE:")
    print(f"     Debt/Equity:      {fmt_ratio(metricas['debt_to_equity'])}")
    print(f"     Interest Coverage:{fmt_ratio(metricas['interest_coverage'])}")
    print(f"     Current Ratio:    {fmt_ratio(metricas['current_ratio'])}")
    print(f"     Net Debt/EBITDA:  {fmt_ratio(metricas['net_debt_ebitda'])}")

    # Quality
    print(f"\n  QUALITY:")
    print(f"     FCF/Net Income:   {fmt_ratio(metricas['fcf_to_ni'])}")
    print(f"     CapEx/Depr:       {fmt_ratio(metricas['capex_to_depr'])}")
    print(f"     Asset Turnover:   {fmt_ratio(metricas['asset_turnover'])}")

    # Valuation
    print(f"\n  VALUATION:")
    print(f"     P/E Ratio:        {fmt_ratio(metricas['pe_ratio'])}")
    print(f"     EV/EBITDA:        {fmt_ratio(metricas['ev_to_ebitda'])}")
    print(f"     FCF Yield:        {fmt_pct(metricas['fcf_yield'])}")


# ============================================================
# 5. GUARDAR EN DB
# ============================================================
def guardar_en_db(metricas: dict):
    """Guarda las metricas en la tabla financials."""
    if metricas is None:
        return

    conn = init_db()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO financials VALUES (
                NULL,
                :ticker, :fecha, :company_name, :sector,
                :revenue, :net_income, :operating_income, :ebitda, :fcf,
                :total_assets, :total_debt, :cash, :equity, :market_cap,
                :operating_margin, :net_margin, :roe, :roic,
                :revenue_growth, :ni_growth, :fcf_growth,
                :debt_to_equity, :interest_coverage, :current_ratio, :net_debt_ebitda,
                :fcf_to_ni, :capex_to_depr, :asset_turnover,
                :pe_ratio, :ev_to_ebitda, :fcf_yield
            )
        """, metricas)
        conn.commit()
    except Exception as e:
        print(f"   Error guardando en DB: {e}")
    finally:
        conn.close()


# ============================================================
# 6. RUNNER
# ============================================================
def correr_analisis(tickers: list):
    """Ejecuta el extractor para una lista de tickers."""
    portfolio = cargar_portfolio()

    print("=" * 70)
    print(f"  FINANCIALS EXTRACTOR - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Tickers: {', '.join(tickers)}")
    print("=" * 70)

    resultados = []
    for ticker in tickers:
        metricas = extraer_financials(ticker)
        if metricas:
            imprimir_resultado(metricas, portfolio)
            guardar_en_db(metricas)
            resultados.append(metricas)

    print("\n" + "=" * 70)
    print(f"  Procesados: {len(resultados)}/{len(tickers)} tickers")
    print("=" * 70)
    return resultados


# ============================================================
# 7. MAIN
# ============================================================
if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print("Uso:")
        print("  python3 financials_extractor.py AAPL")
        print("  python3 financials_extractor.py PENG MELI NU")
        print("  python3 financials_extractor.py portfolio")
        sys.exit(1)

    # Caso especial: "portfolio" lee my_portfolio.json
    if args[0].lower() == "portfolio":
        portfolio = cargar_portfolio()
        if not portfolio:
            print("ERROR: my_portfolio.json no encontrado o vacio")
            sys.exit(1)
        tickers = list(portfolio.keys())
    else:
        tickers = [t.upper() for t in args]

    correr_analisis(tickers)
