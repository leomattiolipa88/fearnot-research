"""
Macro Agent — Tracker de Performance
Registra señales, evalúa resultados, mide si el agente funciona.
"""

import sqlite3
import json
import yfinance as yf
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

DB_PATH = "data/macro.db"

# Cuántos días esperar para evaluar cada horizonte
DIAS_POR_HORIZONTE = {
    "SEMANAL":     5,
    "MENSUAL":     21,
    "TRIMESTRAL":  63,
}

# Tickers reales para cada activo del agente
TICKERS = {
    # Macro / Technical agents
    "SPY": "SPY",
    "QQQ": "QQQ",
    "GLD": "GLD",
    "TLT": "TLT",
    "USO": "USO",
    "DXY": "DX-Y.NYB",
    # Energy Desk - commodities/futures
    "WTI": "CL=F",
    "BRENT": "BZ=F",
    "NATGAS": "NG=F",
    "GASOLINA": "RB=F",
    "HEATING_OIL": "HO=F",
    # Energy Desk - stocks/ETFs
    "XOM": "XOM",
    "CVX": "CVX",
    "OXY": "OXY",
    "VLO": "VLO",
    "EOG": "EOG",
    "VIST": "VIST",
    "XLE": "XLE",
    "CRAK": "CRAK",
}


# ── Setup de tablas ───────────────────────────────────────────────────────────
def init_tracker(db_path: str = DB_PATH):
    """Crea las tablas de tracking si no existen."""
    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS senales (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_senal       TEXT NOT NULL,
            activo            TEXT NOT NULL,
            direccion         TEXT NOT NULL,
            horizonte         TEXT NOT NULL,
            conviccion        INTEGER NOT NULL,
            precio_entrada    REAL,
            regimen           TEXT,
            razonamiento      TEXT,
            fuente            TEXT DEFAULT 'macro',
            fecha_evaluacion  TEXT,
            precio_salida     REAL,
            retorno_pct       REAL,
            acierto           INTEGER,
            evaluado          INTEGER DEFAULT 0
        )
    """)
    # Agregar columna fuente si la tabla ya existia
    try:
        conn.execute("ALTER TABLE senales ADD COLUMN fuente TEXT DEFAULT 'macro'")
        conn.commit()
    except:
        pass

    conn.execute("""
        CREATE TABLE IF NOT EXISTS performance_diaria (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT NOT NULL UNIQUE,
            senales_total   INTEGER,
            senales_long    INTEGER,
            senales_short   INTEGER,
            hit_rate_7d     REAL,
            hit_rate_21d    REAL,
            hit_rate_63d    REAL,
            retorno_medio   REAL,
            confianza_media REAL
        )
    """)

    conn.commit()
    return conn


# ── Registrar señales nuevas ──────────────────────────────────────────────────
def registrar_senales(tesis: dict, db_path: str = DB_PATH):
    """
    Toma la tesis del agente y registra cada señal con su precio de entrada.
    Se llama automáticamente después de cada run del agente.

    Modelo B (Position Holder): si ya existe una señal abierta del mismo
    (fuente, activo, direccion, horizonte) dentro del horizonte, NO registra
    una nueva. Esto previene duplicados conceptuales.
    """
    conn = init_tracker(db_path)
    hoy = date.today().isoformat()
    registradas = 0
    skipped = 0

    fuente = tesis.get("fuente", "macro")

    for senal in tesis.get("senales", []):
        activo = senal["activo"]
        direccion = senal["direccion"]
        horizonte = senal["horizonte"]
        dias = DIAS_POR_HORIZONTE.get(horizonte, 21)

        # CHECK DEDUPLICACION: existe señal abierta del mismo
        # (fuente, activo, direccion, horizonte) dentro del horizonte?
        fecha_limite = (date.today() - timedelta(days=dias)).isoformat()
        existe = conn.execute("""
            SELECT id FROM senales
            WHERE fuente = ? AND activo = ? AND direccion = ?
              AND horizonte = ? AND fecha_senal > ?
            LIMIT 1
        """, (fuente, activo, direccion, horizonte, fecha_limite)).fetchone()

        if existe:
            skipped += 1
            continue

        ticker = TICKERS.get(activo)

        # Obtener precio de entrada actual
        precio_entrada = None
        if ticker:
            try:
                hist = yf.Ticker(ticker).history(period="1d")
                if not hist.empty:
                    precio_entrada = float(hist["Close"].iloc[-1])
            except Exception:
                pass

        # Calcular fecha de evaluación según horizonte
        fecha_eval = (date.today() + timedelta(days=dias)).isoformat()

        conn.execute("""
            INSERT INTO senales
            (fecha_senal, activo, direccion, horizonte, conviccion,
             precio_entrada, regimen, razonamiento, fuente, fecha_evaluacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            hoy,
            activo,
            direccion,
            horizonte,
            senal["conviccion"],
            precio_entrada,
            tesis.get("regimen", {}).get("clasificacion", ""),
            senal.get("razonamiento", "")[:500],
            fuente,
            fecha_eval
        ))
        registradas += 1

    conn.commit()
    conn.close()
    print(f"  Tracker [{fuente}]: {registradas} nuevas, {skipped} skipped (ya abiertas)")
    return registradas


# ── Evaluar señales vencidas ──────────────────────────────────────────────────
def evaluar_senales_vencidas(db_path: str = DB_PATH) -> list:
    """
    Busca señales cuya fecha de evaluación ya llegó y las evalúa.
    Descarga el precio actual y calcula si la señal acertó.
    """
    conn = init_tracker(db_path)
    hoy = date.today().isoformat()

    # Buscar señales no evaluadas cuya fecha de evaluación ya pasó
    vencidas = conn.execute("""
        SELECT id, activo, direccion, precio_entrada, fecha_evaluacion
        FROM senales
        WHERE evaluado = 0
        AND fecha_evaluacion <= ?
        AND precio_entrada IS NOT NULL
    """, (hoy,)).fetchall()

    resultados = []

    for row in vencidas:
        id_senal, activo, direccion, precio_entrada, fecha_eval = row
        ticker = TICKERS.get(activo)
        if not ticker:
            continue

        try:
            hist = yf.Ticker(ticker).history(period="2d")
            if hist.empty:
                continue

            precio_salida = float(hist["Close"].iloc[-1])
            retorno = (precio_salida - precio_entrada) / precio_entrada

            # ¿Acertó?
            if direccion == "LONG":
                acierto = 1 if retorno > 0 else 0
            elif direccion == "SHORT":
                acierto = 1 if retorno < 0 else 0
            else:  # NEUTRAL
                acierto = 1 if abs(retorno) < 0.02 else 0

            conn.execute("""
                UPDATE senales
                SET precio_salida = ?,
                    retorno_pct   = ?,
                    acierto       = ?,
                    evaluado      = 1,
                    fecha_evaluada = ?
                WHERE id = ?
            """, (precio_salida, retorno * 100, acierto, hoy, id_senal))

            resultado = {
                "activo":         activo,
                "direccion":      direccion,
                "precio_entrada": precio_entrada,
                "precio_salida":  precio_salida,
                "retorno_pct":    round(retorno * 100, 2),
                "acierto":        bool(acierto),
            }
            resultados.append(resultado)
            emoji = "✅" if acierto else "❌"
            print(f"{emoji} {activo:6s} {direccion:6s} → "
                  f"entrada: {precio_entrada:.2f} | "
                  f"salida: {precio_salida:.2f} | "
                  f"retorno: {retorno*100:+.1f}%")

        except Exception as e:
            print(f"Error evaluando {activo}: {e}")
            continue

    conn.commit()
    conn.close()
    return resultados


# ── Evaluar convicciones del Synthesizer (path-dependent) ─────────────────────
def evaluar_convicciones_vencidas(db_path: str = DB_PATH) -> list:
    """
    Evalua convicciones del Synthesizer cuya fecha de evaluacion ya llego.

    PATH-DEPENDENT: descarga la serie completa de precios entre entry y exit,
    y calcula no solo el retorno final sino tambien:
    - MFE (Maximum Favorable Excursion): el mejor momento del trade
    - MAE (Maximum Adverse Excursion): el peor momento del trade
    - Volatilidad realizada
    - Dias hasta MFE/MAE
    - Precio max/min durante el trade

    Corrige bug de single-point: usa el precio del dia de vencimiento
    (fecha_evaluacion), no el precio de HOY.

    Usa el dict TICKERS para mapear nombres a tickers yfinance (BRENT -> BZ=F).
    """
    import pandas as pd

    conn = sqlite3.connect(db_path)
    hoy = date.today().isoformat()

    vencidas = conn.execute("""
        SELECT id, fecha, ticker, direccion, precio_entrada, fecha_evaluacion
        FROM convicciones
        WHERE evaluado = 0
          AND fecha_evaluacion <= ?
          AND precio_entrada IS NOT NULL
    """, (hoy,)).fetchall()

    resultados = []
    for row in vencidas:
        id_conv, fecha_entry, ticker_raw, direccion, precio_entrada, fecha_eval = row

        ticker_yf = TICKERS.get(ticker_raw, ticker_raw)

        try:
            # Descargar serie completa entry -> exit (+1 dia para incluir el dia de eval)
            end_plus = (date.fromisoformat(fecha_eval) + timedelta(days=1)).isoformat()
            hist = yf.Ticker(ticker_yf).history(start=fecha_entry, end=end_plus)

            if hist.empty or len(hist) < 1:
                print(f"   Sin datos para {ticker_raw} ({ticker_yf}) entre {fecha_entry} y {fecha_eval} - skip")
                continue

            # Precio de salida = ultimo Close disponible <= fecha_evaluacion
            precio_salida = float(hist["Close"].iloc[-1])

            # Path-dependent metrics
            max_high = float(hist["High"].max())
            min_low = float(hist["Low"].min())
            dia_max = hist["High"].idxmax().date()
            dia_min = hist["Low"].idxmin().date()

            entry_d = date.fromisoformat(fecha_entry)
            dias_hasta_mfe = (dia_max - entry_d).days
            dias_hasta_mae = (dia_min - entry_d).days
            dias_trade = (date.fromisoformat(fecha_eval) - entry_d).days

            # Retornos segun direccion
            if direccion == "SHORT":
                # Para SHORT, "favorable" es cuando el precio BAJA
                mfe = (precio_entrada - min_low) / precio_entrada * 100
                mae = (precio_entrada - max_high) / precio_entrada * 100
                retorno_final = (precio_entrada - precio_salida) / precio_entrada * 100
                # swap dias (el min_low es el mejor momento para short)
                dias_hasta_mfe, dias_hasta_mae = dias_hasta_mae, dias_hasta_mfe
            else:  # LONG o NEUTRAL
                mfe = (max_high - precio_entrada) / precio_entrada * 100
                mae = (min_low - precio_entrada) / precio_entrada * 100
                retorno_final = (precio_salida - precio_entrada) / precio_entrada * 100

            # Volatilidad realizada (std de retornos diarios de Close)
            retornos_diarios = hist["Close"].pct_change().dropna()
            vol = float(retornos_diarios.std() * 100) if len(retornos_diarios) > 1 else 0.0

            # Acierto: final return positivo (definicion estricta)
            if direccion == "LONG":
                acierto = 1 if retorno_final > 0 else 0
            elif direccion == "SHORT":
                acierto = 1 if retorno_final > 0 else 0  # ya invertido arriba
            else:
                acierto = 1 if abs(retorno_final) < 2 else 0

            conn.execute("""
                UPDATE convicciones
                SET precio_salida    = ?,
                    retorno_pct      = ?,
                    mfe_pct          = ?,
                    mae_pct          = ?,
                    dias_hasta_mfe   = ?,
                    dias_hasta_mae   = ?,
                    volatilidad_pct  = ?,
                    precio_max       = ?,
                    precio_min       = ?,
                    dias_trade       = ?,
                    evaluado         = 1
                WHERE id = ?
            """, (
                round(precio_salida, 2),
                round(retorno_final, 2),
                round(mfe, 2),
                round(mae, 2),
                dias_hasta_mfe,
                dias_hasta_mae,
                round(vol, 2),
                round(max_high, 2),
                round(min_low, 2),
                dias_trade,
                id_conv,
            ))

            resultado = {
                "ticker":         ticker_raw,
                "direccion":      direccion,
                "precio_entrada": precio_entrada,
                "precio_salida":  round(precio_salida, 2),
                "retorno_pct":    round(retorno_final, 2),
                "mfe_pct":        round(mfe, 2),
                "mae_pct":        round(mae, 2),
                "volatilidad_pct": round(vol, 2),
                "acierto":        bool(acierto),
            }
            resultados.append(resultado)

            emoji = "WIN " if acierto else "LOSS"
            print(f"{emoji} {ticker_raw:6s} {direccion:6s} -> "
                  f"final: {retorno_final:+.1f}% | "
                  f"MFE: {mfe:+.1f}% (d{dias_hasta_mfe}) | "
                  f"MAE: {mae:+.1f}% (d{dias_hasta_mae}) | "
                  f"vol: {vol:.1f}%")
        except Exception as e:
            print(f"   Error evaluando {ticker_raw}: {e}")
            continue

    conn.commit()
    conn.close()
    return resultados


# ── Calcular métricas de performance ─────────────────────────────────────────
def calcular_performance(db_path: str = DB_PATH) -> dict:
    """
    Calcula todas las métricas de performance del agente.
    Retorna un dict con hit rates, retornos, y calibración de convicción.
    """
    conn = init_tracker(db_path)

    # Todas las señales evaluadas
    df = pd.read_sql_query("""
        SELECT activo, direccion, horizonte, conviccion,
               retorno_pct, acierto, fecha_senal, regimen
        FROM senales
        WHERE evaluado = 1
    """, conn)
    conn.close()

    if df.empty:
        return {"mensaje": "No hay señales evaluadas todavía. Volvé en unos días."}

    metricas = {}

    # ── Hit rate global ───────────────────────────────────────────────────────
    metricas["total_senales"] = len(df)
    metricas["hit_rate_global"] = round(df["acierto"].mean() * 100, 1)
    metricas["retorno_medio_pct"] = round(df["retorno_pct"].mean(), 2)

    # ── Hit rate por horizonte ────────────────────────────────────────────────
    metricas["por_horizonte"] = {}
    for horizonte in ["SEMANAL", "MENSUAL", "TRIMESTRAL"]:
        subset = df[df["horizonte"] == horizonte]
        if len(subset) >= 3:
            metricas["por_horizonte"][horizonte] = {
                "n":        len(subset),
                "hit_rate": round(subset["acierto"].mean() * 100, 1),
                "retorno":  round(subset["retorno_pct"].mean(), 2),
            }

    # ── Hit rate por activo ───────────────────────────────────────────────────
    metricas["por_activo"] = {}
    for activo in df["activo"].unique():
        subset = df[df["activo"] == activo]
        if len(subset) >= 3:
            metricas["por_activo"][activo] = {
                "n":        len(subset),
                "hit_rate": round(subset["acierto"].mean() * 100, 1),
                "retorno":  round(subset["retorno_pct"].mean(), 2),
            }

    # ── Calibración de convicción ─────────────────────────────────────────────
    # Esta es la métrica más importante: ¿la convicción alta predice mejor?
    metricas["calibracion_conviccion"] = {}
    bins = [(1, 4, "baja"), (5, 7, "media"), (8, 10, "alta")]
    for min_c, max_c, label in bins:
        subset = df[(df["conviccion"] >= min_c) & (df["conviccion"] <= max_c)]
        if len(subset) >= 3:
            metricas["calibracion_conviccion"][label] = {
                "n":        len(subset),
                "hit_rate": round(subset["acierto"].mean() * 100, 1),
                "retorno":  round(subset["retorno_pct"].mean(), 2),
            }

    # ── Hit rate por régimen ──────────────────────────────────────────────────
    metricas["por_regimen"] = {}
    for regimen in df["regimen"].unique():
        if not regimen:
            continue
        subset = df[df["regimen"] == regimen]
        if len(subset) >= 3:
            metricas["por_regimen"][regimen] = {
                "n":        len(subset),
                "hit_rate": round(subset["acierto"].mean() * 100, 1),
            }

    # ── Señal de alerta ───────────────────────────────────────────────────────
    hr = metricas["hit_rate_global"]
    if hr < 45:
        metricas["alerta"] = "🚨 Hit rate < 45% — el agente está activamente dañando"
    elif hr < 52:
        metricas["alerta"] = "⚠️  Hit rate < 52% — no hay edge claro todavía"
    elif hr < 58:
        metricas["alerta"] = "🟡 Hit rate aceptable — seguir monitoreando"
    else:
        metricas["alerta"] = "✅ Hit rate > 58% — el agente tiene edge positivo"

    return metricas


# ── Imprimir reporte de performance ──────────────────────────────────────────
def calcular_performance_convicciones(db_path: str = DB_PATH) -> dict:
    """
    Metricas agregadas sobre convicciones EVALUADAS del Synthesizer.
    Disenadas para ser significativas desde poca data (no requieren
    masa critica como Sharpe).

    Returns dict con:
    - n_evaluadas, n_aciertos, win_rate
    - avg_return, avg_mfe, avg_mae
    - alpha_capture: cuanto del MFE se captura en el final (final/MFE)
    - avg_volatilidad
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT ticker, direccion, retorno_pct, mfe_pct, mae_pct, volatilidad_pct
        FROM convicciones
        WHERE evaluado = 1 AND retorno_pct IS NOT NULL
    """).fetchall()
    conn.close()

    n = len(rows)
    if n == 0:
        return {
            "n_evaluadas": 0,
            "mensaje": "Sin convicciones evaluadas todavia",
        }

    retornos = [r["retorno_pct"] for r in rows]
    mfes = [r["mfe_pct"] for r in rows if r["mfe_pct"] is not None]
    maes = [r["mae_pct"] for r in rows if r["mae_pct"] is not None]
    vols = [r["volatilidad_pct"] for r in rows if r["volatilidad_pct"] is not None]

    aciertos = sum(1 for r in retornos if r > 0)

    avg_return = sum(retornos) / n
    avg_mfe = sum(mfes) / len(mfes) if mfes else 0
    avg_mae = sum(maes) / len(maes) if maes else 0
    avg_vol = sum(vols) / len(vols) if vols else 0

    # Alpha capture: que fraccion del peak (MFE) se captura en el cierre
    # Solo para trades con MFE positivo (donde hubo oportunidad)
    capturas = []
    for r in rows:
        if r["mfe_pct"] and r["mfe_pct"] > 0:
            capturas.append(r["retorno_pct"] / r["mfe_pct"])
    alpha_capture = (sum(capturas) / len(capturas) * 100) if capturas else None

    return {
        "n_evaluadas": n,
        "n_aciertos": aciertos,
        "win_rate": round(aciertos / n * 100, 1),
        "avg_return_pct": round(avg_return, 2),
        "avg_mfe_pct": round(avg_mfe, 2),
        "avg_mae_pct": round(avg_mae, 2),
        "avg_volatilidad_pct": round(avg_vol, 2),
        "alpha_capture_pct": round(alpha_capture, 1) if alpha_capture is not None else None,
    }


def imprimir_reporte(db_path: str = DB_PATH):
    """Imprime el reporte completo de performance en la terminal."""

    print("\n" + "=" * 60)
    print("REPORTE DE PERFORMANCE DEL AGENTE")
    print(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Evaluar señales vencidas primero
    print("\n📊 Evaluando señales vencidas...")
    resultados = evaluar_senales_vencidas(db_path)
    if not resultados:
        print("   No hay señales vencidas hoy")

    # Calcular métricas
    metricas = calcular_performance(db_path)

    if "mensaje" in metricas:
        print(f"\n{metricas['mensaje']}")
        print("\nEl sistema necesita al menos 5 días de señales para mostrar métricas.")
        return

    print(f"\n{metricas.get('alerta', '')}")
    print(f"\n📈 MÉTRICAS GLOBALES")
    print(f"   Total señales evaluadas: {metricas['total_senales']}")
    print(f"   Hit rate global:         {metricas['hit_rate_global']}%")
    print(f"   Retorno medio:           {metricas['retorno_medio_pct']:+.2f}%")

    if metricas.get("por_horizonte"):
        print(f"\n⏱️  POR HORIZONTE")
        for h, v in metricas["por_horizonte"].items():
            print(f"   {h:12s}: {v['hit_rate']:5.1f}% hit rate | "
                  f"{v['retorno']:+.2f}% retorno medio | n={v['n']}")

    if metricas.get("por_activo"):
        print(f"\n📦 POR ACTIVO")
        for a, v in metricas["por_activo"].items():
            print(f"   {a:6s}: {v['hit_rate']:5.1f}% hit rate | "
                  f"{v['retorno']:+.2f}% retorno medio | n={v['n']}")

    if metricas.get("calibracion_conviccion"):
        print(f"\n🎯 CALIBRACIÓN DE CONVICCIÓN (la más importante)")
        print(f"   Si el agente está bien calibrado, convicción alta = hit rate alto")
        for nivel, v in metricas["calibracion_conviccion"].items():
            print(f"   Convicción {nivel:6s}: {v['hit_rate']:5.1f}% hit rate | "
                  f"{v['retorno']:+.2f}% retorno | n={v['n']}")

    if metricas.get("por_regimen"):
        print(f"\n🌍 POR RÉGIMEN")
        for r, v in metricas["por_regimen"].items():
            print(f"   {r:15s}: {v['hit_rate']:5.1f}% hit rate | n={v['n']}")

    print("\n" + "=" * 60)
    print("INTERPRETACIÓN:")
    print("  > 58% hit rate sostenido = el agente tiene edge real")
    print("  < 50% hit rate           = descartá las señales de ese tipo")
    print("  Convicción alta > baja   = el scoring está bien calibrado")
    print("  Convicción alta < baja   = el scoring no sirve, ignorarlo")
    print("=" * 60)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "reporte":
        imprimir_reporte()
    else:
        print("Uso:")
        print("  python3 tracker.py reporte   → ver performance del agente")
        print("\nEl tracker se alimenta automáticamente cuando corrés agent.py")
