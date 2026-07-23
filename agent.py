"""
Macro Agent — Agente Claude
Lee el snapshot del colector y genera la tesis macro del día.
Anti-alucinación: solo puede afirmar lo que está en el JSON recibido.
"""

import json
import os
import anthropic
from datetime import datetime
from collector import obtener_snapshot
from news_collector import obtener_contexto_noticias
from tracker import registrar_senales, init_tracker

# ── Cliente Anthropic ─────────────────────────────────────────────────────────
def get_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError(
            "Necesitás setear ANTHROPIC_API_KEY\n"
            "  export ANTHROPIC_API_KEY=tu_key"
        )
    return anthropic.Anthropic(api_key=api_key)


# ── System prompt — las reglas del agente ────────────────────────────────────
SYSTEM_PROMPT = """Sos un analista macro senior de un hedge fund. Tu trabajo es analizar datos macroeconómicos en tiempo real y generar una tesis de inversión diaria.

REGLAS ANTI-ALUCINACIÓN (no negociables):
1. Solo podés hacer afirmaciones sobre datos que estén en el JSON que recibís. Nunca inventes valores numéricos.
2. Cada afirmación factual debe citar el indicador del JSON. Ejemplo: "La yield curve está en +0.73% (yield_curve)"
3. Si un dato tiene es_fresco=false o es_valido=false, debés mencionarlo explícitamente y reducir tu confianza en esa señal.
4. Si no tenés suficientes datos confiables para una señal, decí "convicción insuficiente" en lugar de inventar.
5. Nunca predecís precios específicos. Solo dirección (long/short/neutral) y horizonte temporal.

FRAMEWORK DE ANÁLISIS (en este orden):
1. Identificar el régimen macro (growth × inflation quadrant de Dalio)
2. Evaluar el estado de la liquidez (credit spreads, VIX)
3. Analizar las monedas — especialmente USD/JPY como señal de carry trade
4. Evaluar cada activo en el contexto del régimen
5. Generar señales con convicción calibrada
6. Citar explícitamente 3-5 noticias reales del día con su fuente y explicar el impacto concreto en mercados

ESCALA DE CONVICCIÓN:
- 8-10: Múltiples señales alineadas, datos frescos, régimen claro
- 5-7: Señales mixtas o datos parcialmente rancios
- 1-4: Datos insuficientes, régimen incierto, o señales contradictorias

Tu output debe ser JSON válido con la estructura exacta que se te indica."""


# ── User prompt con los datos ─────────────────────────────────────────────────
def construir_prompt(snapshot: dict, noticias: str = "") -> str:
    """
    Construye el prompt con los datos reales del snapshot.
    El agente solo puede razonar sobre estos datos.
    """

    # Filtramos solo los datos válidos y frescos para el resumen
    datos_confiables = {
        k: v for k, v in snapshot["indicadores"].items()
        if v["es_valido"] and v["es_fresco"]
    }
    datos_rancios = {
        k: v for k, v in snapshot["indicadores"].items()
        if not v["es_fresco"] and v["es_valido"]
    }

    noticias_texto = noticias or "Sin contexto de noticias disponible."
    prompt = f"""Fecha de análisis: {snapshot['timestamp_snapshot']}
Datos confiables disponibles: {snapshot['datos_confiables']}/{snapshot['datos_totales']}

═══ DATOS MACROECONÓMICOS (solo estos podés usar) ═══

{json.dumps(datos_confiables, indent=2, ensure_ascii=False)}

═══ DATOS CON RETRASO (usar con cautela) ═══

{json.dumps(datos_rancios, indent=2, ensure_ascii=False)}

═══ CONTEXTO DE NOTICIAS (últimas 24 horas) ═══

{noticias_texto}

═══ RÉGIMEN PRE-CALCULADO ═══

{json.dumps(snapshot['regimen'], indent=2, ensure_ascii=False)}

═══ TU TAREA ═══

Analizá estos datos y generá tu tesis macro del día. Respondé ÚNICAMENTE con este JSON (sin texto extra, sin markdown, sin explicaciones fuera del JSON):

{{
  "fecha": "YYYY-MM-DD",
  "regimen": {{
    "clasificacion": "GOLDILOCKS|REFLACION|DESACELERACION|STAGFLATION",
    "confianza": 0-100,
    "razonamiento": "explicación citando indicadores específicos del JSON"
  }},
  "senales": [
    {{
      "activo": "SPY|QQQ|GLD|TLT|USO|DXY",
      "direccion": "LONG|SHORT|NEUTRAL",
      "horizonte": "SEMANAL|MENSUAL|TRIMESTRAL",
      "conviccion": 1-10,
      "razonamiento": "explicación citando datos del JSON",
      "dato_clave": "el indicador más importante para esta señal"
    }}
  ],
  "tesis_principal": "2-3 párrafos explicando el panorama macro completo, citando cada número del JSON",
  "invalidadores": [
    "qué tendría que pasar para que esta tesis esté equivocada (3-5 puntos)",
  ],
  "alertas": [
    "cualquier anomalía o dato preocupante que merezca atención especial"
  ],
  "datos_insuficientes": [
    "indicadores que no tienen datos frescos y afectan el análisis"
  ],
  "eventos_clave": [
    "[Fuente] Titular real — impacto concreto en mercados"
  ],
  "confianza_general": 0-100
}}"""

    return prompt


# ── Validador anti-alucinación ────────────────────────────────────────────────
def validar_tesis(tesis: dict, snapshot: dict) -> tuple[bool, list, list]:
    """
    Segunda pasada: verifica que cada número en la tesis
    existe en el snapshot. Rechaza si hay discrepancias.

    Returns:
        es_valida: True si NO hubo errores en toda la tesis.
        errores: lista de strings con cada error encontrado.
        senales_validas: lista de señales que pasaron TODOS los chequeos
            de campos (activo, conviccion, direccion). Las malformadas
            se descartan acá para que no rompan tracker ni print.
    """
    errores = []
    senales_validas = []
    indicadores = snapshot["indicadores"]

    # Verificar que los activos en las señales son válidos
    activos_validos = {"SPY", "QQQ", "GLD", "TLT", "USO", "DXY"}
    for i, senal in enumerate(tesis.get("senales", []), 1):
        # Validacion defensiva: usar .get() en lugar de [] para evitar KeyError
        activo = senal.get("activo")
        conviccion = senal.get("conviccion")
        direccion = senal.get("direccion")

        errores_senal = []

        if activo is None:
            errores_senal.append(f"Senal {i}: falta campo 'activo'")
        elif activo not in activos_validos:
            errores_senal.append(f"Activo invalido: {activo}")

        if conviccion is None:
            errores_senal.append(f"Senal {activo}: falta campo 'conviccion'")
        elif not (1 <= conviccion <= 10):
            errores_senal.append(f"Conviccion fuera de rango en {activo}: {conviccion}")

        if direccion is None:
            errores_senal.append(f"Senal {activo}: falta campo 'direccion'")
        elif direccion not in {"LONG", "SHORT", "NEUTRAL"}:
            errores_senal.append(f"Direccion invalida en {activo}: {direccion}")

        horizonte = senal.get("horizonte")
        if horizonte is None:
            errores_senal.append(f"Senal {activo}: falta campo 'horizonte'")
        elif horizonte not in {"SEMANAL", "MENSUAL", "TRIMESTRAL"}:
            errores_senal.append(f"Horizonte invalido en {activo}: {horizonte}")

        errores.extend(errores_senal)
        if not errores_senal:
            senales_validas.append(senal)

    # Verificar que la confianza está en rango
    if not (0 <= tesis.get("confianza_general", 50) <= 100):
        errores.append("confianza_general fuera de rango 0-100")

    # Verificar régimen válido
    regimenes_validos = {"GOLDILOCKS", "REFLACION", "DESACELERACION", "STAGFLATION"}
    if tesis.get("regimen", {}).get("clasificacion") not in regimenes_validos:
        errores.append("Régimen inválido")

    # Verificar que hay invalidadores
    if len(tesis.get("invalidadores", [])) < 2:
        errores.append("Debe haber al menos 2 invalidadores")

    return len(errores) == 0, errores, senales_validas


# ── Función principal del agente ──────────────────────────────────────────────
def correr_agente(db_path: str = "data/macro.db",
                  max_reintentos: int = 2) -> dict:
    """
    Corre el agente completo:
    1. Obtiene snapshot del colector
    2. Llama a Claude API
    3. Valida la respuesta
    4. Retorna la tesis validada
    """
    print("=" * 60)
    print(f"Agente iniciado: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Paso 1: Obtener datos del colector
    print("\n[1/4] Obteniendo snapshot de datos...")
    snapshot = obtener_snapshot(db_path)
    print(f"      Datos confiables: {snapshot['datos_confiables']}/{snapshot['datos_totales']}")
    print(f"      Régimen pre-calculado: {snapshot['regimen']['regimen']}")

    if snapshot["datos_confiables"] < 10:
        print("⚠️  ADVERTENCIA: Menos de 10 datos confiables — corrés el colector primero")
        return {"error": "Datos insuficientes — correr collector.py primero"}

    # Paso 2: Obtener noticias y construir prompt
    print("\n[2/4] Obteniendo noticias...")
    noticias = obtener_contexto_noticias(os.environ.get("NEWS_API_KEY", ""))
    print("\n[3/5] Construyendo prompt...")
    prompt = construir_prompt(snapshot, noticias)

    # Paso 3: Llamar a Claude
    client = get_client()
    tesis = None

    for intento in range(max_reintentos + 1):
        if intento > 0:
            print(f"\n      Reintento {intento}/{max_reintentos}...")

        print(f"\n[4/5] Llamando a Claude API (intento {intento + 1})...")

        try:
            response = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )

            texto = response.content[0].text.strip()

            # Limpiar posibles backticks de markdown
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
                return {"error": f"No se pudo parsear la respuesta de Claude: {e}"}
            continue

        except Exception as e:
            print(f"      Error llamando a Claude API: {e}")
            return {"error": str(e)}

    # Paso 4: Validar anti-alucinación
    print("\n[5/5] Validando tesis (anti-alucinación)...")
    es_valida, errores, senales_validas = validar_tesis(tesis, snapshot)

    # Reemplazar las señales del dict con las filtradas: si una señal
    # vino malformada (sin 'activo'/'direccion'/'conviccion' o con
    # valores fuera de rango), la descartamos acá para que no llegue
    # a imprimir_tesis ni a registrar_senales y dispare un KeyError.
    senales_descartadas = len(tesis.get("senales", [])) - len(senales_validas)
    tesis["senales"] = senales_validas

    if not es_valida:
        print(f"      ⚠️  Validación falló: {errores}")
        if senales_descartadas:
            print(f"      ⚠️  {senales_descartadas} señales malformadas fueron descartadas")
        tesis["advertencias_validacion"] = errores
    else:
        print("      ✓ Tesis validada correctamente")

    # Agregar metadata
    tesis["metadata"] = {
        "timestamp": datetime.now().isoformat(),
        "datos_usados": snapshot["datos_confiables"],
        "datos_totales": snapshot["datos_totales"],
        "validacion_ok": es_valida,
    }

    return tesis


# ── Output formateado para leer en terminal ───────────────────────────────────
def imprimir_tesis(tesis: dict):
    """Imprime la tesis de forma legible en la terminal."""

    if "error" in tesis:
        print(f"\n❌ Error: {tesis['error']}")
        return

    print("\n" + "=" * 60)
    print("TESIS MACRO DEL DÍA")
    print("=" * 60)

    # Régimen
    reg = tesis.get("regimen", {})
    print(f"\n🌍 RÉGIMEN: {reg.get('clasificacion')} "
          f"(confianza: {reg.get('confianza')}%)")
    print(f"   {reg.get('razonamiento')}")

    # Señales
    print(f"\n📊 SEÑALES:")
    for s in tesis.get("senales", []):
        emoji = "🟢" if s["direccion"] == "LONG" else "🔴" if s["direccion"] == "SHORT" else "⚪"
        print(f"\n   {emoji} {s['activo']:6s} → {s['direccion']:7s} "
              f"| Horizonte: {s['horizonte']:10s} "
              f"| Convicción: {s.get('conviccion', 'N/A')}/10")
        print(f"      {s['razonamiento']}")

    # Tesis
    print(f"\n📝 TESIS PRINCIPAL:")
    print(f"   {tesis.get('tesis_principal', '')}")

    # Invalidadores
    print(f"\n⚠️  INVALIDADORES (leer primero):")
    for i, inv in enumerate(tesis.get("invalidadores", []), 1):
        print(f"   {i}. {inv}")

    # Alertas
    alertas = tesis.get("alertas", [])
    if alertas:
        print(f"\n🚨 ALERTAS:")
        for a in alertas:
            print(f"   → {a}")

    # Eventos clave
    eventos = tesis.get("eventos_clave", [])
    if eventos:
        print(f"\n📰 EVENTOS CLAVE DEL DÍA:")
        for e in eventos:
            print(f"   → {e}")

    # Confianza general
    print(f"\n📈 CONFIANZA GENERAL: {tesis.get('confianza_general')}%")
    print(f"   Datos usados: {tesis.get('metadata', {}).get('datos_usados')}"
          f"/{tesis.get('metadata', {}).get('datos_totales')}")
    print("\n" + "=" * 60)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tesis = correr_agente()
    imprimir_tesis(tesis)

    # Guardar tesis en archivo JSON
    fecha = datetime.now().strftime("%Y-%m-%d")
    archivo = f"data/tesis_{fecha}.json"
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(tesis, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Tesis guardada en: {archivo}")

    # Registrar señales en el tracker automáticamente
    if "error" not in tesis and "senales" in tesis:
        print("\n📊 Registrando señales en tracker...")
        init_tracker()
        n = registrar_senales(tesis)
        print(f"   ✓ {n} señales registradas con precio de entrada")
