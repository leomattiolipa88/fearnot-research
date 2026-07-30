"""
FearNot - O&G + LPG Agent (Sonnet 4.6)

Head trader del energy desk. DNA Trafigura.
Lee data sectorial (precios, spreads, EIA, noticias) + tesis macro y tecnica.
Genera memo sectorial energetico que sirve de INPUT al Synthesizer.

NO es el Synthesizer. NO genera convicciones finales.
Genera regimen fisico clasificado por producto (Oil, Natural Gas, LPG)
y senales por activo.
"""

import json
import os
import sqlite3
import anthropic
from datetime import datetime, date, timedelta
from pathlib import Path
from config import MODEL
from tracker import registrar_senales

DB_PATH = "data/macro.db"


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
SYSTEM_PROMPT = """Sos el head trader del energy desk de Asymmetric Global Macro Fund. Tu DNA es Trafigura - una de las trading houses mas sofisticadas del mundo en oil, gas y LPG.

Tu trabajo:
- LEER tu propia data sectorial (precios, spreads, inventarios EIA, noticias)
- LEER las tesis macro y tecnica del fondo (regimen, indicadores)
- GENERAR un memo sectorial energetico con regimen fisico clasificado y senales por activo

NO sos el Synthesizer. NO generas convicciones finales. Tu output es un INPUT para el Synthesizer.

REGLAS NO NEGOCIABLES:

1. ANTI-HALLUCINATION ESTRICTO. Solo afirma cosas que esten en tus inputs. Si necesitas un dato que no tenes (Saudi CP exacto, freight rates especificos, FEI Asia), decilo: "no tengo ese dato".

2. PIENSA EN TERMINOS FISICOS, NO ESPECULATIVOS.
   - Backwardation = tightness fisica real
   - Crack spreads = demanda real de productos refinados
   - EIA inventories = balance fisico oferta/demanda
   - El precio puede mentir corto plazo, los flujos fisicos no.

3. CONTEXTO MACRO IMPORTA. Lee la tesis macro. Si estamos en GOLDILOCKS, demanda energetica sostenida. Si estamos en RECESION PROXIMA, demanda colapsa. Tu lectura sectorial debe ser coherente con el regimen macro.

4. CONTRADICCIONES SON SENALES. Si los precios suben pero los inventarios crecen, algo no encaja. Si el crack spread es alto pero la utilizacion de refinerias baja, hay disrupcion operacional. Identifica estas contradicciones - son donde estan las oportunidades.

5. ESPECIFICA POR PRODUCTO. Oil, Natural Gas, LPG tienen dinamicas distintas. No promedies. Da regimen especifico para cada uno. Si tenes data limitada para LPG, decilo explicitamente en el razonamiento del regimen LPG.

6. EVENTOS GEOPOLITICOS PESAN. Iran, Russia, OPEC decisions, Middle East tensions cambian la oferta global en cuestion de dias. Las noticias son input critico, no decoracion.

PROCESO MENTAL OBLIGATORIO:

Paso 1: Lee el regimen macro y tecnico actual.
Paso 2: Analiza inventarios EIA - estan en draw o build? Versus 5-year average si tenes contexto.
Paso 3: Analiza curva de futuros - backwardation o contango? Que dice fisicamente?
Paso 4: Analiza crack spreads - demanda real fuerte o debil?
Paso 5: Lee las noticias por categoria. Identifica los 3-5 eventos clave de la semana.
Paso 6: Clasifica regimen para Oil, Natural Gas, LPG.
Paso 7: Genera senales por activo (los 13 que trackeamos).
Paso 8: Identifica invalidadores especificos.

ESTRUCTURA DEL OUTPUT (JSON estricto):

{
  "fecha": "YYYY-MM-DD",
  "regimen_oil": {
    "clasificacion": "TIGHT_BACKWARDATED | BALANCED | OVERSUPPLIED_CONTANGO",
    "confianza": 0-100,
    "razonamiento": "STRING explicando fisicamente"
  },
  "regimen_natgas": {
    "clasificacion": "TIGHT | BALANCED | OVERSUPPLIED",
    "confianza": 0-100,
    "razonamiento": "STRING"
  },
  "regimen_lpg": {
    "clasificacion": "TIGHT | BALANCED | OVERSUPPLIED",
    "confianza": 0-100,
    "razonamiento": "STRING - reconocer si tenes data limitada"
  },
  "tesis_principal": "STRING - 2-3 parrafos integrando todo",
  "senales": [
    {
      "activo": "WTI|BRENT|NATGAS|GASOLINA|HEATING_OIL|XOM|CVX|OXY|VLO|EOG|VIST|XLE|CRAK",
      "direccion": "LONG|SHORT|NEUTRAL",
      "conviccion": 1-10,
      "razonamiento": "STRING - cita data especifica"
    }
  ],
  "eventos_clave": ["evento 1", "evento 2", "evento 3", "evento 4", "evento 5"],
  "contradicciones_observadas": "STRING - dislocaciones interesantes que viste",
  "invalidadores": ["punto 1", "punto 2", "punto 3"],
  "data_gaps": "STRING - que datos te faltan para mejor analisis"
}

CALIBRACION DE CONVICCION:
- 1-3: NEUTRAL real, sin direccion clara
- 4-5: Lean direccional debil
- 6-7: Direccion clara con multiple data points
- 8-9: Setup fuerte, multiples factores alineados
- 10: Convergencia excepcional - raro

Si dudas entre dos niveles, elegi el menor. Mejor under-promise."""


# ----------------- Cargar inputs -----------------
def cargar_inputs() -> dict:
    """Carga toda la data necesaria para el agente."""
    data_dir = Path("data")
    inputs = {
        "fecha_analisis": date.today().isoformat(),
        "tesis_macro": None,
        "tesis_tecnica": None,
        "precios_og": {},
        "spreads_og": {},
        "indicadores_eia": {},
        "noticias_og": {},
    }

    # Tesis macro mas reciente
    tesis_macro_files = sorted(
        [f for f in data_dir.glob("tesis_2*.json") if "tecnica" not in f.name],
        reverse=True,
    )
    if tesis_macro_files:
        try:
            with open(tesis_macro_files[0], encoding="utf-8") as f:
                inputs["tesis_macro"] = json.load(f)
        except Exception as e:
            print(f"   Error leyendo tesis macro: {e}")

    # Tesis tecnica mas reciente
    tesis_tec_files = sorted(data_dir.glob("tesis_tecnica_*.json"), reverse=True)
    if tesis_tec_files:
        try:
            with open(tesis_tec_files[0], encoding="utf-8") as f:
                inputs["tesis_tecnica"] = json.load(f)
        except Exception as e:
            print(f"   Error leyendo tesis tecnica: {e}")

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # Precios OG mas recientes por activo
        for row in conn.execute("""
            SELECT activo, ticker, precio, fecha
            FROM precios_og
            WHERE fecha = (SELECT MAX(fecha) FROM precios_og)
        """):
            inputs["precios_og"][row["activo"]] = {
                "ticker": row["ticker"],
                "precio": row["precio"],
                "fecha": row["fecha"],
            }

        # Spreads mas recientes
        for row in conn.execute("""
            SELECT tipo, valor, interpretacion, fecha
            FROM spreads_og
            WHERE fecha = (SELECT MAX(fecha) FROM spreads_og)
        """):
            inputs["spreads_og"][row["tipo"]] = {
                "valor": row["valor"],
                "interpretacion": row["interpretacion"],
                "fecha": row["fecha"],
            }

        # Indicadores EIA mas recientes
        for row in conn.execute("""
            SELECT nombre, valor, fecha_publicacion, descripcion
            FROM indicadores_eia
            WHERE id IN (
                SELECT MAX(id) FROM indicadores_eia GROUP BY nombre
            )
        """):
            inputs["indicadores_eia"][row["nombre"]] = {
                "valor": row["valor"],
                "fecha": row["fecha_publicacion"],
                "descripcion": row["descripcion"],
            }

        # Noticias por categoria (ultimas 24hs)
        ayer = (datetime.now() - timedelta(hours=36)).isoformat()
        for row in conn.execute("""
            SELECT categoria, titulo, descripcion, fuente, published_at
            FROM noticias_og
            WHERE fecha_descarga >= ?
            ORDER BY published_at DESC
            LIMIT 50
        """, (ayer,)):
            cat = row["categoria"]
            if cat not in inputs["noticias_og"]:
                inputs["noticias_og"][cat] = []
            inputs["noticias_og"][cat].append({
                "titulo": row["titulo"],
                "descripcion": row["descripcion"],
                "fuente": row["fuente"],
                "published_at": row["published_at"],
            })

        conn.close()
    except Exception as e:
        print(f"   Error leyendo DB: {e}")

    return inputs


# ----------------- Construir prompt -----------------
def construir_prompt(inputs: dict) -> str:
    # Resumen condensado de tesis macro
    tesis_macro_resumen = "Sin tesis macro disponible"
    if inputs["tesis_macro"]:
        tm = inputs["tesis_macro"]
        regimen = tm.get("regimen", {})
        tesis_macro_resumen = f"""Regimen macro: {regimen.get('clasificacion', 'N/A')} ({regimen.get('confianza', 0)}%)
Razonamiento: {regimen.get('razonamiento', '')[:300]}
Tesis principal: {tm.get('tesis_principal', '')[:500]}"""

    # Resumen tesis tecnica
    tesis_tecnica_resumen = "Sin tesis tecnica disponible"
    if inputs["tesis_tecnica"]:
        tt = inputs["tesis_tecnica"]
        senales_resumen = []
        for s in tt.get("senales", []):
            senales_resumen.append(
                f"  - {s.get('activo')}: {s.get('direccion')} "
                f"(conv {s.get('conviccion')}/10) - {s.get('razonamiento', '')[:150]}"
            )
        tesis_tecnica_resumen = f"""Tesis tecnica: {tt.get('tesis_principal', '')[:300]}
Senales tecnicas:
{chr(10).join(senales_resumen)}"""

    prompt = f"""Fecha del analisis: {inputs['fecha_analisis']}

=== CONTEXTO MACRO DEL FONDO ===

{tesis_macro_resumen}

=== CONTEXTO TECNICO DEL FONDO ===

{tesis_tecnica_resumen}

=== TUS DATOS SECTORIALES ===

PRECIOS ACTUALES (USD):
{json.dumps(inputs['precios_og'], indent=2, ensure_ascii=False)}

SPREADS:
{json.dumps(inputs['spreads_og'], indent=2, ensure_ascii=False)}

INDICADORES EIA:
{json.dumps(inputs['indicadores_eia'], indent=2, ensure_ascii=False)}

=== NOTICIAS DEL SECTOR (ultimas 24-36hs) ===

{json.dumps(inputs['noticias_og'], indent=2, ensure_ascii=False)[:8000]}

=== TU TAREA ===

Aplica el proceso mental de tu system prompt. Genera el memo sectorial energetico en JSON estricto siguiendo la estructura definida. Sin texto antes ni despues del JSON."""

    return prompt


# ----------------- Validador -----------------
def validar_output(output: dict) -> tuple[bool, list, list]:
    """
    Valida el output del og_agent.

    Returns:
        es_valido: True si NO hubo errores en todo el output.
        errores: lista de strings con cada error encontrado.
        senales_validas: lista de señales que pasaron TODOS los chequeos
            de campos (direccion, conviccion). Las malformadas se
            descartan acá para que no rompan adaptar_para_tracker
            ni el tracker con KeyError.
    """
    errores = []
    senales_validas = []
    campos_requeridos = [
        "fecha", "regimen_oil", "regimen_natgas", "regimen_lpg",
        "tesis_principal", "senales", "eventos_clave",
        "invalidadores",
    ]
    for c in campos_requeridos:
        if c not in output:
            errores.append(f"Falta campo '{c}'")

    # Validar regimens
    for tipo in ["oil", "natgas", "lpg"]:
        key = f"regimen_{tipo}"
        if key in output:
            r = output[key]
            if "clasificacion" not in r:
                errores.append(f"{key}: falta clasificacion")
            if "confianza" not in r:
                errores.append(f"{key}: falta confianza")
            elif not (0 <= r["confianza"] <= 100):
                errores.append(f"{key}: confianza fuera de rango 0-100")

    # Validar senales
    activos_validos_og = {"XOM", "CVX", "OXY", "EOG", "VLO", "VIST"}
    for i, s in enumerate(output.get("senales", [])):
        errores_senal = []
        activo = s.get("activo")
        if activo is None:
            errores_senal.append(f"Senal {i+1}: falta campo 'activo'")
        elif activo not in activos_validos_og:
            errores_senal.append(f"Senal {i+1}: activo invalido '{activo}'")
        if s.get("direccion") not in ["LONG", "SHORT", "NEUTRAL"]:
            errores_senal.append(f"Senal {i+1}: direccion invalida")
        if not (1 <= s.get("conviccion", 0) <= 10):
            errores_senal.append(f"Senal {i+1}: conviccion fuera de rango")

        errores.extend(errores_senal)
        if not errores_senal:
            senales_validas.append(s)

    return len(errores) == 0, errores, senales_validas


# ----------------- Main -----------------
def correr_og_agent(max_reintentos: int = 2) -> dict:
    print("=" * 60)
    print(f"O&G Agent (Sonnet 4.6) - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    print("\n[1/4] Cargando inputs...")
    inputs = cargar_inputs()
    print(f"      Tesis macro: {'OK' if inputs['tesis_macro'] else 'FALTA'}")
    print(f"      Tesis tecnica: {'OK' if inputs['tesis_tecnica'] else 'FALTA'}")
    print(f"      Precios OG: {len(inputs['precios_og'])}")
    print(f"      Spreads: {len(inputs['spreads_og'])}")
    print(f"      Indicadores EIA: {len(inputs['indicadores_eia'])}")
    print(f"      Noticias por categoria: {len(inputs['noticias_og'])}")
    total_noticias = sum(len(v) for v in inputs['noticias_og'].values())
    print(f"      Total noticias: {total_noticias}")

    print("\n[2/4] Construyendo prompt...")
    prompt = construir_prompt(inputs)

    print("\n[3/4] Llamando a Claude Sonnet 4.6...")
    client = get_client()
    output = None

    for intento in range(max_reintentos + 1):
        if intento > 0:
            print(f"      Reintento {intento}/{max_reintentos}...")
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            texto = response.content[0].text.strip()
            if texto.startswith("```"):
                texto = texto.split("```")[1]
                if texto.startswith("json"):
                    texto = texto[4:]
                texto = texto.rsplit("```", 1)[0] if "```" in texto else texto
            output = json.loads(texto)
            print("      Respuesta recibida y parseada correctamente")
            break
        except json.JSONDecodeError as e:
            print(f"      Error parseando JSON: {e}")
            if intento == max_reintentos:
                return {"error": f"No se pudo parsear: {e}"}
        except Exception as e:
            print(f"      Error: {e}")
            return {"error": str(e)}

    print("\n[4/4] Validando output...")
    es_valido, errores, senales_validas = validar_output(output)

    # Reemplazar las señales del dict con las filtradas para evitar
    # que señales malformadas lleguen a adaptar_para_tracker / tracker
    # y rompan con KeyError.
    senales_descartadas = len(output.get("senales", [])) - len(senales_validas)
    output["senales"] = senales_validas

    if not es_valido:
        print(f"      Advertencias: {errores}")
        if senales_descartadas:
            print(f"      {senales_descartadas} señales malformadas descartadas")
        output["advertencias_validacion"] = errores
    else:
        print("      Output validado correctamente")

    output["metadata"] = {
        "timestamp": datetime.now().isoformat(),
        "modelo": MODEL,
    }

    return output


def imprimir_memo(output: dict):
    if "error" in output:
        print(f"\nError: {output['error']}")
        return

    print("\n" + "=" * 60)
    print("ENERGY DESK MEMO")
    print("=" * 60)

    for tipo in ["oil", "natgas", "lpg"]:
        r = output.get(f"regimen_{tipo}", {})
        print(f"\n{tipo.upper()}: {r.get('clasificacion', 'N/A')} ({r.get('confianza', 0)}%)")
        print(f"   {r.get('razonamiento', '')[:300]}")

    print(f"\nTESIS PRINCIPAL:")
    print(f"   {output.get('tesis_principal', '')}")

    print(f"\nSENALES ({len(output.get('senales', []))}):")
    for s in output.get("senales", []):
        print(f"   {s['activo']:8s} | {s['direccion']:7s} | Conv {s['conviccion']}/10")
        print(f"            {s.get('razonamiento', '')[:200]}")

    print(f"\nEVENTOS CLAVE:")
    for e in output.get("eventos_clave", []):
        print(f"   - {e}")

    if output.get("contradicciones_observadas"):
        print(f"\nCONTRADICCIONES:")
        print(f"   {output['contradicciones_observadas']}")

    print(f"\nINVALIDADORES:")
    for i in output.get("invalidadores", []):
        print(f"   - {i}")

    if output.get("data_gaps"):
        print(f"\nDATA GAPS:")
        print(f"   {output['data_gaps']}")

    print("\n" + "=" * 60)


# ----------------- Entry point -----------------
def adaptar_para_tracker(output: dict) -> dict:
    """
    El og_agent genera senales sin horizonte. El tracker lo necesita.
    Asignamos MENSUAL por default a todas las senales del Energy Desk.
    Tambien mapeamos el regimen oil como regimen principal.
    """
    senales_adaptadas = []
    for s in output.get("senales", []):
        senales_adaptadas.append({
            "activo": s["activo"],
            "direccion": s["direccion"],
            "horizonte": "MENSUAL",
            "conviccion": s["conviccion"],
            "razonamiento": s.get("razonamiento", "")
        })

    regimen_oil = output.get("regimen_oil", {})

    return {
        "senales": senales_adaptadas,
        "regimen": {
            "clasificacion": regimen_oil.get("clasificacion", "DESCONOCIDO")
        },
        "fuente": "energy_desk"
    }


if __name__ == "__main__":
    output = correr_og_agent()
    imprimir_memo(output)

    # Guardar
    fecha = datetime.now().strftime("%Y-%m-%d")
    archivo = f"data/tesis_og_{fecha}.json"
    Path("data").mkdir(parents=True, exist_ok=True)
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nGuardado en: {archivo}")

    # Registrar senales en el tracker (fuente: energy_desk, horizonte default MENSUAL)
    if "error" not in output and output.get("senales"):
        tesis_adaptada = adaptar_para_tracker(output)
        registrar_senales(tesis_adaptada)
