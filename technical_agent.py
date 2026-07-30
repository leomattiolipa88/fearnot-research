"""
Macro Agent — Technical Agent (Opus 4.7)
Analiza indicadores tecnicos y los combina con el regimen macro
para generar senales tecnicas con conviccion calibrada.

DNA: Tudor Jones + Simons + Barroso & Santa-Clara
Framework: Cooper, Gutierrez & Hameed (2004) — momentum condicionado al regimen
"""

import json
import os
import anthropic
from datetime import datetime
from pathlib import Path
from config import MODEL
from technical_collector import obtener_snapshot_tecnico


def cargar_options_flow(db_path: str = "data/macro.db") -> dict:
    """Lee los indicadores de options flow mas recientes desde la DB."""
    import sqlite3
    options_flow = {}
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT vix_9d, vix_6m, vix_iv_pct, put_call_ratio,
                   vix_rvx_skew, interpretacion, fecha
            FROM indicadores_options_flow
            ORDER BY fecha DESC LIMIT 1
        """).fetchone()
        if row:
            options_flow = dict(row)
        conn.close()
    except Exception as e:
        print(f"   Aviso: no se pudo cargar options flow: {e}")
    return options_flow
from tracker import registrar_senales, init_tracker


# ----------------- Cliente Anthropic -----------------
def get_client():
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("Necesitas setear ANTHROPIC_API_KEY")
    return anthropic.Anthropic(api_key=api_key)


# ----------------- System Prompt -----------------
SYSTEM_PROMPT = """Sos un quant trader senior con DNA de Tudor Jones y Jim Simons.
Tu trabajo es analizar indicadores tecnicos y cuantitativos con evidencia empirica real,
y generar senales tecnicas integradas con el regimen macro actual.

REGLAS ANTI-ALUCINACION (no negociables):
1. Solo podes hacer afirmaciones sobre datos que esten en el JSON que recibis.
2. Cada afirmacion numerica debe citar el indicador. Ejemplo: "momentum 12M en +36.4% (momentum_12m)".
3. Si un dato no esta en el snapshot, decilo explicitamente. No inventes valores.
4. Nunca predecis precios especificos. Solo direccion (LONG/SHORT/NEUTRAL) y horizonte.

FRAMEWORK DE ANALISIS (basado en evidencia empirica):

1. REGLA UNIVERSAL DE TUDOR JONES:
   - Si precio SOBRE 200DMA -> zona habilitada para LONG
   - Si precio BAJO 200DMA  -> zona prohibida, NUNCA LONG
   - CRUCE_ALCISTA = senal de compra mas fuerte
   - CRUCE_BAJISTA = salir sin excepciones

2. MOMENTUM AJUSTADO POR VOLATILIDAD (Barroso & Santa-Clara 2015):
   - Mom/Vol > +1.5   -> momentum fuerte, senal LONG con alta conviccion
   - Mom/Vol entre -0.5 y +1.5 -> senal ambigua, NEUTRAL o baja conviccion
   - Mom/Vol < -0.5   -> momentum bajista, SHORT si precio tambien bajo 200DMA

3. CONDICIONAMIENTO POR REGIMEN MACRO (Cooper, Gutierrez, Hameed 2004):
   CRITICO: momentum CAMBIA DE SIGNO segun el regimen.
   - GOLDILOCKS  -> momentum full sizing (UP market, +0.93%/mes)
   - REFLACION   -> commodity momentum + carry preferidos
   - DESACELERACION -> REDUCIR momentum 50%, riesgo de crash
   - STAGFLATION -> solo trend-following en real assets (GLD, USO), evitar equity momentum

4. VIX TERM STRUCTURE:
   - CONTANGO_NORMAL o FUERTE -> condiciones normales, operar con normalidad
   - BACKWARDATION            -> stress agudo, reducir risk-on

5. VARIANCE RISK PREMIUM (Bollerslev et al. 2009):
   - VRP positivo -> seguro sobrepagado, bullish para equities
   - VRP negativo -> complacencia, bearish

6. BREADTH:
   - >70% sobre 200DMA -> mercado amplio, confirma tendencia
   - 30-70%           -> condiciones normales
   - <30%             -> oversold masivo, contrarian buy en slowdown

7. OPTIONS FLOW (term structure expandida + IV percentile):
   OBLIGATORIO: tu contexto_tecnico_global DEBE mencionar explicitamente:
   (a) el spread VIX 9D vs VIX 6M y que indica
   (b) el VIX IV percentile (1-year) y donde esta posicionado
   Estos son indicadores nuevos del fondo, criticos para diferenciar miedo
   inmediato vs estructural. Si no los mencionas, el output esta incompleto.

   VIX 9D vs VIX 6M -> spread mide miedo estructural vs inmediato.
   - Spread > 5      -> miedo estructural mayor al inmediato (alguien se cubre lejos)
   - Spread 0-5      -> term structure normal en contango
   - Spread < 0      -> backwardation completa, stress en todo el espectro

   VIX IV Percentile (1-year) -> donde esta el VIX hoy en su rango anual.
   - <30  -> VIX historicamente bajo, posible complacencia (cuidado en limite)
   - 30-70 -> zona normal
   - >70  -> VIX historicamente alto, fear elevado (contrarian buy en limite)

   Cuando ambos signals divergen (ej: IV percentile bajo pero spread 9D-6M alto),
   eso es informacion. Mencionalo en tu contexto.

ESCALA DE CONVICCION:
- 8-10: Multiples senales alineadas, regimen claro, cruce reciente
- 5-7:  Senales mixtas o ambiguas
- 1-4:  Senales contradictorias o datos insuficientes

Tu output debe ser JSON valido con la estructura exacta indicada."""


# ----------------- Construir prompt -----------------
def construir_prompt(snapshot_tecnico: dict, regimen_macro: str = "DESCONOCIDO", options_flow: dict = None) -> str:
    """Construye el prompt con datos tecnicos + regimen macro."""

    prompt = f"""Fecha de analisis: {snapshot_tecnico['timestamp']}

=== REGIMEN MACRO ACTUAL (del agente macro) ===

Regimen detectado: {regimen_macro}

Este regimen condiciona TODA tu interpretacion de las senales tecnicas.
Recorda: Cooper et al. 2004 - momentum solo funciona en UP markets.

=== INDICADORES TECNICOS POR ACTIVO ===

{json.dumps(snapshot_tecnico['activos'], indent=2, ensure_ascii=False)}

=== INDICADORES DE MERCADO ===

{json.dumps(snapshot_tecnico['mercado'], indent=2, ensure_ascii=False)}

=== OPTIONS FLOW ===
{json.dumps(options_flow, indent=2, ensure_ascii=False) if options_flow else "(Sin data de options flow disponible)"}

=== TU TAREA ===

Analiza estos datos aplicando el framework del system prompt.
Generas senales tecnicas para cada activo. Responde UNICAMENTE con este JSON:

{{
  "fecha": "YYYY-MM-DD",
  "regimen_macro_aplicado": "{regimen_macro}",
  "contexto_tecnico_global": "3-4 oraciones sobre el estado tecnico del mercado. DEBE incluir: VIX spot/3M term structure, VRP, breadth, Y TAMBIEN VIX 9D vs VIX 6M spread + VIX IV percentile (indicadores de options flow)",
  "senales": [
    {{
      "activo": "SPY|QQQ|GLD|TLT|USO|DXY",
      "direccion": "LONG|SHORT|NEUTRAL",
      "horizonte": "SEMANAL|MENSUAL|TRIMESTRAL",
      "conviccion": 1-10,
      "razonamiento": "explicacion citando indicadores especificos (200DMA, momentum, vol)",
      "indicador_clave": "cual indicador domina la senal",
      "interaccion_macro": "como el regimen macro {regimen_macro} modifica esta senal"
    }}
  ],
  "alertas_tecnicas": [
    "cruces recientes, sobreextensiones, o divergencias importantes"
  ],
  "invalidadores_tecnicos": [
    "que tendria que pasar tecnicamente para invalidar estas senales (3-5 puntos)"
  ],
  "confianza_general": 0-100
}}"""

    return prompt


# ----------------- Validador -----------------
def validar_tesis_tecnica(tesis: dict) -> tuple[bool, list, list]:
    """
    Valida que el output del agente sea consistente.

    Returns:
        es_valida: True si NO hubo errores en toda la tesis.
        errores: lista de strings con cada error encontrado.
        senales_validas: lista de señales que pasaron TODOS los chequeos
            de campos (activo, conviccion, direccion). Las malformadas
            se descartan acá para que no rompan tracker ni print.
    """
    errores = []
    senales_validas = []

    activos_validos = {"SPY", "QQQ", "GLD", "TLT", "USO", "DXY"}
    for senal in tesis.get("senales", []):
        errores_senal = []

        if senal.get("activo") not in activos_validos:
            errores_senal.append(f"Activo invalido: {senal.get('activo')}")
        conv = senal.get("conviccion", 0)
        if not (1 <= conv <= 10):
            errores_senal.append(f"Conviccion fuera de rango: {conv}")
        if senal.get("direccion") not in {"LONG", "SHORT", "NEUTRAL"}:
            errores_senal.append(f"Direccion invalida: {senal.get('direccion')}")

        horizonte = senal.get("horizonte")
        if horizonte is None:
            errores_senal.append(f"Senal {senal.get('activo')}: falta campo 'horizonte'")
        elif horizonte not in {"SEMANAL", "MENSUAL", "TRIMESTRAL"}:
            errores_senal.append(f"Horizonte invalido en {senal.get('activo')}: {horizonte}")

        errores.extend(errores_senal)
        if not errores_senal:
            senales_validas.append(senal)

    if not (0 <= tesis.get("confianza_general", 50) <= 100):
        errores.append("confianza_general fuera de rango 0-100")

    if len(tesis.get("invalidadores_tecnicos", [])) < 2:
        errores.append("Necesita al menos 2 invalidadores tecnicos")

    return len(errores) == 0, errores, senales_validas


# ----------------- Leer regimen macro -----------------
def leer_regimen_macro() -> str:
    """Lee el regimen macro del ultimo archivo de tesis generado."""
    fecha = datetime.now().strftime("%Y-%m-%d")
    archivo = f"data/tesis_{fecha}.json"
    try:
        with open(archivo, encoding="utf-8") as f:
            tesis_macro = json.load(f)
        return tesis_macro.get("regimen", {}).get("clasificacion", "DESCONOCIDO")
    except Exception:
        # Si no existe, buscar el mas reciente
        try:
            data_dir = Path("data")
            tesis_files = sorted(
                [f for f in data_dir.glob("tesis_*.json")
                 if "tecnica" not in f.name and "og" not in f.name],
                reverse=True
            )
            if tesis_files:
                with open(tesis_files[0], encoding="utf-8") as f:
                    return json.load(f).get("regimen", {}).get("clasificacion", "DESCONOCIDO")
        except Exception:
            pass
        return "DESCONOCIDO"


# ----------------- Funcion principal -----------------
def correr_agente_tecnico(db_path: str = "data/macro.db",
                          max_reintentos: int = 2) -> dict:
    """Corre el agente tecnico completo."""
    print("=" * 60)
    print(f"Agente tecnico (Opus 4.7) iniciado: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Paso 1: Snapshot tecnico
    print("\n[1/4] Obteniendo snapshot tecnico...")
    snapshot = obtener_snapshot_tecnico(db_path)
    print(f"      Activos: {len(snapshot['activos'])}")
    print(f"      VIX: {snapshot['mercado'].get('vix_spot')} | "
          f"Breadth: {snapshot['mercado'].get('pct_sobre_200')}%")

    if len(snapshot["activos"]) < 3:
        return {"error": "Datos tecnicos insuficientes - corre technical_collector.py primero"}

    # Paso 2: Leer regimen macro
    print("\n[2/4] Leyendo regimen macro del agente macro...")
    regimen_macro = leer_regimen_macro()
    print(f"      Regimen aplicado: {regimen_macro}")

    # Paso 3: Llamar a Opus 4.7
    print("\n[3/4] Llamando a Claude Opus 4.7...")
    prompt = construir_prompt(snapshot, regimen_macro, options_flow=cargar_options_flow())
    client = get_client()
    tesis = None

    for intento in range(max_reintentos + 1):
        if intento > 0:
            print(f"      Reintento {intento}/{max_reintentos}...")
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=3000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            texto = response.content[0].text.strip()
            if texto.startswith("```"):
                texto = texto.split("```")[1]
                if texto.startswith("json"):
                    texto = texto[4:]
            tesis = json.loads(texto)
            print("      Respuesta recibida y parseada correctamente")
            break
        except json.JSONDecodeError as e:
            print(f"      Error parseando JSON: {e}")
            if intento == max_reintentos:
                return {"error": f"No se pudo parsear: {e}"}
        except Exception as e:
            print(f"      Error: {e}")
            return {"error": str(e)}

    # Paso 4: Validar
    print("\n[4/4] Validando tesis tecnica...")
    es_valida, errores, senales_validas = validar_tesis_tecnica(tesis)

    # Reemplazar las señales del dict con las filtradas para evitar
    # que señales malformadas lleguen a imprimir/tracker y rompan
    # con KeyError.
    senales_descartadas = len(tesis.get("senales", [])) - len(senales_validas)
    tesis["senales"] = senales_validas

    if not es_valida:
        print(f"      Advertencias: {errores}")
        if senales_descartadas:
            print(f"      {senales_descartadas} señales malformadas descartadas")
        tesis["advertencias_validacion"] = errores
    else:
        print("      Tesis validada correctamente")

    tesis["metadata"] = {
        "timestamp": datetime.now().isoformat(),
        "modelo": MODEL,
        "activos_analizados": len(snapshot["activos"]),
        "regimen_macro": regimen_macro,
    }
    return tesis


# ----------------- Imprimir tesis -----------------
def imprimir_tesis_tecnica(tesis: dict):
    if "error" in tesis:
        print(f"\nError: {tesis['error']}")
        return

    print("\n" + "=" * 60)
    print("TESIS TECNICA DEL DIA (Opus 4.7)")
    print("=" * 60)

    print(f"\nRegimen macro aplicado: {tesis.get('regimen_macro_aplicado')}")
    print(f"\nContexto tecnico global:")
    print(f"   {tesis.get('contexto_tecnico_global', '')}")

    print(f"\nSENALES TECNICAS:")
    for s in tesis.get("senales", []):
        emoji = "[LONG]" if s["direccion"] == "LONG" else "[SHORT]" if s["direccion"] == "SHORT" else "[NEUT]"
        print(f"\n   {emoji} {s['activo']:6s} | Horizonte: {s['horizonte']:10s} "
              f"| Conviccion: {s['conviccion']}/10")
        print(f"      {s['razonamiento']}")
        print(f"      Indicador clave: {s.get('indicador_clave', '')}")
        print(f"      Interaccion macro: {s.get('interaccion_macro', '')}")

    alertas = tesis.get("alertas_tecnicas", [])
    if alertas:
        print(f"\nALERTAS TECNICAS:")
        for a in alertas:
            print(f"   -> {a}")

    print(f"\nINVALIDADORES TECNICOS:")
    for i, inv in enumerate(tesis.get("invalidadores_tecnicos", []), 1):
        print(f"   {i}. {inv}")

    print(f"\nCONFIANZA GENERAL: {tesis.get('confianza_general')}%")
    print("=" * 60)


# ----------------- Main -----------------
if __name__ == "__main__":
    tesis = correr_agente_tecnico()
    imprimir_tesis_tecnica(tesis)

    # Guardar tesis tecnica
    fecha = datetime.now().strftime("%Y-%m-%d")
    archivo = f"data/tesis_tecnica_{fecha}.json"
    Path("data").mkdir(parents=True, exist_ok=True)
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(tesis, f, indent=2, ensure_ascii=False)
    print(f"\nTesis tecnica guardada en: {archivo}")

    # Registrar senales en el tracker (fuente: technical)
    if "error" not in tesis and tesis.get("senales"):
        tesis["fuente"] = "technical"
        registrar_senales(tesis)
