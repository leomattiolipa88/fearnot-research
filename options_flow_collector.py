"""
FearNot - Options Flow Collector

Modulo separado que recolecta 4 indicadores de options flow:
1. VIX IV Percentile (1-year) - donde esta el VIX en su rango anual
2. Put/Call Ratio CBOE          - sentiment indicator clasico
3. VIX vs RVX skew              - stress en small caps vs large caps
4. Term structure expandida     - VIX9D y VIX6M

Todo gratis via yfinance.
Se corre DESPUES de technical_collector.py.
Usa la misma DB pero su propia tabla.
"""

import sqlite3
import yfinance as yf
import logging
from datetime import date, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

DB_PATH = "data/macro.db"


def init_options_flow_table(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Crea la tabla de options flow si no existe."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS indicadores_options_flow (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT NOT NULL UNIQUE,
            vix_9d          REAL,
            vix_6m          REAL,
            vix_iv_pct      REAL,
            put_call_ratio  REAL,
            vix_rvx_skew    REAL,
            interpretacion  TEXT
        )
    """)
    conn.commit()
    return conn


def calcular_vix_term_expandida() -> dict:
    """VIX 9D y VIX 6M - completar la curva de term structure."""
    resultado = {"vix_9d": None, "vix_6m": None}

    for nombre, ticker in [("vix_9d", "^VIX9D"), ("vix_6m", "^VIX6M")]:
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if not hist.empty:
                resultado[nombre] = float(hist["Close"].iloc[-1])
        except Exception as e:
            log.warning(f"Error obteniendo {ticker}: {e}")

    return resultado


def calcular_vix_iv_percentile() -> float | None:
    """
    VIX IV Percentile (1-year).
    Devuelve donde esta el VIX hoy en su distribucion del ultimo año.
    - 0-30: VIX historicamente bajo (complacencia)
    - 30-70: VIX en zona normal
    - 70-100: VIX historicamente alto (fear)
    """
    try:
        vix_hist = yf.Ticker("^VIX").history(period="1y")
        if vix_hist.empty or len(vix_hist) < 200:
            return None

        vix_actual = float(vix_hist["Close"].iloc[-1])
        vix_pasado = vix_hist["Close"].iloc[:-1]
        percentil = (vix_pasado < vix_actual).sum() / len(vix_pasado) * 100
        return round(float(percentil), 1)
    except Exception as e:
        log.warning(f"Error calculando VIX IV percentile: {e}")
        return None


def calcular_put_call_ratio() -> float | None:
    """
    Put/Call Ratio del CBOE.
    - >1.0: bearish sentiment (mas puts que calls)
    - 0.7-1.0: neutral
    - <0.7: bullish sentiment (mas calls que puts)
    Extremos en cualquier direccion suelen marcar reversals.
    """
    try:
        cpc_hist = yf.Ticker("^CPC").history(period="5d")
        if cpc_hist.empty:
            return None
        return round(float(cpc_hist["Close"].iloc[-1]), 3)
    except Exception as e:
        log.warning(f"Error obteniendo Put/Call Ratio: {e}")
        return None


def calcular_vix_rvx_skew() -> float | None:
    """
    VIX vs RVX skew (small caps stress).
    RVX = volatility implícita del Russell 2000 (small caps).
    - <1.2: stress similar en small caps y large caps
    - 1.2-1.4: leve stress en small caps
    - >1.4: stress notable en small caps (señal adelantada de risk-off)
    """
    try:
        rvx_hist = yf.Ticker("^RVX").history(period="5d")
        vix_hist = yf.Ticker("^VIX").history(period="5d")
        if rvx_hist.empty or vix_hist.empty:
            return None

        rvx = float(rvx_hist["Close"].iloc[-1])
        vix = float(vix_hist["Close"].iloc[-1])
        if vix <= 0:
            return None
        return round(rvx / vix, 3)
    except Exception as e:
        log.warning(f"Error calculando VIX/RVX skew: {e}")
        return None


def interpretar_options_flow(datos: dict) -> str:
    """Genera una interpretacion textual de los indicadores."""
    interpretaciones = []

    iv_pct = datos.get("vix_iv_pct")
    if iv_pct is not None:
        if iv_pct < 30:
            interpretaciones.append(f"VIX en percentil {iv_pct} (bajo, posible complacencia)")
        elif iv_pct > 70:
            interpretaciones.append(f"VIX en percentil {iv_pct} (alto, fear elevado)")
        else:
            interpretaciones.append(f"VIX en percentil {iv_pct} (zona normal)")

    pc = datos.get("put_call_ratio")
    if pc is not None:
        if pc > 1.0:
            interpretaciones.append(f"P/C ratio {pc} (bearish sentiment)")
        elif pc < 0.7:
            interpretaciones.append(f"P/C ratio {pc} (bullish sentiment)")
        else:
            interpretaciones.append(f"P/C ratio {pc} (neutral)")

    skew = datos.get("vix_rvx_skew")
    if skew is not None:
        if skew > 1.4:
            interpretaciones.append(f"RVX/VIX {skew} (stress en small caps)")
        elif skew < 1.2:
            interpretaciones.append(f"RVX/VIX {skew} (stress balanceado)")
        else:
            interpretaciones.append(f"RVX/VIX {skew} (leve stress small caps)")

    return " | ".join(interpretaciones) if interpretaciones else "Sin data suficiente"


def main():
    print("=" * 60)
    print(f"Options Flow Collector - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    print("\n[1/4] VIX term structure expandida (VIX9D, VIX6M)...")
    term_expandida = calcular_vix_term_expandida()
    print(f"      VIX 9D: {term_expandida['vix_9d']}")
    print(f"      VIX 6M: {term_expandida['vix_6m']}")

    print("\n[2/4] VIX IV Percentile (1-year)...")
    iv_pct = calcular_vix_iv_percentile()
    print(f"      Percentil: {iv_pct}")

    # Put/Call y RVX no disponibles en yfinance
    pc_ratio = None
    skew = None

    # Guardar en DB
    datos = {
        "vix_9d": term_expandida["vix_9d"],
        "vix_6m": term_expandida["vix_6m"],
        "vix_iv_pct": iv_pct,
        "put_call_ratio": pc_ratio,
        "vix_rvx_skew": skew,
    }
    interpretacion = interpretar_options_flow(datos)

    conn = init_options_flow_table()
    fecha_hoy = date.today().isoformat()

    conn.execute("""
        INSERT OR REPLACE INTO indicadores_options_flow
        (fecha, vix_9d, vix_6m, vix_iv_pct, put_call_ratio,
         vix_rvx_skew, interpretacion)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        fecha_hoy,
        datos["vix_9d"],
        datos["vix_6m"],
        datos["vix_iv_pct"],
        datos["put_call_ratio"],
        datos["vix_rvx_skew"],
        interpretacion,
    ))
    conn.commit()
    conn.close()

    print(f"\n{interpretacion}")
    print("\n" + "=" * 60)
    print("Recoleccion completa")
    print("=" * 60)


if __name__ == "__main__":
    main()
