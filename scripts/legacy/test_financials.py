"""
Test exploratorio v2: ver datos de Exxon de manera legible.
"""

import yfinance as yf

xom = yf.Ticker("XOM")
income = xom.income_stmt

# Lista de items que nos importan (filtramos el ruido)
items_clave = [
    "Total Revenue",
    "Cost Of Revenue",
    "Gross Profit",
    "Operating Expense",
    "Operating Income",
    "Net Income",
    "Diluted EPS",
    "Diluted Average Shares",
    "EBITDA",
    "EBIT",
    "Interest Expense",
    "Reconciled Depreciation",
]

print("=" * 80)
print("INCOME STATEMENT - EXXON MOBIL (XOM)")
print("=" * 80)
print(f"\n{'Item':<35} {'2025':>15} {'2024':>15} {'2023':>15}")
print("-" * 80)

for item in items_clave:
    if item in income.index:
        # Tomar los 3 años más recientes
        valores = income.loc[item].head(3)
        # Formatear: si es EPS o ratio, mostrar como número normal
        # Si es valor grande, mostrar en miles de millones
        formatted = []
        for v in valores:
            if "EPS" in item:
                formatted.append(f"${v:.2f}" if v == v else "N/A")  # v==v chequea NaN
            elif "Shares" in item:
                formatted.append(f"{v/1e9:.2f}B" if v == v else "N/A")
            else:
                formatted.append(f"${v/1e9:.1f}B" if v == v else "N/A")
        print(f"{item:<35} {formatted[0]:>15} {formatted[1]:>15} {formatted[2]:>15}")
    else:
        print(f"{item:<35} {'NO DISPONIBLE':>47}")

print()
# Balance Sheet
print("\n" + "=" * 80)
print("BALANCE SHEET - EXXON MOBIL (XOM)")
print("=" * 80)

balance = xom.balance_sheet
items_balance = [
    "Total Assets",
    "Current Assets",
    "Cash And Cash Equivalents",
    "Inventory",
    "Total Liabilities Net Minority Interest",
    "Current Liabilities",
    "Long Term Debt",
    "Total Debt",
    "Stockholders Equity",
]

print(f"\n{'Item':<45} {'2025':>15} {'2024':>15} {'2023':>15}")
print("-" * 90)

for item in items_balance:
    if item in balance.index:
        valores = balance.loc[item].head(3)
        formatted = [f"${v/1e9:.1f}B" if v == v else "N/A" for v in valores]
        print(f"{item:<45} {formatted[0]:>15} {formatted[1]:>15} {formatted[2]:>15}")
    else:
        print(f"{item:<45} {'NO DISPONIBLE':>47}")


# Cash Flow Statement
print("\n" + "=" * 80)
print("CASH FLOW STATEMENT - EXXON MOBIL (XOM)")
print("=" * 80)

cashflow = xom.cashflow
items_cashflow = [
    "Operating Cash Flow",
    "Capital Expenditure",
    "Free Cash Flow",
    "Net Income From Continuing Operations",
    "Depreciation And Amortization",
    "Cash Dividends Paid",
    "Repurchase Of Capital Stock",
]

print(f"\n{'Item':<45} {'2025':>15} {'2024':>15} {'2023':>15}")
print("-" * 90)

for item in items_cashflow:
    if item in cashflow.index:
        valores = cashflow.loc[item].head(3)
        formatted = [f"${v/1e9:.1f}B" if v == v else "N/A" for v in valores]
        print(f"{item:<45} {formatted[0]:>15} {formatted[1]:>15} {formatted[2]:>15}")
    else:
        print(f"{item:<45} {'NO DISPONIBLE':>47}")
