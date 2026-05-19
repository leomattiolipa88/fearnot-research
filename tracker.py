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
