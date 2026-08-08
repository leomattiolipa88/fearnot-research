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
from datetime import date, datetime
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

# Probe-and-fallback: NII es el bellwether porque los 7 bancos lo reportan
# (universal + investment). Umbral 4/7 = mayoría — evita que 1-2 rezagados
# congelen el ancla.
BELLWETHER_PROBE = "net_interest_income"
COBERTURA_MINIMA_PROBE = 4


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


# ----------------- Probe-and-fallback del ancla trimestral -----------------

def _ultimo_trimestre_completo_calendario() -> tuple[int, int]:
    """Último trimestre calendario que YA CERRÓ, sin colchón de presentación.
    Distinto de config.trimestre_actual() que resta 45 días: este es el punto
    de partida del probe — le preguntamos a SEC si el frame más nuevo trae
    data, y bajamos si no."""
    today = date.today()
    q = (today.month - 1) // 3 + 1
    fin_dia = 31 if q in (1, 4) else 30
    fin_q = date(today.year, q * 3, fin_dia)
    if today >= fin_q:
        return (today.year, q)
    if q == 1:
        return (today.year - 1, 4)
    return (today.year, q - 1)


def _sondear_cobertura(anio: int, quarter: int) -> int:
    """Cuenta cuántos de los 7 bancos tienen fact del BELLWETHER (NII) en
    el frame CY{anio}Q{quarter}. Reusa la maquinaria de frames de
    financials_extractor_v2 + las mismas tablas GAAP/IFRS que la recolección."""
    from financials_extractor_v2 import (
        obtener_cik, obtener_facts, extraer_fact_trimestral_auto,
    )
    from sector_router import get_names_for_concept
    from ifrs_taxonomy import is_ifrs_filer, get_ifrs_names_for_concept
    from sector_mappings.banking import BANKING_TICKERS

    hits = 0
    for ticker in sorted(BANKING_TICKERS):
        cik = obtener_cik(ticker)
        if cik is None:
            continue
        facts = obtener_facts(cik)
        if facts is None:
            continue
        if is_ifrs_filer(ticker):
            names = get_ifrs_names_for_concept(BELLWETHER_PROBE)
            taxonomia = "ifrs-full"
        else:
            names = get_names_for_concept(BELLWETHER_PROBE, ticker)
            taxonomia = "us-gaap"
        if not names:
            continue
        val, _ = extraer_fact_trimestral_auto(facts, names, anio, quarter, taxonomia)
        if val is not None:
            hits += 1
    return hits


def resolver_ancla_trimestral() -> tuple[int, int]:
    """Sondea el frame más nuevo en SEC y decide el ancla por cobertura real.
    Si el probe falla entero (SEC caída, imports rotos), cae al cálculo
    calendario de config.trimestre_actual() como red de seguridad."""
    try:
        anio, q = _ultimo_trimestre_completo_calendario()
        hits = _sondear_cobertura(anio, q)
        if hits >= COBERTURA_MINIMA_PROBE:
            print(f"Probe CY{anio}Q{q}: {hits}/7 bancos → ancla CY{anio}Q{q}")
            return anio, q
        prev_q = q - 1
        prev_a = anio
        if prev_q == 0:
            prev_q = 4
            prev_a = anio - 1
        hits_prev = _sondear_cobertura(prev_a, prev_q)
        print(
            f"Probe CY{anio}Q{q}: {hits}/7 (<{COBERTURA_MINIMA_PROBE}) → "
            f"fallback CY{prev_a}Q{prev_q}: {hits_prev}/7 → ancla CY{prev_a}Q{prev_q}"
        )
        return prev_a, prev_q
    except Exception as e:
        anio, q = trimestre_actual()
        print(f"Probe fallo ({e}); cae a config.trimestre_actual() = CY{anio}Q{q}")
        return anio, q


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        # Override manual (análisis histórico): requiere anio + quarter juntos.
        anio = int(sys.argv[1])
        q = int(sys.argv[2])
    else:
        anio, q = resolver_ancla_trimestral()
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    recolectar_todos_q(anio, q, n)
