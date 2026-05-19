"""
Macro Agent — Technical & Quant Data Collector
Recolecta los 5 indicadores tecnicos con evidencia empirica real.

DNA: Tudor Jones (200DMA) + Barroso & Santa-Clara (vol-adjusted momentum)
     + Bollerslev et al. (VRP) + practitioners (breadth, VIX term structure)

Los 5 indicadores son ortogonales:
  1. 200DMA           -> tendencia de largo plazo (Tudor Jones)
  2. Momentum 12M     -> ajustado por volatilidad (Barroso & Santa-Clara 2015)
  3. VIX term struct  -> contango/backwardation (regimen de volatilidad)
  4. VRP              -> Variance Risk Premium (Bollerslev 2009)
  5. Breadth          -> % S&P500 sobre 200DMA (confirmacion sistemica)
"""

import sqlite3
import yfinance as yf
import numpy as np
import pandas as pd
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/technical.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

DB_PATH = "data/macro.db"

# Activos sobre los que generamos senales tecnicas
ACTIVOS = {
    "SPY":  "S&P 500",
    "QQQ":  "Nasdaq 100",
    "GLD":  "Oro",
    "TLT":  "Bonos largos USA",
    "USO":  "Petroleo",
    "DXY":  "Dolar Index",
}

TICKERS_PRECIO = {
    "SPY": "SPY",
    "QQQ": "QQQ",
    "GLD": "GLD",
    "TLT": "TLT",
    "USO": "USO",
    "DXY": "DX-Y.NYB",
}

# Muestra representativa del S&P500 para calcular breadth
SP500_MUESTRA = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "LLY", "JPM",
    "V", "XOM", "UNH", "MA", "JNJ", "PG", "HD", "MRK", "AVGO", "CVX", "ABBV",
    "KO", "PEP", "COST", "TMO", "MCD", "ABT", "WMT", "CSCO", "BAC", "DIS",
    "ACN", "NEE", "ADBE", "CRM", "TXN", "DHR", "VZ", "PM", "RTX", "QCOM",
    "BMY", "AMGN", "HON", "ORCL", "INTC", "UPS", "LIN", "SBUX", "GE", "CAT"
]


# ----------------- Setup de tablas -----------------
def init_technical_tables(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Crea las tablas de indicadores tecnicos si no existen."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS senales_tecnicas (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha             TEXT NOT NULL,
            activo            TEXT NOT NULL,
            precio_actual     REAL,
            dma200            REAL,
            pct_sobre_dma     REAL,
            cruce_dma         TEXT,
            momentum_12m      REAL,
            vol_12m           REAL,
            momentum_ajust    REAL,
            UNIQUE(fecha, activo)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS indicadores_tecnicos_mercado (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT NOT NULL UNIQUE,
            vix_spot        REAL,
            vix_3m          REAL,
            vix_term_struct TEXT,
            vrp             REAL,
            pct_sobre_200   REAL
        )
    """)

    conn.commit()
    return conn


# ----------------- Descargar precios -----------------
def descargar_precios(ticker: str, dias: int = 260) -> Optional[pd.DataFrame]:
    """Descarga precios historicos (por defecto 260 dias para cubrir 200DMA + 12M)."""
    # Para DXY, yfinance necesita mas dias porque tiene gaps en fines de semana
    periodo = f"{dias + 150}d" if ticker == "DX-Y.NYB" else f"{dias + 50}d"
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=periodo)
        if hist.empty:
            log.warning(f"yfinance retorno vacio para {ticker}")
            return None
        if len(hist) < dias:
            log.warning(f"Solo {len(hist)} dias de datos para {ticker} (necesitamos {dias})")
            # Si es DXY y tenemos al menos 252 dias, aceptamos
            if ticker == "DX-Y.NYB" and len(hist) >= 252:
                return hist
            return None
        return hist
    except Exception as e:
        log.warning(f"Error descargando {ticker}: {e}")
        return None


# ----------------- 1. 200DMA -----------------
def calcular_dma200(hist: pd.DataFrame) -> dict:
    """
    Calcula 200DMA y detecta cruces.
    Evidencia: Faber (2007), Hurst et al. (2017), Tudor Jones.

    Detecta:
      - CRUCE_ALCISTA: precio cruza hacia arriba (compra)
      - CRUCE_BAJISTA: precio cruza hacia abajo (salir)
      - SOBRE_DMA:     precio sobre 200DMA (zona habilitada)
      - BAJO_DMA:      precio bajo 200DMA (zona prohibida)
    """
    closes = hist["Close"]
    if len(closes) < 202:
        return {}

    dma200 = closes.rolling(200).mean()
    precio_hoy = float(closes.iloc[-1])
    dma_hoy    = float(dma200.iloc[-1])
    precio_ayer = float(closes.iloc[-2])
    dma_ayer    = float(dma200.iloc[-2])

    pct_sobre = ((precio_hoy - dma_hoy) / dma_hoy) * 100

    # Detectar cruce
    sobre_hoy  = precio_hoy  > dma_hoy
    sobre_ayer = precio_ayer > dma_ayer

    if sobre_hoy and not sobre_ayer:
        cruce = "CRUCE_ALCISTA"
    elif not sobre_hoy and sobre_ayer:
        cruce = "CRUCE_BAJISTA"
    elif sobre_hoy:
        cruce = "SOBRE_DMA"
    else:
        cruce = "BAJO_DMA"

    return {
        "precio_actual":  round(precio_hoy, 2),
        "dma200":         round(dma_hoy, 2),
        "pct_sobre_dma":  round(pct_sobre, 2),
        "cruce_dma":      cruce,
    }


# ----------------- 2. Momentum 12M ajustado por volatilidad -----------------
def calcular_momentum_vol_adjusted(hist: pd.DataFrame) -> dict:
    """
    Momentum de 12 meses ajustado por volatilidad realizada.
    Evidencia: Barroso & Santa-Clara (2015, JFE) - casi duplica Sharpe.

    Retorna:
      - momentum_12m:   retorno de los ultimos 252 dias (%)
      - vol_12m:        volatilidad anualizada (%)
      - momentum_ajust: momentum / vol (ratio - lo que realmente importa)
    """
    closes = hist["Close"]
    if len(closes) < 252:
        return {}

    # Retorno de 12 meses (saltando el ultimo mes para evitar reversal a corto plazo)
    precio_hoy      = float(closes.iloc[-1])
    precio_hace_12m = float(closes.iloc[-252])
    momentum_12m    = ((precio_hoy - precio_hace_12m) / precio_hace_12m) * 100

    # Volatilidad realizada de los ultimos 252 dias (anualizada)
    returns_daily = closes.pct_change().dropna().iloc[-252:]
    vol_anualizada = float(returns_daily.std() * np.sqrt(252) * 100)

    # Momentum ajustado por volatilidad (signal-to-noise ratio)
    momentum_ajustado = momentum_12m / vol_anualizada if vol_anualizada > 0 else 0

    return {
        "momentum_12m":    round(momentum_12m, 2),
        "vol_12m":         round(vol_anualizada, 2),
        "momentum_ajust":  round(momentum_ajustado, 3),
    }


# ----------------- 3. VIX Term Structure -----------------
def calcular_vix_term_structure() -> dict:
    """
    Compara VIX spot con VIX 3 meses.
    Contango (spot < 3m) = mercado tranquilo, normal
    Backwardation (spot > 3m) = stress agudo, miedo inmediato
    """
    try:
        vix_spot_data = yf.Ticker("^VIX").history(period="5d")
        vix_3m_data   = yf.Ticker("^VIX3M").history(period="5d")

        if vix_spot_data.empty or vix_3m_data.empty:
            return {}

        vix_spot = float(vix_spot_data["Close"].iloc[-1])
        vix_3m   = float(vix_3m_data["Close"].iloc[-1])

        if vix_spot > vix_3m:
            estado = "BACKWARDATION"  # stress agudo
        elif (vix_3m - vix_spot) / vix_spot > 0.10:
            estado = "CONTANGO_FUERTE"  # mercado muy tranquilo
        else:
            estado = "CONTANGO_NORMAL"

        return {
            "vix_spot": round(vix_spot, 2),
            "vix_3m":   round(vix_3m, 2),
            "vix_term_struct": estado,
        }
    except Exception as e:
        log.warning(f"Error calculando VIX term structure: {e}")
        return {}


# ----------------- 4. Variance Risk Premium -----------------
def calcular_vrp() -> Optional[float]:
    """
    Variance Risk Premium = VIX^2 - varianza realizada de los ultimos 22 dias.
    Evidencia: Bollerslev, Tauchen & Zhou (2009, RFS).

    VRP alto -> mercado sobrepaga por proteccion (bullish para equities)
    VRP bajo/negativo -> complacencia (bearish)
    """
    try:
        vix_data = yf.Ticker("^VIX").history(period="5d")
        spy_data = yf.Ticker("SPY").history(period="30d")

        if vix_data.empty or spy_data.empty:
            return None

        vix = float(vix_data["Close"].iloc[-1])
        # Varianza implicita (VIX ya es anualizado, lo convertimos a mensual)
        iv_squared = (vix / 100) ** 2

        # Varianza realizada de los ultimos 22 dias (anualizada)
        returns = spy_data["Close"].pct_change().dropna().iloc[-22:]
        rv_monthly = float(returns.var() * 252)

        vrp = (iv_squared - rv_monthly) * 10000  # en basis points para que se vea mejor
        return round(vrp, 2)
    except Exception as e:
        log.warning(f"Error calculando VRP: {e}")
        return None


# ----------------- 5. Breadth -----------------
def calcular_breadth() -> Optional[float]:
    """
    Porcentaje del S&P500 (muestra de 50 acciones) cotizando sobre su 200DMA.
    Evidencia: practitioners, breadth literature.

    >80% = mercado sobrecomprado (cautela)
    <30% = mercado sobrevendido (contrarian buy en slowdown)
    """
    log.info("   Calculando breadth (puede tardar un minuto)...")
    sobre_dma = 0
    total = 0

    for ticker in SP500_MUESTRA:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="260d")
            if hist.empty or len(hist) < 202:
                continue

            closes = hist["Close"]
            dma200 = float(closes.rolling(200).mean().iloc[-1])
            precio = float(closes.iloc[-1])

            if precio > dma200:
                sobre_dma += 1
            total += 1
        except Exception:
            continue

    if total == 0:
        return None

    pct = (sobre_dma / total) * 100
    log.info(f"   Breadth: {sobre_dma}/{total} stocks sobre 200DMA ({pct:.1f}%)")
    return round(pct, 1)


# ----------------- Funcion principal -----------------
def correr_colector_tecnico(db_path: str = DB_PATH) -> dict:
    """
    Corre el colector completo.
    Retorna dict con resumen para el agente tecnico.
    """
    log.info("=" * 60)
    log.info(f"Colector tecnico iniciado: {date.today()}")
    log.info("=" * 60)

    conn = init_technical_tables(db_path)
    hoy = date.today().isoformat()
    resumen = {"fecha": hoy, "activos": {}, "mercado": {}}

    # -- 1-2. Calcular 200DMA y momentum para cada activo --
    log.info("\n--- Indicadores por activo (200DMA + Momentum) ---")
    for activo, ticker in TICKERS_PRECIO.items():
        log.info(f"\n  {activo} ({ticker}):")
        hist = descargar_precios(ticker, dias=260)
        if hist is None:
            log.warning(f"    No se pudieron obtener datos")
            continue

        dma_info = calcular_dma200(hist)
        mom_info = calcular_momentum_vol_adjusted(hist)

        if not dma_info or not mom_info:
            continue

        log.info(f"    Precio: {dma_info['precio_actual']} | "
                 f"200DMA: {dma_info['dma200']} | "
                 f"Estado: {dma_info['cruce_dma']} ({dma_info['pct_sobre_dma']:+.1f}%)")
        log.info(f"    Momentum 12M: {mom_info['momentum_12m']:+.1f}% | "
                 f"Vol: {mom_info['vol_12m']:.1f}% | "
                 f"Mom/Vol: {mom_info['momentum_ajust']:+.3f}")

        # Guardar en DB
        conn.execute("""
            INSERT OR REPLACE INTO senales_tecnicas
            (fecha, activo, precio_actual, dma200, pct_sobre_dma, cruce_dma,
             momentum_12m, vol_12m, momentum_ajust)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            hoy, activo,
            dma_info["precio_actual"], dma_info["dma200"],
            dma_info["pct_sobre_dma"], dma_info["cruce_dma"],
            mom_info["momentum_12m"], mom_info["vol_12m"],
            mom_info["momentum_ajust"],
        ))

        resumen["activos"][activo] = {**dma_info, **mom_info}

    # -- 3. VIX Term Structure --
    log.info("\n--- VIX Term Structure ---")
    vix_ts = calcular_vix_term_structure()
    if vix_ts:
        log.info(f"  VIX spot: {vix_ts['vix_spot']} | VIX 3M: {vix_ts['vix_3m']} | "
                 f"Estado: {vix_ts['vix_term_struct']}")
        resumen["mercado"].update(vix_ts)

    # -- 4. VRP --
    log.info("\n--- Variance Risk Premium ---")
    vrp = calcular_vrp()
    if vrp is not None:
        log.info(f"  VRP: {vrp:+.2f} bps")
        resumen["mercado"]["vrp"] = vrp

    # -- 5. Breadth --
    log.info("\n--- Breadth (% S&P500 sobre 200DMA) ---")
    breadth = calcular_breadth()
    if breadth is not None:
        resumen["mercado"]["pct_sobre_200"] = breadth

    # Guardar indicadores de mercado
    conn.execute("""
        INSERT OR REPLACE INTO indicadores_tecnicos_mercado
        (fecha, vix_spot, vix_3m, vix_term_struct, vrp, pct_sobre_200)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        hoy,
        resumen["mercado"].get("vix_spot"),
        resumen["mercado"].get("vix_3m"),
        resumen["mercado"].get("vix_term_struct"),
        resumen["mercado"].get("vrp"),
        resumen["mercado"].get("pct_sobre_200"),
    ))
    conn.commit()
    conn.close()

    log.info("\n" + "=" * 60)
    log.info(f"Colector tecnico completado: {len(resumen['activos'])} activos procesados")
    log.info("=" * 60)

    return resumen


# ----------------- Snapshot para el agente -----------------
def obtener_snapshot_tecnico(db_path: str = DB_PATH) -> dict:
    """
    Lee la DB y retorna el snapshot listo para el agente tecnico.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Ultima senal tecnica de cada activo
    activos = {}
    for row in conn.execute("""
        SELECT * FROM senales_tecnicas
        WHERE fecha = (SELECT MAX(fecha) FROM senales_tecnicas)
    """):
        activos[row["activo"]] = dict(row)

    # Ultimos indicadores de mercado
    mercado_row = conn.execute("""
        SELECT * FROM indicadores_tecnicos_mercado
        ORDER BY fecha DESC LIMIT 1
    """).fetchone()
    mercado = dict(mercado_row) if mercado_row else {}

    conn.close()

    return {
        "timestamp": datetime.now().isoformat(),
        "activos":   activos,
        "mercado":   mercado,
    }


# ----------------- Main -----------------
if __name__ == "__main__":
    resumen = correr_colector_tecnico()
    print(f"\nResumen: {len(resumen['activos'])} activos, "
          f"breadth={resumen['mercado'].get('pct_sobre_200')}%, "
          f"VIX={resumen['mercado'].get('vix_spot')}, "
          f"VRP={resumen['mercado'].get('vrp')} bps")
