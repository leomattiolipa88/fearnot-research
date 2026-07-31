"""
Banking Agent — Analista del banking desk de Asymmetric Global Macro Fund.

Gemelo estructural de og_agent.py. Lee fundamentals bancarios de la DB
(banking_financials, poblada por banking_collector.py) + las tesis macro/
tecnica del fondo, y genera un memo sectorial con el regimen del ciclo de
credito clasificado y senales por banco.

ADN: Howard Marks (Oaktree) para leer el ciclo de credito + Mike Mayo para
el escepticismo ante numeros que no cierran.

NO es el Synthesizer. Su output es INPUT para el Synthesizer.
"""

import os
import json
import sqlite3
from datetime import date
from pathlib import Path

import anthropic

from config import MODEL, extract_text

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
SYSTEM_PROMPT = """Sos el analista del banking desk de Asymmetric Global Macro Fund. Tu ADN combina dos escuelas: Howard Marks (Oaktree) para leer el ciclo de credito, y Mike Mayo para el escepticismo brutal ante numeros que no cierran.

Tu trabajo:
- LEER tu propia data sectorial: fundamentals bancarios (NII, depositos, prestamos, provisiones) y metricas (loan-to-deposit, cost-of-risk, efficiency-ratio) de los 7 bancos.
- LEER las tesis macro y tecnica del fondo (regimen, indicadores).
- GENERAR un memo sectorial bancario que clasifique EN QUE FASE DEL CICLO DE CREDITO estamos y que senalan los bancos sobre la economia.

NO sos el Synthesizer. NO generas convicciones finales. Tu output es un INPUT para el Synthesizer.

REGLAS NO NEGOCIABLES:

1. ANTI-HALLUCINATION ESTRICTO. Solo afirma cosas que esten en tus inputs. Cada dato trae un quality flag. Si un dato dice not_found, NO inventes el numero. Si necesitas algo que no tenes (ROTCE, NIM, capital ratios CET1/Tier1), decilo: "no tengo ese dato" (estan documentados en LIMITATIONS #14/#16/#17 - requieren parse de 10-K, no estan en XBRL).

2. PENSA EN CICLO DE CREDITO, NO EN STOCK PICKS (Marks). Los bancos son SENSORES del ciclo de credito, no oportunidades de stock individuales.
   - cost_of_risk subiendo = provisiones anticipando morosidad = los bancos huelen recesion. Es el leading indicator mas potente.
   - loan_to_deposit = apetito de prestamo. Bajo = miedo o exceso de liquidez. Subiendo = confianza en el ciclo.
   - "Cuando todos prestan sin miedo, es tarde en el ciclo. Cuando nadie quiere prestar, suele ser temprano."

3. LAS CONTRADICCIONES SON SENALES. Si algo no encaja, ahi esta la oportunidad o el riesgo.
   - NII cae pero provisiones bajan -> complacencia?
   - efficiency_ratio empeora mientras el banco se dice sano.
   - cost_of_risk sospechosamente bajo dado el regimen macro actual.

4. ESCEPTICISMO MAYO ante numeros lindos. No te creas el numero sano sin preguntarte que esconde.
   - Un cost_of_risk demasiado bajo en ciclo tardio NO es fortaleza, es provision insuficiente (riesgo diferido).
   - Un efficiency_ratio que mejora por recorte de costos (no por crecimiento de ingresos) es fragil.

5. COHERENCIA MACRO. Lee la tesis macro del fondo. Si el regimen es GOLDILOCKS, el credito se expande sano. Si es RECESION PROXIMA, las provisiones DEBERIAN estar subiendo - si no lo estan, ESO es la senal (los bancos no la vieron o la esconden). Tu lectura sectorial debe ser coherente con el regimen macro.

6. SUB-TIPOS IMPORTAN. No mezcles tipos de banco distintos.
   - Universal banks (JPM, BAC, WFC, C): se leen por NIM, cost_of_risk, loan_to_deposit. Banca comercial.
   - Investment banks (GS, MS): se leen por trading/eficiencia. cost_of_risk casi no aplica (no prestan).
   - Digital EM (NU): otro animal (Brasil, credito unsecured, NIM altisimo). Cobertura limitada.
"""


# ----------------- Cargar inputs -----------------
def cargar_inputs(fiscal_year: int = 2024) -> dict:
    """Carga tesis macro/tecnica (JSON) + fundamentals bancarios (DB)."""
    data_dir = Path("data")
    inputs = {
        "fecha_analisis": date.today().isoformat(),
        "fiscal_year": fiscal_year,
        "tesis_macro": None,
        "tesis_tecnica": None,
        "bancos": {},  # ticker -> {subtype, concepts: {concept: {value, quality}}}
    }

    # Tesis macro mas reciente (mismo patron que og_agent)
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

    tesis_tec_files = sorted(data_dir.glob("tesis_tecnica_*.json"), reverse=True)
    if tesis_tec_files:
        try:
            with open(tesis_tec_files[0], encoding="utf-8") as f:
                inputs["tesis_tecnica"] = json.load(f)
        except Exception as e:
            print(f"   Error leyendo tesis tecnica: {e}")

    # Fundamentals bancarios desde la DB
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        for row in conn.execute("""
            SELECT ticker, subtype, concept, value, quality
            FROM banking_financials
            WHERE fiscal_year = ?
            ORDER BY ticker, concept
        """, (fiscal_year,)):
            t = row["ticker"]
            if t not in inputs["bancos"]:
                inputs["bancos"][t] = {"subtype": row["subtype"], "concepts": {}}
            inputs["bancos"][t]["concepts"][row["concept"]] = {
                "value": row["value"],
                "quality": row["quality"],
            }
        conn.close()
    except Exception as e:
        print(f"   Error leyendo banking_financials: {e}")

    return inputs


# ----------------- Construir prompt -----------------
def construir_prompt(inputs: dict) -> str:
    # Resumen tesis macro (mismo patron que og_agent)
    tesis_macro_resumen = "Sin tesis macro disponible"
    if inputs["tesis_macro"]:
        tm = inputs["tesis_macro"]
        regimen = tm.get("regimen", {})
        tesis_macro_resumen = f"""Regimen macro: {regimen.get('clasificacion', 'N/A')} ({regimen.get('confianza', 0)}%)
Razonamiento: {regimen.get('razonamiento', '')[:300]}
Tesis principal: {tm.get('tesis_principal', '')[:500]}"""

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
Fiscal year de los fundamentals: {inputs['fiscal_year']}

=== CONTEXTO MACRO DEL FONDO ===

{tesis_macro_resumen}

=== CONTEXTO TECNICO DEL FONDO ===

{tesis_tecnica_resumen}

=== TUS DATOS SECTORIALES (fundamentals bancarios FY{inputs['fiscal_year']}) ===

Cada banco con su sub-tipo y conceptos. Cada concepto trae value + quality.
quality "direct" = de XBRL; "calculated_from_*" = metrica derivada;
"not_found" = NO disponible (no inventar).

{json.dumps(inputs['bancos'], indent=2, ensure_ascii=False)}

=== METRICAS NO DISPONIBLES (LIMITATIONS) ===

ROTCE, NIM y capital ratios (CET1/Tier1) NO estan disponibles via XBRL
(requieren parse de 10-K, documentado #14/#16/#17). Si tu analisis los
necesita, decilo explicitamente como dato faltante.

=== TU TAREA ===

Aplica el proceso mental de tu system prompt (Marks + Mayo). Clasifica la
fase del ciclo de credito y genera senales por banco. Genera el memo en
JSON estricto con esta estructura, sin texto antes ni despues:

{{
  "fecha": "YYYY-MM-DD",
  "regimen_credito": {{
    "clasificacion": "EXPANSION|EUFORIA|CONTRACCION|PANICO|NEUTRAL",
    "confianza": 0-100,
    "razonamiento": "por que estamos en esta fase, leyendo provisiones y apetito de prestamo"
  }},
  "tesis_principal": "lectura del ciclo de credito y que senalan los bancos sobre la macro",
  "senales": [
    {{
      "activo": "JPM|BAC|WFC|C|GS|MS|NU",
      "direccion": "LONG|SHORT|NEUTRAL",
      "conviccion": 1-10,
      "razonamiento": "coherente con el ciclo y el sub-tipo del banco"
    }}
  ],
  "contradicciones": ["lo que no encaja en los datos, estilo Mayo"],
  "eventos_clave": ["que mirar en el proximo trimestre"],
  "invalidadores": ["que datos cambiarian esta lectura"]
}}"""

    return prompt


# ----------------- Validador -----------------
def validar_output(output: dict) -> tuple:
    """Valida el output del banking_agent. Devuelve (es_valido, errores, senales_validas)."""
    errores = []
    senales_validas = []
    campos_requeridos = [
        "fecha", "regimen_credito", "tesis_principal",
        "senales", "contradicciones", "eventos_clave", "invalidadores",
    ]
    for c in campos_requeridos:
        if c not in output:
            errores.append(f"Falta campo '{c}'")

    # Validar regimen_credito
    if "regimen_credito" in output:
        r = output["regimen_credito"]
        clasif_validas = {"EXPANSION", "EUFORIA", "CONTRACCION", "PANICO", "NEUTRAL"}
        if "clasificacion" not in r:
            errores.append("regimen_credito: falta clasificacion")
        elif r["clasificacion"] not in clasif_validas:
            errores.append(f"regimen_credito: clasificacion invalida '{r['clasificacion']}'")
        if "confianza" not in r:
            errores.append("regimen_credito: falta confianza")
        elif not (0 <= r["confianza"] <= 100):
            errores.append("regimen_credito: confianza fuera de rango 0-100")

    # Validar senales
    bancos_validos = {"JPM", "BAC", "WFC", "C", "GS", "MS", "NU"}
    for i, s in enumerate(output.get("senales", [])):
        errores_senal = []
        activo = s.get("activo")
        if activo is None:
            errores_senal.append(f"Senal {i+1}: falta 'activo'")
        elif activo not in bancos_validos:
            errores_senal.append(f"Senal {i+1}: activo invalido '{activo}'")
        if s.get("direccion") not in ["LONG", "SHORT", "NEUTRAL"]:
            errores_senal.append(f"Senal {i+1}: direccion invalida")
        if not (1 <= s.get("conviccion", 0) <= 10):
            errores_senal.append(f"Senal {i+1}: conviccion fuera de rango 1-10")
        errores.extend(errores_senal)
        if not errores_senal:
            senales_validas.append(s)

    return len(errores) == 0, errores, senales_validas


# ----------------- Main -----------------
def correr_banking_agent(fiscal_year: int = 2024, max_reintentos: int = 2) -> dict:
    inputs = cargar_inputs(fiscal_year)
    if not inputs["bancos"]:
        return {"error": "No hay datos en banking_financials. Corre banking_collector.py primero."}

    prompt = construir_prompt(inputs)
    client = get_client()

    output = None
    for intento in range(max_reintentos + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            texto = extract_text(response).strip()
            # Limpiar posibles fences
            if texto.startswith("```"):
                texto = texto.split("```")[1]
                if texto.startswith("json"):
                    texto = texto[4:]
                texto = texto.strip()
            output = json.loads(texto)
        except json.JSONDecodeError as e:
            if intento >= max_reintentos:
                return {"error": f"No se pudo parsear JSON: {e}"}
            continue
        except Exception as e:
            return {"error": str(e)}

        es_valido, errores, senales_validas = validar_output(output)
        output["senales"] = senales_validas  # descartar malformadas
        if es_valido:
            break
        elif intento >= max_reintentos:
            output["_validacion_errores"] = errores

    return output


def imprimir_memo(output: dict):
    if "error" in output:
        print(f"ERROR: {output['error']}")
        return
    rc = output.get("regimen_credito", {})
    print("=" * 60)
    print(f"BANKING DESK MEMO - {output.get('fecha', 'N/A')}")
    print("=" * 60)
    print(f"Regimen de credito: {rc.get('clasificacion', 'N/A')} ({rc.get('confianza', 0)}%)")
    print(f"\nTesis: {output.get('tesis_principal', '')}")
    print("\nSenales:")
    for s in output.get("senales", []):
        print(f"  {s['activo']:5s} {s['direccion']:8s} conv {s['conviccion']}/10 - {s.get('razonamiento','')[:80]}")
    if output.get("contradicciones"):
        print("\nContradicciones (Mayo):")
        for c in output["contradicciones"]:
            print(f"  - {c}")


# ----------------- Entry point -----------------
def adaptar_para_tracker(output: dict) -> dict:
    """
    El banking_agent genera senales sin horizonte. El tracker lo necesita.
    Asignamos TRIMESTRAL por default (los fundamentals bancarios son trimestrales).
    Mapeamos regimen_credito como regimen principal.
    """
    senales_adaptadas = []
    for s in output.get("senales", []):
        senales_adaptadas.append({
            "activo": s["activo"],
            "direccion": s["direccion"],
            "horizonte": "TRIMESTRAL",
            "conviccion": s["conviccion"],
            "razonamiento": s.get("razonamiento", "")
        })
    regimen_credito = output.get("regimen_credito", {})
    return {
        "senales": senales_adaptadas,
        "regimen": {
            "clasificacion": regimen_credito.get("clasificacion", "DESCONOCIDO")
        },
        "fuente": "banking_desk"
    }


if __name__ == "__main__":
    import sys
    fy = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    output = correr_banking_agent(fy)
    imprimir_memo(output)
    # Guardar (mismo patron que og_agent)
    from datetime import datetime
    fecha = datetime.now().strftime("%Y-%m-%d")
    archivo = f"data/tesis_banking_{fecha}.json"
    Path("data").mkdir(parents=True, exist_ok=True)
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nGuardado en: {archivo}")
