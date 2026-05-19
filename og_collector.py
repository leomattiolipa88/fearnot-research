"""
FearNot - O&G + LPG Data Collector

Recolecta datos del mercado energetico:
- Precios de WTI, Brent, Natural Gas, Propano, Gasoline, Heating Oil
- Equity tickers clave: XOM, CVX, OXY, VLO, EOG, VIST (Argentina)
- ETFs: XLE (broad energy), CRAK (refiners)
- Inventarios EIA: crude, gasoline, distillate, propane
- Refining utilization
- Natural gas storage
- Calendar spread WTI (proxy de backwardation/contango)
- Crack spread 3:2:1 (margen teorico de refining)

Datos persistidos en data/macro.db (mismas tablas que el resto del sistema).
"""

import os
import sqlite3
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, date, timedelta
from pathlib import Path

DB_PATH = "data/macro.db"


# ----------------- Cargar API keys -----------------
def cargar_env():
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()


# ----------------- Activos a tracker -----------------
ACTIVOS_OG = {
    # Futures (precio del commodity)
    "WTI": "CL=F",            # WTI Crude
    "BRENT": "BZ=F",          # Brent Crude
    "NATGAS": "NG=F",         # Natural Gas Henry Hub
    "GASOLINA": "RB=F",       # RBOB Gasoline (para crack spread)
    "HEATING_OIL": "HO=F",    # Heating Oil / diesel proxy

    # Equities
    "XOM": "XOM",   # ExxonMobil - integrated
    "CVX": "CVX",   # Chevron - integrated
    "OXY": "OXY",   # Occidental - pure E&P (Buffett favorite)
    "VLO": "VLO",   # Valero - pure refiner
    "EOG": "EOG",   # EOG Resources - pure shale
    "VIST": "VIST", # Vista Energy - Argentina/Vaca Muerta

    # ETFs
    "XLE": "XLE",   # Energy Select Sector ETF
    "CRAK": "CRAK", # VanEck Refiners ETF
}


# ----------------- Series de EIA API v2 -----------------
EIA_SERIES = {
    # Petroleum Weekly (PSW = Petroleum Status Weekly)
    "crude_inventory": {
        "endpoint": "petroleum/stoc/wstk/data/",
        "params": {
            "data[]": "value",
            "facets[series][]": "WCESTUS1",  # Crude Oil Ending Stocks (excl SPR)
            "frequency": "weekly",
        },
        "descripcion": "Crude oil inventory USA (thousands of barrels)",
    },
    "gasoline_inventory": {
        "endpoint": "petroleum/stoc/wstk/data/",
        "params": {
            "data[]": "value",
            "facets[series][]": "WGTSTUS1",
            "frequency": "weekly",
        },
        "descripcion": "Total gasoline inventory USA (thousands of barrels)",
    },
    "distillate_inventory": {
        "endpoint": "petroleum/stoc/wstk/data/",
        "params": {
            "data[]": "value",
            "facets[series][]": "WDISTUS1",
            "frequency": "weekly",
        },
        "descripcion": "Distillate inventory USA (thousands of barrels)",
    },
    "propane_inventory": {
        "endpoint": "petroleum/stoc/wstk/data/",
        "params": {
            "data[]": "value",
            "facets[series][]": "WPRSTUS1",
            "frequency": "weekly",
        },
        "descripcion": "Propane/propylene inventory USA (thousands of barrels)",
    },
    "refinery_utilization": {
        "endpoint": "petroleum/pnp/wiup/data/",
        "params": {
            "data[]": "value",
            "facets[series][]": "WPULEUS3",
            "frequency": "weekly",
        },
        "descripcion": "Refinery utilization rate USA (percent)",
    },
    "natgas_storage": {
        "endpoint": "natural-gas/stor/wkly/data/",
        "params": {
            "data[]": "value",
            "facets[series][]": "NW2_EPG0_SWO_R48_BCF",
            "frequency": "weekly",
        },
        "descripcion": "Natural gas working storage Lower 48 (Bcf)",
    },
}


# ----------------- DB helpers -----------------
def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Asegura que existan las tablas necesarias para el OG agent."""
    Path("data").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    # Tabla precios OG (similar a indicadores pero especifica)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS precios_og (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT NOT NULL,
            activo          TEXT NOT NULL,
            ticker          TEXT NOT NULL,
            precio          REAL NOT NULL,
            fecha_descarga  TEXT NOT NULL,
            UNIQUE(fecha, activo)
        )
    """)

    # Tabla indicadores EIA
    conn.execute("""
        CREATE TABLE IF NOT EXISTS indicadores_eia (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre          TEXT NOT NULL,
            valor           REAL NOT NULL,
            fecha_publicacion TEXT NOT NULL,
            fecha_descarga  TEXT NOT NULL,
            descripcion     TEXT,
            UNIQUE(nombre, fecha_publicacion)
        )
    """)

    # Tabla calendar spreads y crack spreads
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spreads_og (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT NOT NULL,
            tipo            TEXT NOT NULL,
            valor           REAL NOT NULL,
            interpretacion  TEXT,
            UNIQUE(fecha, tipo)
        )
    """)

    conn.commit()
    return conn


# ----------------- Recolectar precios via yfinance -----------------
def recolectar_precios(conn: sqlite3.Connection):
    print("\n[1/4] Recolectando precios via yfinance...")
    fecha_hoy = date.today().isoformat()
    fecha_descarga = datetime.now().isoformat()

    exitos = 0
    fallos = []

    for activo, ticker in ACTIVOS_OG.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if hist.empty:
                fallos.append(f"{activo}({ticker}): sin data")
                continue

            precio = float(hist["Close"].iloc[-1])
            fecha_precio = hist.index[-1].date().isoformat()

            conn.execute("""
                INSERT OR REPLACE INTO precios_og
                (fecha, activo, ticker, precio, fecha_descarga)
                VALUES (?, ?, ?, ?, ?)
            """, (fecha_precio, activo, ticker, precio, fecha_descarga))
            exitos += 1

        except Exception as e:
            fallos.append(f"{activo}({ticker}): {e}")

    conn.commit()
    print(f"      OK {exitos}/{len(ACTIVOS_OG)} precios recolectados")
    if fallos:
        for f in fallos:
            print(f"      Fallo: {f}")


# ----------------- Calcular calendar spread WTI -----------------
def calcular_calendar_spread_wti(conn: sqlite3.Connection):
    """
    Calcula el spread entre WTI front month (CL=F) y 6 meses adelante.
    Backwardation (front > 6m) = bullish fisicamente
    Contango (front < 6m) = bearish fisicamente
    """
    print("\n[2/4] Calculando calendar spread WTI...")

    try:
        # WTI front month
        front = yf.Ticker("CL=F").history(period="2d")
        if front.empty:
            print("      No se pudo obtener WTI front month")
            return
        precio_front = float(front["Close"].iloc[-1])

        # WTI 6 meses adelante (aproximado: usamos contrato con 6m de diferencia)
        # Ticker pattern: CL{M}{YY}.NYM donde M = month code (F=Jan, G=Feb...)
        # Como no siempre estan disponibles, intentamos varios fallbacks
        meses_adelante = []
        ahora = datetime.now()
        for offset in [6, 5, 4]:  # intentamos 6m, si falla 5m, etc
            target = ahora + timedelta(days=offset * 30)
            month_codes = ['F', 'G', 'H', 'J', 'K', 'M', 'N', 'Q', 'U', 'V', 'X', 'Z']
            month_code = month_codes[target.month - 1]
            year_short = str(target.year)[-2:]
            ticker_futuro = f"CL{month_code}{year_short}.NYM"
            try:
                t = yf.Ticker(ticker_futuro)
                hist = t.history(period="2d")
                if not hist.empty:
                    precio_futuro = float(hist["Close"].iloc[-1])
                    spread = precio_front - precio_futuro
                    interpretacion = (
                        "BACKWARDATION" if spread > 0
                        else "CONTANGO" if spread < 0
                        else "FLAT"
                    )

                    fecha_hoy = date.today().isoformat()
                    conn.execute("""
                        INSERT OR REPLACE INTO spreads_og
                        (fecha, tipo, valor, interpretacion)
                        VALUES (?, ?, ?, ?)
                    """, (fecha_hoy, f"wti_calendar_{offset}m",
                          spread, interpretacion))
                    conn.commit()

                    print(f"      OK Spread front vs {offset}m: ${spread:.2f}/bbl ({interpretacion})")
                    return
            except Exception:
                continue

        print("      No se pudo calcular calendar spread (futuros lejanos no disponibles)")

    except Exception as e:
        print(f"      Error calculando calendar spread: {e}")


# ----------------- Calcular crack spread 3:2:1 -----------------
def calcular_crack_spread(conn: sqlite3.Connection):
    """
    Crack spread 3:2:1 = (2 * RBOB + 1 * HO) - (3 * WTI)
    Todo convertido a USD/barril.

    RBOB y HO cotizan en USD/galon. 1 barril = 42 galones.
    WTI cotiza en USD/barril.

    Crack alto = refining margins fuertes = bullish refiners
    """
    print("\n[3/4] Calculando crack spread 3:2:1...")

    try:
        wti = yf.Ticker("CL=F").history(period="2d")
        rbob = yf.Ticker("RB=F").history(period="2d")
        ho = yf.Ticker("HO=F").history(period="2d")

        if wti.empty or rbob.empty or ho.empty:
            print("      Falta data para crack spread")
            return

        wti_precio = float(wti["Close"].iloc[-1])
        rbob_precio_galon = float(rbob["Close"].iloc[-1])
        ho_precio_galon = float(ho["Close"].iloc[-1])

        # Convertir RBOB y HO de USD/galon a USD/barril
        rbob_precio_barril = rbob_precio_galon * 42
        ho_precio_barril = ho_precio_galon * 42

        # Formula 3:2:1
        crack = (2 * rbob_precio_barril + 1 * ho_precio_barril) - (3 * wti_precio)
        # Crack por barril de crudo procesado
        crack_por_bbl = crack / 3

        # Interpretacion
        if crack_por_bbl > 25:
            interpretacion = "MUY_FUERTE"
        elif crack_por_bbl > 15:
            interpretacion = "FUERTE"
        elif crack_por_bbl > 8:
            interpretacion = "NORMAL"
        elif crack_por_bbl > 3:
            interpretacion = "DEBIL"
        else:
            interpretacion = "MUY_DEBIL"

        fecha_hoy = date.today().isoformat()
        conn.execute("""
            INSERT OR REPLACE INTO spreads_og
            (fecha, tipo, valor, interpretacion)
            VALUES (?, ?, ?, ?)
        """, (fecha_hoy, "crack_321", crack_por_bbl, interpretacion))
        conn.commit()

        print(f"      OK Crack 3:2:1: ${crack_por_bbl:.2f}/bbl ({interpretacion})")

    except Exception as e:
        print(f"      Error calculando crack spread: {e}")


# ----------------- Recolectar datos EIA -----------------
def recolectar_eia(conn: sqlite3.Connection):
    print("\n[4/4] Recolectando datos de EIA...")

    api_key = os.environ.get("EIA_API_KEY", "")
    if not api_key:
        print("      ERROR: Falta EIA_API_KEY en .env")
        return

    base_url = "https://api.eia.gov/v2/"
    fecha_descarga = datetime.now().isoformat()

    exitos = 0
    fallos = []

    for nombre, config in EIA_SERIES.items():
        try:
            url = base_url + config["endpoint"]
            params = dict(config["params"])
            params["api_key"] = api_key
            params["sort[0][column]"] = "period"
            params["sort[0][direction]"] = "desc"
            params["length"] = "1"  # solo el dato mas reciente

            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            # EIA v2 estructura: response.data[0].value
            if "response" in data and "data" in data["response"]:
                rows = data["response"]["data"]
                if rows:
                    valor = float(rows[0]["value"])
                    fecha_pub = rows[0]["period"]

                    conn.execute("""
                        INSERT OR REPLACE INTO indicadores_eia
                        (nombre, valor, fecha_publicacion, fecha_descarga, descripcion)
                        VALUES (?, ?, ?, ?, ?)
                    """, (nombre, valor, fecha_pub, fecha_descarga,
                          config["descripcion"]))
                    exitos += 1
                else:
                    fallos.append(f"{nombre}: respuesta sin data")
            else:
                fallos.append(f"{nombre}: respuesta inesperada")

        except Exception as e:
            fallos.append(f"{nombre}: {e}")

    conn.commit()
    print(f"      OK {exitos}/{len(EIA_SERIES)} indicadores EIA recolectados")
    if fallos:
        for f in fallos:
            print(f"      Fallo: {f}")


# ----------------- Main -----------------
def main():
    print("=" * 60)
    print(f"O&G + LPG Collector - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    cargar_env()
    conn = init_db()

    recolectar_precios(conn)
    calcular_calendar_spread_wti(conn)
    calcular_crack_spread(conn)
    recolectar_eia(conn)

    conn.close()

    print("\n" + "=" * 60)
    print("Recoleccion completa")
    print("=" * 60)


if __name__ == "__main__":
    main()
