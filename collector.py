"""
Macro Agent — Data Collector
Descarga, valida y guarda indicadores macro con audit trail completo.
Todas las fuentes son FRED (Federal Reserve) o APIs públicas verificables.
"""
 
import sqlite3
import requests
import yfinance as yf
import pandas as pd
import json
import logging
from datetime import datetime, date, timedelta
from dataclasses import dataclass, asdict
from typing import Optional
from pathlib import Path
 
# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/collector.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)
 
# ── Constantes ────────────────────────────────────────────────────────────────
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
DB_PATH   = "data/macro.db"
 
# Rangos históricos validados — fuera de estos rangos = dato corrupto
RANGOS_VALIDOS = {
    "yield_10y":       (0.01,  20.0),
    "yield_3m":        (0.00,  20.0),
    "yield_curve":     (-5.0,  10.0),
    "vix":             (5.0,   90.0),
    "dxy":             (70.0, 120.0),
    "usdjpy":          (70.0, 165.0),
    "eurusd":          (0.80,   2.00),
    "usdcny":          (5.0,   10.0),
    "usdbrl":          (1.5,   10.0),
    "usdmxn":          (10.0,  30.0),
    "gold":            (200.0, 6000.0),
    "spy":             (50.0,  900.0),
    "qqq":             (10.0,  700.0),
    "tlt":             (60.0,  180.0),
    "hy_spread":       (1.5,   25.0),
    "tips_yield_10y":  (-3.0,   8.0),
    "breakeven_5y5y":  (0.0,    6.0),
    "unemployment":    (2.0,   15.0),
    "jobless_claims":  (100e3, 700e3),
    "sahm_rule":       (-1.0,   3.0),
    "pmi_manuf":       (25.0,  70.0),
    "pmi_services":    (25.0,  70.0),
}
 
# Cuántos días puede tener un dato desde su fecha de PUBLICACIÓN antes de
# considerarse "viejo". Toda serie fetched por correr_colector() debe tener
# entrada explícita — el default 5 (en verificar_freshness) es red de
# seguridad, no configuración implícita. Ver TECHNICAL_DEBT.md (2026-08-01).
FRESHNESS_MAX_DIAS = {
    # ── Diarios (yfinance intraday / FRED daily series) + FRED con rezago + derivados ──
    # 4 días calendario cubre el peor gap normal de mercado: viernes → martes
    # post-feriado. Un dato genuinamente estancado dispara a los 5+.
    # (Refinamiento futuro: umbral en días hábiles — ver TECHNICAL_DEBT.md.)
    "yield_10y":              4,
    "yield_3m":               4,
    "vix":                    4,
    "dxy":                    4,
    "usdjpy":                 4,
    "eurusd":                 4,
    "usdcny":                 4,
    "usdbrl":                 4,
    "usdmxn":                 4,
    "gold":                   4,
    "spy":                    4,
    "qqq":                    4,
    "tlt":                    4,
    "yield_10y_mkt":          4,  # confirmación yfinance del yield_10y (^TNX)
    "usdjpy_mkt":             4,  # confirmación yfinance del usdjpy

    # FRED con 1-2 días hábiles de rezago típico (mismo umbral: dentro del gap normal)
    "hy_spread":              4,  # BAMLH0A0HYM2 - publicado al día siguiente
    "tips_yield_10y":         4,  # DFII10
    "breakeven_5y5y":         4,  # T5YIFR

    # Derivado (recalculado en cada corrida si las bases están frescas)
    "yield_curve":            4,  # spread 10Y-3M

    # ── Semanales ──
    "jobless_claims":         8,  # ICSA - publicado los jueves, +1 día de gracia

    # ── Mensuales ──
    # Nota semántica (calibrado 2026-08-02 tras test en vivo):
    # FRED reporta fecha_publicacion = fecha del PERÍODO OBSERVADO, no del
    # comunicado. Ej: el CPI de junio tiene fecha 2026-06-01 aunque se
    # publique ~15 de julio. Un dato mensual "al día", justo antes del
    # release del siguiente, tiene naturalmente 30-60 días de edad medida
    # por observación; con pce_core (release a fin del mes siguiente) llega
    # a ~89. El umbral cubre el ciclo mensual + rezago de publicación
    # (max ≈ frecuencia + lag_release + margen).
    "unemployment":          75,  # UNRATE - release primer viernes del mes siguiente
    "sahm_rule":             75,  # SAHMREALTIME - depende de UNRATE, mismo calendario
    "cpi":                   75,  # CPIAUCSL - release ~10-15 del mes siguiente
    "pce_core":              95,  # PCEPILFE - release hacia fin del mes siguiente (el más tardío)
    "michigan_inflation_exp": 75, # MICH - quincenal U.Michigan, lag ~15-30 días

    # ── Series declaradas para futuro (no fetched hoy por correr_colector) ──
    "pmi_manuf":             75,  # ISM Manuf. PMI - mensual, release primer día hábil
    "pmi_services":          75,  # ISM Services PMI - mensual, release ~3er día hábil
}
 
 
# ── Dataclass para cada dato ──────────────────────────────────────────────────
@dataclass
class Dato:
    nombre:           str
    valor:            float
    fecha_publicacion: str   # fecha del dato (ej: "2026-03-28")
    fecha_descarga:   str    # cuando lo bajamos nosotros
    fuente:           str    # URL o API usada
    es_valido:        bool
    nota:             str    # razón de invalidez si aplica
 
 
# ── Base de datos ─────────────────────────────────────────────────────────────
def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Crea la base de datos y las tablas si no existen."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS indicadores (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre           TEXT    NOT NULL,
            valor            REAL    NOT NULL,
            fecha_publicacion TEXT   NOT NULL,
            fecha_descarga   TEXT    NOT NULL,
            fuente           TEXT    NOT NULL,
            es_valido        INTEGER NOT NULL,
            nota             TEXT,
            UNIQUE(nombre, fecha_descarga)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alertas (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp      TEXT    NOT NULL,
            nivel          TEXT    NOT NULL,
            nombre_dato    TEXT    NOT NULL,
            mensaje        TEXT    NOT NULL
        )
    """)
    conn.commit()
    log.info(f"Base de datos inicializada: {db_path}")
    return conn
 
 
def guardar_dato(conn: sqlite3.Connection, dato: Dato) -> bool:
    """Guarda un dato en la DB. Retorna True si se guardó, False si ya existía."""
    try:
        conn.execute(
            """INSERT OR IGNORE INTO indicadores
               (nombre, valor, fecha_publicacion, fecha_descarga, fuente, es_valido, nota)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (dato.nombre, dato.valor, dato.fecha_publicacion,
             dato.fecha_descarga, dato.fuente, int(dato.es_valido), dato.nota)
        )
        conn.commit()
        return True
    except Exception as e:
        log.error(f"Error guardando {dato.nombre}: {e}")
        return False
 
 
def registrar_alerta(conn: sqlite3.Connection, nivel: str, nombre: str, mensaje: str):
    """Registra una alerta en la DB y en el log."""
    conn.execute(
        "INSERT INTO alertas (timestamp, nivel, nombre_dato, mensaje) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), nivel, nombre, mensaje)
    )
    conn.commit()
    if nivel == "ERROR":
        log.error(f"[ALERTA {nivel}] {nombre}: {mensaje}")
    else:
        log.warning(f"[ALERTA {nivel}] {nombre}: {mensaje}")
 
 
def obtener_ultimo(conn: sqlite3.Connection, nombre: str) -> Optional[Dato]:
    """Recupera el dato más reciente para un indicador."""
    row = conn.execute(
        "SELECT * FROM indicadores WHERE nombre=? ORDER BY fecha_descarga DESC LIMIT 1",
        (nombre,)
    ).fetchone()
    if not row:
        return None
    return Dato(
        nombre=row[1], valor=row[2], fecha_publicacion=row[3],
        fecha_descarga=row[4], fuente=row[5], es_valido=bool(row[6]), nota=row[7]
    )
 
 
# ── Validación de datos ───────────────────────────────────────────────────────
def validar(nombre: str, valor: float, anterior: Optional[float],
            conn: sqlite3.Connection) -> tuple[bool, str]:
    """
    Valida un dato contra rangos históricos y cambio máximo diario.
    Retorna (es_valido, nota).
    """
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        registrar_alerta(conn, "ERROR", nombre, "Valor nulo o NaN")
        return False, "Valor nulo"
 
    # Rango histórico
    if nombre in RANGOS_VALIDOS:
        min_v, max_v = RANGOS_VALIDOS[nombre]
        if not (min_v <= valor <= max_v):
            msg = f"Fuera de rango histórico: {valor} (esperado {min_v}-{max_v})"
            registrar_alerta(conn, "ERROR", nombre, msg)
            return False, msg
 
    # Cambio máximo diario (solo si tenemos dato anterior)
    if anterior is not None:
        cambios_max = {
            "yield_10y":  0.50,   # 50 bps máximo en un día
            "yield_3m":   0.50,
            "vix":        35.0,
            "dxy":        3.0,
            "usdjpy":     5.0,
            "eurusd":     0.05,
            "gold":       200.0,
            "spy":        0.15,   # 15% máximo en un día
            "hy_spread":  3.0,
        }
        if nombre in cambios_max:
            cambio = abs(valor - anterior)
            # Para porcentajes usamos diferencia relativa
            if nombre in ("spy", "qqq", "tlt", "gold"):
                cambio_rel = abs(valor - anterior) / anterior
                if cambio_rel > cambios_max.get(nombre, 0.20):
                    msg = f"Cambio diario sospechoso: {cambio_rel:.1%}"
                    registrar_alerta(conn, "WARNING", nombre, msg)
                    return True, f"ADVERTENCIA: {msg}"
            else:
                if cambio > cambios_max.get(nombre, 999):
                    msg = f"Cambio diario sospechoso: {cambio:.3f}"
                    registrar_alerta(conn, "WARNING", nombre, msg)
                    return True, f"ADVERTENCIA: {msg}"
 
    return True, "OK"
 
 
def verificar_freshness(conn: sqlite3.Connection, nombre: str) -> tuple[bool, int]:
    """
    Verifica que el dato más reciente no sea demasiado viejo comparando
    contra la fecha de PUBLICACIÓN del dato (no contra cuándo lo bajamos).
    Un dato mensual publicado en mayo, bajado hoy, es de hace 3 meses —
    no de hoy. Antes del fix 2026-08-01 usábamos fecha_descarga y esa
    diferencia hacía aparecer datos vencidos como frescos (ver
    TECHNICAL_DEBT.md).
    Retorna (es_fresco, dias_de_antiguedad).
    """
    ultimo = obtener_ultimo(conn, nombre)
    if not ultimo:
        return False, 999

    # Fallback defensivo: si por algún motivo no hay fecha_publicacion
    # (la columna es NOT NULL, pero por si migran una DB vieja) caemos
    # al comportamiento previo con un WARNING para que sea visible.
    if ultimo.fecha_publicacion:
        fecha_referencia = datetime.fromisoformat(ultimo.fecha_publicacion).date()
    else:
        log.warning(
            f"{nombre}: sin fecha_publicacion, usando fecha_descarga como fallback"
        )
        fecha_referencia = datetime.fromisoformat(ultimo.fecha_descarga).date()

    dias = (date.today() - fecha_referencia).days
    max_dias = FRESHNESS_MAX_DIAS.get(nombre, 5)

    if dias > max_dias:
        registrar_alerta(
            conn, "WARNING", nombre,
            f"Dato tiene {dias} días desde publicación ({ultimo.fecha_publicacion}); "
            f"máx permitido: {max_dias}"
        )
        return False, dias

    return True, dias
 
 
# ── Descarga desde FRED ───────────────────────────────────────────────────────
def fetch_fred(serie: str, api_key: str, nombre: str,
               conn: sqlite3.Connection) -> Optional[Dato]:
    """
    Descarga el último valor disponible de una serie de FRED.
    FRED es la fuente primaria para todos los datos macro — Federal Reserve Bank of St. Louis.
    """
    url = f"{FRED_BASE}?series_id={serie}&api_key={api_key}&file_type=json&sort_order=desc&limit=2"
    hoy = date.today().isoformat()
 
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
 
        obs = [o for o in data.get("observations", []) if o["value"] != "."]
        if not obs:
            registrar_alerta(conn, "ERROR", nombre, f"FRED no devolvió datos para {serie}")
            return None
 
        ultimo_obs = obs[0]
        valor = float(ultimo_obs["value"])
        fecha_pub = ultimo_obs["date"]
 
        # Obtenemos el anterior para validar cambio
        anterior = None
        prev = obtener_ultimo(conn, nombre)
        if prev:
            anterior = prev.valor
 
        es_valido, nota = validar(nombre, valor, anterior, conn)
        fuente = f"FRED:{serie}"
 
        dato = Dato(nombre, valor, fecha_pub, hoy, fuente, es_valido, nota)
        if guardar_dato(conn, dato):
            log.info(f"✓ {nombre:25s} = {valor:10.4f}  [{fecha_pub}]  {nota}")
        return dato
 
    except requests.exceptions.Timeout:
        registrar_alerta(conn, "ERROR", nombre, f"Timeout conectando a FRED para {serie}")
        return None
    except Exception as e:
        registrar_alerta(conn, "ERROR", nombre, f"Error fetching FRED {serie}: {e}")
        return None
 
 
# ── Descarga desde yfinance ───────────────────────────────────────────────────
def fetch_yfinance(ticker: str, nombre: str, campo: str,
                   conn: sqlite3.Connection) -> Optional[Dato]:
    """
    Descarga precio de cierre más reciente via yfinance.
    Usado para ETFs y volatilidad donde yfinance es confiable.
    """
    hoy = date.today().isoformat()
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="3d")
 
        if hist.empty:
            registrar_alerta(conn, "ERROR", nombre, f"yfinance no devolvió datos para {ticker}")
            return None
 
        valor = float(hist[campo].iloc[-1])
        fecha_pub = hist.index[-1].date().isoformat()
 
        anterior = None
        prev = obtener_ultimo(conn, nombre)
        if prev:
            anterior = prev.valor
 
        es_valido, nota = validar(nombre, valor, anterior, conn)
        fuente = f"yfinance:{ticker}"
 
        dato = Dato(nombre, valor, fecha_pub, hoy, fuente, es_valido, nota)
        if guardar_dato(conn, dato):
            log.info(f"✓ {nombre:25s} = {valor:10.4f}  [{fecha_pub}]  {nota}")
        return dato
 
    except Exception as e:
        registrar_alerta(conn, "ERROR", nombre, f"Error yfinance {ticker}: {e}")
        return None
 
 
# ── Cálculos derivados ────────────────────────────────────────────────────────
def calcular_yield_curve(conn: sqlite3.Connection) -> Optional[Dato]:
    """Calcula el spread 10Y-3M — el predictor más robusto de recesiones."""
    hoy = date.today().isoformat()
    y10 = obtener_ultimo(conn, "yield_10y")
    y3m = obtener_ultimo(conn, "yield_3m")
 
    if not y10 or not y3m:
        log.warning("No se puede calcular yield curve — faltan datos base")
        return None
 
    spread = round(y10.valor - y3m.valor, 4)
    anterior = None
    prev = obtener_ultimo(conn, "yield_curve")
    if prev:
        anterior = prev.valor
 
    es_valido, nota = validar("yield_curve", spread, anterior, conn)
    dato = Dato("yield_curve", spread, hoy, hoy, "calculado:10Y-3M", es_valido, nota)
    guardar_dato(conn, dato)
    log.info(f"✓ {'yield_curve':25s} = {spread:10.4f}  [calculado]  {nota}")
    return dato
 
 
def determinar_regimen_basico(conn: sqlite3.Connection) -> dict:
    """
    Clasificación simple de régimen macro usando los indicadores disponibles.
    Este es el output más importante del colector para el agente.
    """
    vc      = obtener_ultimo(conn, "yield_curve")
    hy      = obtener_ultimo(conn, "hy_spread")
    vix     = obtener_ultimo(conn, "vix")
    breakev = obtener_ultimo(conn, "breakeven_5y5y")
    sahm    = obtener_ultimo(conn, "sahm_rule")
 
    senales_riesgo = 0
    senales_inflacion = 0
    detalle = []
 
    if vc and vc.valor < -0.5:
        senales_riesgo += 2
        detalle.append(f"Curva invertida: {vc.valor:.2f}% (recesión en 4-6T)")
    elif vc and vc.valor < 0:
        senales_riesgo += 1
        detalle.append(f"Curva levemente invertida: {vc.valor:.2f}%")
 
    if hy and hy.valor > 5.0:
        senales_riesgo += 2
        detalle.append(f"HY spreads elevados: {hy.valor:.1f}% (stress crediticio)")
    elif hy and hy.valor > 4.0:
        senales_riesgo += 1
        detalle.append(f"HY spreads moderados: {hy.valor:.1f}%")
 
    if vix and vix.valor > 25:
        senales_riesgo += 1
        detalle.append(f"VIX elevado: {vix.valor:.1f} (volatilidad alta)")
 
    if breakev and breakev.valor > 2.5:
        senales_inflacion += 2
        detalle.append(f"Breakevens elevados: {breakev.valor:.2f}% (inflación esperada alta)")
    elif breakev and breakev.valor < 1.5:
        senales_inflacion -= 1
        detalle.append(f"Breakevens bajos: {breakev.valor:.2f}% (deflación posible)")
 
    if sahm and sahm.valor > 0.3:
        senales_riesgo += 2
        detalle.append(f"Regla Sahm activándose: {sahm.valor:.2f} (mercado laboral deteriorándose)")
 
    # Clasificación del régimen
    if senales_riesgo >= 3 and senales_inflacion >= 2:
        regimen = "STAGFLATION"
        color = "red"
    elif senales_riesgo >= 3:
        regimen = "DESACELERACION"
        color = "orange"
    elif senales_inflacion >= 2 and senales_riesgo < 2:
        regimen = "REFLACION"
        color = "yellow"
    else:
        regimen = "GOLDILOCKS"
        color = "green"
 
    return {
        "regimen":          regimen,
        "color":            color,
        "senales_riesgo":   senales_riesgo,
        "senales_inflacion": senales_inflacion,
        "detalle":          detalle,
        "timestamp":        datetime.now().isoformat()
    }
 
 
# ── Colector principal ────────────────────────────────────────────────────────
def correr_colector(api_key_fred: str, db_path: str = DB_PATH) -> dict:
    """
    Función principal. Descarga todos los indicadores, valida, guarda.
    Retorna un resumen del estado del sistema.
    """
    conn = init_db(db_path)
    hoy = date.today().isoformat()
    log.info(f"{'='*60}")
    log.info(f"Colector iniciado: {hoy}")
    log.info(f"{'='*60}")
 
    resultados = {"exitosos": [], "fallidos": [], "advertencias": []}
 
    # ── 1. TASAS Y CURVA ──────────────────────────────────────────────────────
    log.info("--- Tasas y curva de rendimiento ---")
    series_fred = [
        # (serie_fred, nombre_interno)
        ("DGS10",        "yield_10y"),
        ("DTB3",         "yield_3m"),
        ("DFII10",       "tips_yield_10y"),
        ("T5YIFR",       "breakeven_5y5y"),
        ("BAMLH0A0HYM2", "hy_spread"),
    ]
    for serie, nombre in series_fred:
        dato = fetch_fred(serie, api_key_fred, nombre, conn)
        if dato:
            if dato.es_valido:
                resultados["exitosos"].append(nombre)
            else:
                resultados["fallidos"].append(nombre)
        else:
            resultados["fallidos"].append(nombre)
 
    # Derivado: yield curve
    vc = calcular_yield_curve(conn)
    if vc:
        resultados["exitosos"].append("yield_curve")
 
    # ── 2. MERCADO LABORAL ────────────────────────────────────────────────────
    log.info("--- Mercado laboral ---")
    labor_series = [
        ("ICSA",         "jobless_claims"),
        ("UNRATE",       "unemployment"),
        ("SAHMREALTIME", "sahm_rule"),
    ]
    for serie, nombre in labor_series:
        dato = fetch_fred(serie, api_key_fred, nombre, conn)
        if dato:
            (resultados["exitosos"] if dato.es_valido else resultados["fallidos"]).append(nombre)
        else:
            resultados["fallidos"].append(nombre)
 
    # ── 3. INFLACION ─────────────────────────────────────────────────────────
    log.info("--- Inflación ---")
    inflacion_series = [
        ("CPIAUCSL", "cpi"),
        ("PCEPILFE", "pce_core"),
        ("MICH",     "michigan_inflation_exp"),
    ]
    for serie, nombre in inflacion_series:
        dato = fetch_fred(serie, api_key_fred, nombre, conn)
        if dato:
            (resultados["exitosos"] if dato.es_valido else resultados["fallidos"]).append(nombre)
        else:
            resultados["fallidos"].append(nombre)
 
    # ── 4. FX — MONEDAS (todas desde yfinance — tiempo real) ─────────────────
    log.info("--- Divisas (FX) ---")
    fx_yf = [
        ("DX-Y.NYB",  "dxy"),
        ("USDJPY=X",  "usdjpy"),
        ("EURUSD=X",  "eurusd"),
        ("USDCNY=X",  "usdcny"),
        ("USDBRL=X",  "usdbrl"),
        ("USDMXN=X",  "usdmxn"),
    ]
    for ticker, nombre in fx_yf:
        dato = fetch_yfinance(ticker, nombre, "Close", conn)
        if dato:
            (resultados["exitosos"] if dato.es_valido else resultados["fallidos"]).append(nombre)
        else:
            resultados["fallidos"].append(nombre)
 
    # ── 5. MERCADOS (yfinance) ────────────────────────────────────────────────
    log.info("--- Precios de mercado (yfinance) ---")
    yf_tickers = [
        ("^VIX",  "vix",  "Close"),
        ("SPY",   "spy",  "Close"),
        ("QQQ",   "qqq",  "Close"),
        ("GLD",   "gold", "Close"),
        ("TLT",   "tlt",  "Close"),
        ("^TNX",  "yield_10y_mkt", "Close"),  # confirmación del yield 10Y
        ("USDJPY=X", "usdjpy_mkt", "Close"),  # confirmación USD/JPY
    ]
    for ticker, nombre, campo in yf_tickers:
        dato = fetch_yfinance(ticker, nombre, campo, conn)
        if dato:
            (resultados["exitosos"] if dato.es_valido else resultados["fallidos"]).append(nombre)
        else:
            resultados["fallidos"].append(nombre)
 
    # ── 6. VERIFICACIÓN CRUZADA ───────────────────────────────────────────────
    log.info("--- Verificación cruzada de fuentes ---")
    pares_verificacion = [
        ("yield_10y", "yield_10y_mkt", 0.30),   # tolerancia 30 bps
        ("usdjpy",    "usdjpy_mkt",    1.00),    # tolerancia 1 yen
    ]
    for nombre1, nombre2, tolerancia in pares_verificacion:
        d1 = obtener_ultimo(conn, nombre1)
        d2 = obtener_ultimo(conn, nombre2)
        if d1 and d2:
            diff = abs(d1.valor - d2.valor)
            if diff > tolerancia:
                msg = f"Discrepancia entre {nombre1} ({d1.valor}) y {nombre2} ({d2.valor}): {diff:.3f}"
                registrar_alerta(conn, "WARNING", nombre1, msg)
                resultados["advertencias"].append(msg)
                log.warning(f"⚠ {msg}")
            else:
                log.info(f"✓ Verificación cruzada OK: {nombre1} vs {nombre2} (diff={diff:.3f})")
 
    # ── 7. RÉGIMEN ────────────────────────────────────────────────────────────
    regimen = determinar_regimen_basico(conn)
    log.info(f"\n{'='*60}")
    log.info(f"RÉGIMEN DETECTADO: {regimen['regimen']}")
    for d in regimen["detalle"]:
        log.info(f"  → {d}")
    log.info(f"{'='*60}\n")
 
    resumen = {
        "fecha":        hoy,
        "exitosos":     len(resultados["exitosos"]),
        "fallidos":     len(resultados["fallidos"]),
        "advertencias": len(resultados["advertencias"]),
        "indicadores_fallidos": resultados["fallidos"],
        "regimen": regimen,
        "sistema_operacional": len(resultados["fallidos"]) < 5
    }
 
    conn.close()
    return resumen
 
 
# ── Función de snapshot para el agente ───────────────────────────────────────
def obtener_snapshot(db_path: str = DB_PATH) -> dict:
    """
    Devuelve todos los indicadores más recientes en un dict limpio.
    Este es el input que recibe el agente Claude.
    Incluye flags de freshness para que el agente sepa qué datos son confiables.
    """
    conn = sqlite3.connect(db_path)
    indicadores = {}
 
    nombres = conn.execute(
        "SELECT DISTINCT nombre FROM indicadores"
    ).fetchall()
 
    for (nombre,) in nombres:
        ultimo = obtener_ultimo(conn, nombre)
        if not ultimo:
            continue
 
        es_fresco, dias = verificar_freshness(conn, nombre)
        indicadores[nombre] = {
            "valor":             ultimo.valor,
            "fecha_publicacion": ultimo.fecha_publicacion,
            "fecha_descarga":    ultimo.fecha_descarga,
            "fuente":            ultimo.fuente,
            "es_valido":         ultimo.es_valido,
            "es_fresco":         es_fresco,
            "dias_antiguedad":   dias,
            "nota":              ultimo.nota,
        }
 
    # Régimen actual
    regimen = determinar_regimen_basico(conn)
    conn.close()
 
    return {
        "timestamp_snapshot": datetime.now().isoformat(),
        "indicadores":        indicadores,
        "regimen":            regimen,
        "datos_confiables":   sum(
            1 for v in indicadores.values()
            if v["es_valido"] and v["es_fresco"]
        ),
        "datos_totales": len(indicadores)
    }
 
 
if __name__ == "__main__":
    import os
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        print("ERROR: Necesitás setear la variable FRED_API_KEY")
        print("  export FRED_API_KEY=tu_api_key_de_fred")
        print("  (Gratis en https://fred.stlouisfed.org/docs/api/api_key.html)")
        exit(1)
 
    resumen = correr_colector(api_key)
    print(f"\nResumen: {resumen['exitosos']} exitosos, "
          f"{resumen['fallidos']} fallidos, "
          f"{resumen['advertencias']} advertencias")
    print(f"Régimen: {resumen['regimen']['regimen']}")
 
