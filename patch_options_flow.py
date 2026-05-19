#!/usr/bin/env python3
"""
Patch script para agregar 4 indicadores de options flow al technical_collector.py:
  1. VIX IV Percentile (1-year)
  2. Put/Call Ratio (CBOE)
  3. VIX vs RVX skew (small caps stress)
  4. Term structure expandida (VIX9D + VIX6M)

Hace todos los cambios automaticamente. No requiere pasos manuales.
"""

import shutil
from pathlib import Path

ARCHIVO = Path.home() / "Desktop" / "macro_agent" / "technical_collector.py"
BACKUP = Path.home() / "Desktop" / "macro_agent" / "technical_collector.py.bak"

if not ARCHIVO.exists():
    print(f"ERROR: No encuentro {ARCHIVO}")
    exit(1)

shutil.copy(ARCHIVO, BACKUP)
print(f"[1/4] Backup creado en {BACKUP.name}")

contenido = ARCHIVO.read_text()

# ============================================================
# CAMBIO 1: Expandir tabla con migracion segura
# ============================================================
tabla_vieja = """    conn.execute(\"\"\"
        CREATE TABLE IF NOT EXISTS indicadores_tecnicos_mercado (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT NOT NULL UNIQUE,
            vix_spot        REAL,
            vix_3m          REAL,
            vix_term_struct TEXT,
            vrp             REAL,
            pct_sobre_200   REAL
        )
    \"\"\")"""

tabla_nueva = """    conn.execute(\"\"\"
        CREATE TABLE IF NOT EXISTS indicadores_tecnicos_mercado (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           TEXT NOT NULL UNIQUE,
            vix_spot        REAL,
            vix_9d          REAL,
            vix_3m          REAL,
            vix_6m          REAL,
            vix_term_struct TEXT,
            vrp             REAL,
            pct_sobre_200   REAL,
            vix_iv_pct      REAL,
            put_call_ratio  REAL,
            vix_rvx_skew    REAL
        )
    \"\"\")
    # Migracion para DBs viejas: agregar columnas si no existen
    for col in ["vix_9d REAL", "vix_6m REAL", "vix_iv_pct REAL",
                "put_call_ratio REAL", "vix_rvx_skew REAL"]:
        try:
            conn.execute(f"ALTER TABLE indicadores_tecnicos_mercado ADD COLUMN {col}")
        except Exception:
            pass"""

if tabla_vieja in contenido:
    contenido = contenido.replace(tabla_vieja, tabla_nueva)
    print("[2/4] Tabla expandida con 5 columnas nuevas")
else:
    print("[2/4] La tabla parece ya modificada (skip)")

# ============================================================
# CAMBIO 2: Agregar funcion antes de "if __name__"
# ============================================================
funcion_nueva = '''

# ----------------- INDICADORES DE OPTIONS FLOW -----------------
def calcular_indicadores_options_flow() -> dict:
    """
    Calcula 4 indicadores adicionales (gratis via yfinance):
    1. VIX IV Percentile (1-year)
    2. Put/Call Ratio CBOE
    3. VIX vs RVX skew (small caps stress)
    4. Term structure expandida (VIX9D, VIX6M)
    """
    resultados = {
        "vix_9d": None, "vix_6m": None,
        "vix_iv_pct": None, "put_call_ratio": None, "vix_rvx_skew": None,
    }

    # 1. Term structure expandida
    for nombre, ticker in [("vix_9d", "^VIX9D"), ("vix_6m", "^VIX6M")]:
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if not hist.empty:
                resultados[nombre] = float(hist["Close"].iloc[-1])
        except Exception as e:
            log.warning(f"Error obteniendo {ticker}: {e}")

    # 2. VIX IV Percentile (1-year)
    try:
        vix_hist = yf.Ticker("^VIX").history(period="1y")
        if not vix_hist.empty and len(vix_hist) > 200:
            vix_actual = float(vix_hist["Close"].iloc[-1])
            vix_pasado = vix_hist["Close"].iloc[:-1]
            percentil = (vix_pasado < vix_actual).sum() / len(vix_pasado) * 100
            resultados["vix_iv_pct"] = round(float(percentil), 1)
    except Exception as e:
        log.warning(f"Error VIX IV percentile: {e}")

    # 3. VIX vs RVX skew (small caps stress)
    try:
        rvx_hist = yf.Ticker("^RVX").history(period="5d")
        vix_hist = yf.Ticker("^VIX").history(period="5d")
        if not rvx_hist.empty and not vix_hist.empty:
            rvx = float(rvx_hist["Close"].iloc[-1])
            vix = float(vix_hist["Close"].iloc[-1])
            if vix > 0:
                resultados["vix_rvx_skew"] = round(rvx / vix, 3)
    except Exception as e:
        log.warning(f"Error VIX/RVX skew: {e}")

    # 4. Put/Call Ratio (CBOE)
    try:
        cpc_hist = yf.Ticker("^CPC").history(period="5d")
        if not cpc_hist.empty:
            resultados["put_call_ratio"] = round(float(cpc_hist["Close"].iloc[-1]), 3)
    except Exception as e:
        log.warning(f"Error Put/Call Ratio: {e}")

    return resultados


'''

if "calcular_indicadores_options_flow" not in contenido:
    if 'if __name__ == "__main__":' in contenido:
        contenido = contenido.replace(
            'if __name__ == "__main__":',
            funcion_nueva + 'if __name__ == "__main__":'
        )
        print("[3/4] Funcion calcular_indicadores_options_flow agregada")
    elif "if __name__ == '__main__':" in contenido:
        contenido = contenido.replace(
            "if __name__ == '__main__':",
            funcion_nueva + "if __name__ == '__main__':"
        )
        print("[3/4] Funcion calcular_indicadores_options_flow agregada")
    else:
        contenido = contenido + funcion_nueva
        print("[3/4] Funcion agregada al final del archivo")
else:
    print("[3/4] La funcion ya existe (skip)")

# ============================================================
# CAMBIO 3: Modificar el INSERT y el bloque que llama a la funcion
# ============================================================
insert_viejo = '''        INSERT OR REPLACE INTO indicadores_tecnicos_mercado
        (fecha, vix_spot, vix_3m, vix_term_struct, vrp, pct_sobre_200)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        hoy,
        resumen["mercado"].get("vix_spot"),
        resumen["mercado"].get("vix_3m"),
        resumen["mercado"].get("vix_term_struct"),
        resumen["mercado"].get("vrp"),
        resumen["mercado"].get("pct_sobre_200"),
    ))'''

insert_nuevo = '''        INSERT OR REPLACE INTO indicadores_tecnicos_mercado
        (fecha, vix_spot, vix_9d, vix_3m, vix_6m, vix_term_struct, vrp, pct_sobre_200,
         vix_iv_pct, put_call_ratio, vix_rvx_skew)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        hoy,
        resumen["mercado"].get("vix_spot"),
        options_flow.get("vix_9d"),
        resumen["mercado"].get("vix_3m"),
        options_flow.get("vix_6m"),
        resumen["mercado"].get("vix_term_struct"),
        resumen["mercado"].get("vrp"),
        resumen["mercado"].get("pct_sobre_200"),
        options_flow.get("vix_iv_pct"),
        options_flow.get("put_call_ratio"),
        options_flow.get("vix_rvx_skew"),
    ))'''

if insert_viejo in contenido:
    # Tambien necesitamos agregar la llamada a calcular_indicadores_options_flow()
    # antes del INSERT. La agregamos justo antes del bloque execute.
    contenido = contenido.replace(
        insert_viejo,
        '''options_flow = calcular_indicadores_options_flow()
    log.info(f"      Options flow: VIX IV pct={options_flow.get('vix_iv_pct')}, "
             f"P/C={options_flow.get('put_call_ratio')}, "
             f"RVX/VIX={options_flow.get('vix_rvx_skew')}")
    conn.execute("""
''' + insert_nuevo
    )
    print("[4/4] INSERT modificado y llamada a options_flow agregada")
else:
    print("[4/4] No encontre el INSERT exacto. Verificar manualmente.")

ARCHIVO.write_text(contenido)
print(f"\n✓ Archivo actualizado: {ARCHIVO.name}")
print(f"  Backup en: {BACKUP.name}")
print("\nPara probar, corre:")
print("  cd ~/Desktop/macro_agent && python3 technical_collector.py")
