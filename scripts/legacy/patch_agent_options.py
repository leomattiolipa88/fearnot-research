"""
Patch para agregar options flow al technical_agent.py.

Hace 3 cambios:
1. Agrega seccion 7 al SYSTEM_PROMPT (interpretacion de options flow)
2. Agrega funcion cargar_options_flow() que lee de la DB
3. Modifica construir_prompt() para incluir options flow en el prompt
"""

import shutil
from pathlib import Path

ARCHIVO = Path.home() / "Desktop" / "macro_agent" / "technical_agent.py"
BACKUP = Path.home() / "Desktop" / "macro_agent" / "technical_agent.py.bak"

if not ARCHIVO.exists():
    print(f"ERROR: No encuentro {ARCHIVO}")
    exit(1)

shutil.copy(ARCHIVO, BACKUP)
print(f"[1/4] Backup en {BACKUP.name}")

contenido = ARCHIVO.read_text()

# ============================================================
# CAMBIO 1: Agregar seccion 7 al system prompt
# ============================================================
seccion_breadth_vieja = """6. BREADTH:
   - >70% sobre 200DMA -> mercado amplio, confirma tendencia
   - 30-70%           -> condiciones normales
   - <30%             -> oversold masivo, contrarian buy en slowdown"""

seccion_breadth_nueva = """6. BREADTH:
   - >70% sobre 200DMA -> mercado amplio, confirma tendencia
   - 30-70%           -> condiciones normales
   - <30%             -> oversold masivo, contrarian buy en slowdown

7. OPTIONS FLOW (term structure expandida + IV percentile):
   VIX 9D vs VIX 6M -> spread mide miedo estructural vs inmediato.
   - Spread > 5      -> miedo estructural mayor al inmediato (alguien se cubre lejos)
   - Spread 0-5      -> term structure normal en contango
   - Spread < 0      -> backwardation completa, stress en todo el espectro

   VIX IV Percentile (1-year) -> donde esta el VIX hoy en su rango anual.
   - <30  -> VIX historicamente bajo, posible complacencia (cuidado en limite)
   - 30-70 -> zona normal
   - >70  -> VIX historicamente alto, fear elevado (contrarian buy en limite)"""

if seccion_breadth_vieja in contenido:
    contenido = contenido.replace(seccion_breadth_vieja, seccion_breadth_nueva)
    print("[2/4] Seccion 7 (options flow) agregada al system prompt")
else:
    print("[2/4] No encontre la seccion 6 exacta. Verificar manualmente.")

# ============================================================
# CAMBIO 2: Agregar funcion cargar_options_flow despues de los imports
# ============================================================
import_anchor = "from technical_collector import obtener_snapshot_tecnico"

funcion_options_flow = """from technical_collector import obtener_snapshot_tecnico


def cargar_options_flow(db_path: str = "data/macro.db") -> dict:
    \"\"\"Lee los indicadores de options flow mas recientes desde la DB.\"\"\"
    import sqlite3
    options_flow = {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(\"\"\"
            SELECT vix_9d, vix_6m, vix_iv_pct, put_call_ratio,
                   vix_rvx_skew, interpretacion, fecha
            FROM indicadores_options_flow
            ORDER BY fecha DESC LIMIT 1
        \"\"\").fetchone()
        if row:
            options_flow = dict(row)
        conn.close()
    except Exception as e:
        print(f"   Aviso: no se pudo cargar options flow: {e}")
    return options_flow"""

if "def cargar_options_flow" not in contenido:
    contenido = contenido.replace(import_anchor, funcion_options_flow)
    print("[3/4] Funcion cargar_options_flow agregada")
else:
    print("[3/4] La funcion ya existe (skip)")

# ============================================================
# CAMBIO 3: Modificar construir_prompt para incluir options flow
# ============================================================
firma_vieja = "def construir_prompt(snapshot_tecnico: dict, regimen_macro: str = \"DESCONOCIDO\") -> str:"
firma_nueva = "def construir_prompt(snapshot_tecnico: dict, regimen_macro: str = \"DESCONOCIDO\", options_flow: dict = None) -> str:"

if firma_vieja in contenido and firma_nueva not in contenido:
    contenido = contenido.replace(firma_vieja, firma_nueva)

# Agregar bloque de options flow al prompt (despues de INDICADORES DE MERCADO)
mercado_anchor = """=== INDICADORES DE MERCADO ===
{json.dumps(snapshot_tecnico['mercado'], indent=2, ensure_ascii=False)}"""

mercado_con_options = """=== INDICADORES DE MERCADO ===
{json.dumps(snapshot_tecnico['mercado'], indent=2, ensure_ascii=False)}

=== OPTIONS FLOW ===
{json.dumps(options_flow, indent=2, ensure_ascii=False) if options_flow else "(Sin data de options flow disponible)"}"""

if mercado_anchor in contenido and "=== OPTIONS FLOW ===" not in contenido:
    contenido = contenido.replace(mercado_anchor, mercado_con_options)

# ============================================================
# CAMBIO 4: Modificar la llamada a construir_prompt para pasar options_flow
# ============================================================
# Buscar donde se llama a construir_prompt y agregar options_flow como argumento
# Es probable que sea algo como: construir_prompt(snapshot, regimen_macro)
# Lo dejamos para chequear despues si hace falta cambio adicional

ARCHIVO.write_text(contenido)
print("[4/4] Archivo actualizado")
print()
print(f"Backup en: {BACKUP.name}")
print()
print("IMPORTANTE: Hay que hacer un cambio mas manual.")
print("Buscar en technical_agent.py donde se llama a construir_prompt")
print("y agregar 'options_flow=cargar_options_flow()' como argumento.")
print()
print("Para verlo:")
print("  grep -n 'construir_prompt(' ~/Desktop/macro_agent/technical_agent.py")
