"""
Banking Collector — Recolecta financials de bancos desde SEC EDGAR y los
persiste en la DB (data/macro.db), tabla banking_financials.

Gemelo estructural de og_collector.py. A diferencia de og (que recolecta
precios diarios via yfinance/EIA), banking recolecta fundamentals
trimestrales/anuales via SEC EDGAR (financials_extractor_v2).

Flujo por banco:
1. extraer_financials_v2(ticker, fiscal_year) -> 6 conceptos crudos + quality
2. calcular las 3 metricas derivadas (loan_to_deposit, cost_of_risk,
   efficiency_ratio) con calculated_metrics
3. guardar todo (crudos + metricas) en banking_financials (long format)

Long format: una fila por (ticker, fiscal_year, concept). Agregar un
concepto nuevo (ej. ROTCE cuando exista el parser de 10-K) = insertar
filas, sin ALTER TABLE.

Universo: 7 bancos (JPM, BAC, WFC, C, GS, MS, NU). Ver sector_mappings/banking.py.
"""

import sqlite3
from datetime import date, datetime
from pathlib import Path

DB_PATH = "data/macro.db"

# Conceptos crudos que extraemos de SEC (los 6 verificados en Phase 2)
CONCEPTOS_BANCA = [
    "net_interest_income",
    "deposits",
    "loans_held_for_investment",
    "provision_for_credit_losses",
    "noninterest_income",
    "noninterest_expense",
]


# ----------------- DB helpers -----------------
def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Crea la conexion y la tabla banking_financials si no existe."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS banking_financials (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT NOT NULL,
            subtype         TEXT NOT NULL,
            fiscal_year     INTEGER NOT NULL,
            concept         TEXT NOT NULL,
            value           REAL,
            quality         TEXT NOT NULL,
            fecha_descarga  TEXT NOT NULL,
            UNIQUE(ticker, fiscal_year, concept)
        )
    """)
    conn.commit()
    return conn


def guardar_concepto(conn, ticker, subtype, fiscal_year, concept, value, quality):
    """INSERT OR REPLACE de una fila (idempotente, como og_collector)."""
    conn.execute("""
        INSERT OR REPLACE INTO banking_financials
        (ticker, subtype, fiscal_year, concept, value, quality, fecha_descarga)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (ticker, subtype, fiscal_year, concept, value, quality,
          datetime.now().isoformat()))


# ----------------- Recoleccion -----------------
def recolectar_banco(conn, ticker: str, fiscal_year: int) -> dict:
    """
    Recolecta un banco: extrae crudos, calcula metricas, guarda todo.
    Devuelve un resumen {recolectados, not_found, metricas_calculadas}.
    """
    from financials_extractor_v2 import extraer_financials_v2
    from calculated_metrics import (
        calcular_loan_to_deposit,
        calcular_cost_of_risk,
        calcular_efficiency_ratio,
    )
    from sector_mappings.banking import get_banking_subtype

    subtype = get_banking_subtype(ticker) or "unknown"
    fin = extraer_financials_v2(ticker, fiscal_year)

    resumen = {"ticker": ticker, "recolectados": 0, "not_found": 0,
               "metricas": 0, "error": None}

    if "error" in fin:
        resumen["error"] = fin["error"]
        return resumen

    # 1) Guardar los 6 conceptos crudos
    valores = {}  # para reusar en las metricas
    for concepto in CONCEPTOS_BANCA:
        valor = fin.get(concepto)
        quality = fin.get(f"{concepto}_quality", "not_found")
        guardar_concepto(conn, ticker, subtype, fiscal_year, concepto, valor, quality)
        valores[concepto] = valor
        if valor is not None:
            resumen["recolectados"] += 1
        else:
            resumen["not_found"] += 1

    # 2) Calcular y guardar las 3 metricas derivadas
    metricas = {
        "loan_to_deposit": calcular_loan_to_deposit(
            valores["loans_held_for_investment"], valores["deposits"]),
        "cost_of_risk": calcular_cost_of_risk(
            valores["provision_for_credit_losses"], valores["loans_held_for_investment"]),
        "efficiency_ratio": calcular_efficiency_ratio(
            valores["noninterest_expense"], valores["net_interest_income"],
            valores["noninterest_income"]),
    }
    for nombre, res in metricas.items():
        guardar_concepto(conn, ticker, subtype, fiscal_year, nombre,
                         res["value"], res["quality"])
        if res["value"] is not None:
            resumen["metricas"] += 1

    conn.commit()
    return resumen


def recolectar_todos(fiscal_year: int, db_path: str = DB_PATH):
    """Recolecta los 7 bancos del universo."""
    from sector_mappings.banking import BANKING_TICKERS

    conn = init_db(db_path)
    print(f"Recolectando banking_financials FY{fiscal_year} ({len(BANKING_TICKERS)} bancos)...")
    print("=" * 60)
    for ticker in sorted(BANKING_TICKERS):
        r = recolectar_banco(conn, ticker, fiscal_year)
        if r["error"]:
            print(f"  {ticker:5s} ERROR: {r['error']}")
        else:
            print(f"  {ticker:5s} crudos={r['recolectados']}/6  "
                  f"not_found={r['not_found']}  metricas={r['metricas']}/3")
    conn.close()
    print("=" * 60)
    print("Listo. Datos en banking_financials.")


# ----------------- Entry point -----------------
if __name__ == "__main__":
    import sys
    fy = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    recolectar_todos(fy)
