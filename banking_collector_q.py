"""
Banking Collector Trimestral — Recolecta la SERIE trimestral de los bancos
desde SEC EDGAR y la persiste en data/macro.db, tabla banking_financials_q.

Evolucion del banking_collector.py anual. Diferencias clave:
- Recolecta una SERIE (varios trimestres), no un solo periodo.
- Tabla con columna 'period' (TEXT): "CY2025Q3" trimestral, "FY2024" anual.
  Disenada para que anual y trimestral convivan en la misma tabla.
- Usa extraer_serie_trimestral (con reconstruccion de Q4 para flujos).

Flujo por banco:
1. extraer_serie_trimestral(ticker, conceptos, anio, q, n) -> serie de N trimestres
2. por cada trimestre: calcular las 3 metricas derivadas
3. guardar cada (ticker, period, concept) en banking_financials_q

Universo: 7 bancos. Ver sector_mappings/banking.py.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from config import trimestre_actual

DB_PATH = "data/macro.db"

CONCEPTOS_BANCA = [
    "net_interest_income",
    "deposits",
    "loans_held_for_investment",
    "provision_for_credit_losses",
    "noninterest_income",
    "noninterest_expense",
]


def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Crea la tabla banking_financials_q (trimestral) si no existe."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS banking_financials_q (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT NOT NULL,
            subtype         TEXT NOT NULL,
            period          TEXT NOT NULL,
            anio            INTEGER NOT NULL,
            quarter         INTEGER,
            concept         TEXT NOT NULL,
            value           REAL,
            quality         TEXT NOT NULL,
            metodo          TEXT,
            fecha_descarga  TEXT NOT NULL,
            UNIQUE(ticker, period, concept)
        )
    """)
    conn.commit()
    return conn


def guardar(conn, ticker, subtype, period, anio, quarter, concept, value, quality, metodo):
    conn.execute("""
        INSERT OR REPLACE INTO banking_financials_q
        (ticker, subtype, period, anio, quarter, concept, value, quality, metodo, fecha_descarga)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (ticker, subtype, period, anio, quarter, concept, value, quality, metodo,
          datetime.now().isoformat()))


def recolectar_banco_q(conn, ticker, anio_actual, quarter_actual, n_trimestres=6):
    """Recolecta la serie trimestral de un banco y guarda con metricas por trimestre."""
    from financials_extractor_v2 import extraer_serie_trimestral
    from calculated_metrics import (
        calcular_loan_to_deposit, calcular_cost_of_risk, calcular_efficiency_ratio,
    )
    from sector_mappings.banking import get_banking_subtype

    subtype = get_banking_subtype(ticker) or "unknown"
    serie = extraer_serie_trimestral(
        ticker, CONCEPTOS_BANCA, anio_actual, quarter_actual, n_trimestres
    )
    resumen = {"ticker": ticker, "trimestres": 0, "valores": 0, "metricas": 0, "error": None}

    if "error" in serie:
        resumen["error"] = serie["error"]
        return resumen

    for t in serie["serie"]:
        period = t["frame_label"]  # "CY2025Q3"
        anio, q = t["anio"], t["quarter"]
        vals = {}  # para las metricas
        # Guardar los 6 conceptos crudos
        for concepto in CONCEPTOS_BANCA:
            c = t["concepts"][concepto]
            quality = "direct" if c["metodo"] == "direct" else (
                c["metodo"] if c["value"] is not None else "not_found")
            guardar(conn, ticker, subtype, period, anio, q, concepto,
                    c["value"], quality, c["metodo"])
            vals[concepto] = c["value"]
            if c["value"] is not None:
                resumen["valores"] += 1
        # Calcular y guardar las 3 metricas para este trimestre
        metricas = {
            "loan_to_deposit": calcular_loan_to_deposit(
                vals["loans_held_for_investment"], vals["deposits"]),
            "cost_of_risk": calcular_cost_of_risk(
                vals["provision_for_credit_losses"], vals["loans_held_for_investment"]),
            "efficiency_ratio": calcular_efficiency_ratio(
                vals["noninterest_expense"], vals["net_interest_income"],
                vals["noninterest_income"]),
        }
        for nombre, res in metricas.items():
            guardar(conn, ticker, subtype, period, anio, q, nombre,
                    res["value"], res["quality"], "calculated")
            if res["value"] is not None:
                resumen["metricas"] += 1
        resumen["trimestres"] += 1

    conn.commit()
    return resumen


def recolectar_todos_q(anio_actual, quarter_actual, n_trimestres=6, db_path=DB_PATH):
    from sector_mappings.banking import BANKING_TICKERS
    conn = init_db(db_path)
    print(f"Recolectando serie trimestral (ultimos {n_trimestres}Q desde CY{anio_actual}Q{quarter_actual})...")
    print("=" * 64)
    for ticker in sorted(BANKING_TICKERS):
        r = recolectar_banco_q(conn, ticker, anio_actual, quarter_actual, n_trimestres)
        if r["error"]:
            print(f"  {ticker:5s} ERROR: {r['error']}")
        else:
            print(f"  {ticker:5s} trimestres={r['trimestres']}  "
                  f"valores={r['valores']}  metricas={r['metricas']}")
    conn.close()
    print("=" * 64)
    print("Listo. Serie en banking_financials_q.")


if __name__ == "__main__":
    import sys
    anio_default, q_default = trimestre_actual()
    anio = int(sys.argv[1]) if len(sys.argv) > 1 else anio_default
    q = int(sys.argv[2]) if len(sys.argv) > 2 else q_default
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    recolectar_todos_q(anio, q, n)
