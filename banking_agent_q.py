"""
Banking Agent Trimestral — Analista del banking desk leyendo TENDENCIAS.

Evolucion del banking_agent.py anual. Diferencia central: en vez de razonar
sobre un retrato fijo (FY2024), lee la SERIE de los ultimos trimestres
(banking_financials_q) y razona sobre la PENDIENTE de cada metrica.

ADN: Howard Marks (lee hacia donde se mueve el ciclo de credito) + Mike Mayo
(escepticismo ante tendencias que no cierran entre si).

Pre-procesa la tendencia en Python (analizar_tendencia) y le pasa a Claude la
direccion ya interpretada + la serie cruda - no le pide al modelo que
interprete numeros sueltos.

NO es el Synthesizer. Su output es INPUT para el Synthesizer.
"""

import os
import json
import sqlite3
from datetime import date
from pathlib import Path

import anthropic

from config import MODEL, MAX_TOKENS, extract_text, trimestre_actual
from tendencia import analizar_tendencia
from tracker import registrar_senales

DB_PATH = "data/macro.db"

# Las 5 metricas clave que analizamos por tendencia (decision de diseno)
METRICAS_CLAVE = [
    "cost_of_risk", "efficiency_ratio", "loan_to_deposit",
    "net_interest_income", "provision_for_credit_losses",
]


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


# ----------------- System Prompt (reorientado a TENDENCIA) -----------------
SYSTEM_PROMPT = """Sos el analista del banking desk de Asymmetric Global Macro Fund. Tu ADN combina dos escuelas: Howard Marks (Oaktree) para leer el ciclo de credito, y Mike Mayo para el escepticismo brutal ante numeros que no cierran.

A DIFERENCIA de un analisis estatico, vos lees TENDENCIAS trimestrales. No te dan un retrato fijo: te dan la DIRECCION en que se mueve cada metrica a lo largo de los ultimos trimestres. Tu ventaja es leer la PENDIENTE, no el nivel.

Tu trabajo:
- LEER las TENDENCIAS de tus 5 metricas clave del ciclo (cost_of_risk, efficiency_ratio, loan_to_deposit, NII, provisiones) para los 7 bancos. Cada una viene con su direccion, cambio %, rachas de trimestres consecutivos, y la serie cruda.
- LEER las tesis macro y tecnica del fondo.
- GENERAR un memo que clasifique la FASE del ciclo de credito Y HACIA DONDE se mueve, y que senalan los bancos.

NO sos el Synthesizer. Tu output es un INPUT para el Synthesizer.

REGLAS NO NEGOCIABLES:

1. LEE LA PENDIENTE, NO EL NIVEL (Marks trimestral). La direccion anticipa al nivel.
   - cost_of_risk SUBIENDO varios trimestres seguidos = provisiones anticipando morosidad = el ciclo girando hacia contraccion, AUNQUE el nivel todavia se vea bajo. La racha es la senal, no el valor absoluto.
   - loan_to_deposit subiendo = apetito de prestamo creciendo = confianza en el ciclo. Bajando = miedo o liquidez ociosa.
   - "Cuando el apetito de prestamo acelera trimestre tras trimestre sin freno, es tarde en el ciclo."

2. ESTABLE ES UNA LECTURA VALIDA. Si las tendencias son planas (cambios <2%, sin rachas), NO fuerces una narrativa de giro. Una serie chata de cost_of_risk significa "sin deterioro de credito visible" - eso es informacion, no falta de ella. No inventes una historia de ciclo donde los datos muestran estabilidad.

3. ANTI-HALLUCINATION ESTRICTO. Solo afirma lo que este en tus inputs. Si una metrica dice "sin datos" o "insuficiente", NO inventes su tendencia. Si necesitas algo que no tenes (ROTCE, NIM, CET1/Tier1), decilo (LIMITATIONS #14/#16/#17 - requieren parse de 10-K, no XBRL).

4. ESCEPTICISMO MAYO sobre la COHERENCIA ENTRE TENDENCIAS. El escepticismo ahora se aplica a trayectorias que no cierran entre si:
   - Provisiones BAJANDO mientras los prestamos CRECEN agresivo = el banco no esta reconociendo el riesgo que acumula. Bandera roja.
   - Efficiency mejorando solo porque NII sube (no por control de costos) = mejora fragil que se revierte cuando el ciclo de tasas gire.
   - cost_of_risk plano mientras el resto del sector sube = o este banco es genuinamente mejor, o esta provisionando tarde. La divergencia es la senal.
   - Un banco cuya tendencia contradice al regimen macro del fondo: si la macro dice RECESION PROXIMA pero sus provisiones bajan, o no la vio o la esconde.

5. COHERENCIA MACRO. Tu lectura de tendencias debe dialogar con el regimen macro del fondo. Si el regimen es GOLDILOCKS, esperas cost_of_risk estable/bajando y apetito creciendo. Si las tendencias contradicen el regimen, ESO es lo interesante.

6. SUB-TIPOS IMPORTAN. No mezcles tipos de banco.
   - Universal banks (JPM, BAC, WFC, C): se leen por cost_of_risk, loan_to_deposit, NII. Banca comercial.
   - Investment banks (GS, MS): por trading/eficiencia. cost_of_risk casi no aplica (no prestan tradicional).
   - Digital EM (NU): otro animal (Brasil, unsecured). Cobertura trimestral muy limitada via XBRL - declara el limite.
"""


# ----------------- Anclaje del ancla en datos -----------------
def _resolver_trimestre_anclado_en_datos() -> tuple[int, int]:
    """Ancla el análisis en el trimestre más nuevo presente en la DB
    (banking_financials_q). Si la tabla está vacía o inaccesible, cae a
    config.trimestre_actual() como red de seguridad."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT anio, quarter FROM banking_financials_q "
            "WHERE quarter IS NOT NULL "
            "ORDER BY anio DESC, quarter DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row and row[0] is not None and row[1] is not None:
            return int(row[0]), int(row[1])
    except Exception:
        pass
    return trimestre_actual()


# ----------------- Cargar inputs (trimestral) -----------------
def cargar_inputs_q(anio_actual: int = None, quarter_actual: int = None) -> dict:
    """Carga tesis macro/tecnica (JSON) + SERIES trimestrales con tendencia (DB)."""
    if anio_actual is None or quarter_actual is None:
        anio_actual, quarter_actual = _resolver_trimestre_anclado_en_datos()
    data_dir = Path("data")
    inputs = {
        "fecha_analisis": date.today().isoformat(),
        "periodo_actual": f"CY{anio_actual}Q{quarter_actual}",
        "tesis_macro": None,
        "tesis_tecnica": None,
        "bancos": {},
    }
    # Tesis macro mas reciente (mismo patron que el anual)
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
    # Series trimestrales desde banking_financials_q
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        filas = conn.execute("""
            SELECT ticker, subtype, period, anio, quarter, concept, value
            FROM banking_financials_q
            ORDER BY ticker, concept, anio, quarter
        """).fetchall()
        conn.close()
        for r in filas:
            t = r["ticker"]
            if t not in inputs["bancos"]:
                inputs["bancos"][t] = {"subtype": r["subtype"], "metricas": {}}
            concept = r["concept"]
            if concept not in inputs["bancos"][t]["metricas"]:
                inputs["bancos"][t]["metricas"][concept] = {"serie": [], "tendencia": None, "ultimo_valor": None}
            inputs["bancos"][t]["metricas"][concept]["serie"].append((r["period"], r["value"]))
        # Correr tendencia sobre cada serie
        for t, banco in inputs["bancos"].items():
            for concept, m in banco["metricas"].items():
                m["tendencia"] = analizar_tendencia(m["serie"])
                for period, val in reversed(m["serie"]):
                    if val is not None:
                        m["ultimo_valor"] = val
                        break
    except Exception as e:
        print(f"   Error leyendo banking_financials_q: {e}")
    return inputs


# ----------------- Construir prompt (trimestral) -----------------
def construir_prompt(inputs: dict) -> str:
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

    # Bloque de tendencias por banco (las 5 metricas clave)
    lineas = []
    for ticker, banco in sorted(inputs["bancos"].items()):
        lineas.append(f"\n{ticker} ({banco['subtype']}):")
        for concepto in METRICAS_CLAVE:
            m = banco["metricas"].get(concepto)
            if m is None or m["tendencia"] is None:
                lineas.append(f"  {concepto}: sin datos")
                continue
            tend = m["tendencia"]
            serie_str = ", ".join(f"{v:.4g}" if v is not None else "n/a" for _, v in m["serie"])
            lineas.append(f"  {concepto}: {tend['lectura']}")
            lineas.append(f"    serie (viejo->nuevo): [{serie_str}]")
    bloque_bancos = "\n".join(lineas)

    prompt = f"""Fecha del analisis: {inputs['fecha_analisis']}
Periodo mas reciente: {inputs['periodo_actual']}

=== CONTEXTO MACRO DEL FONDO ===

{tesis_macro_resumen}

=== CONTEXTO TECNICO DEL FONDO ===

{tesis_tecnica_resumen}

=== TUS DATOS SECTORIALES (TENDENCIAS trimestrales) ===

Para cada banco, las 5 metricas clave del ciclo de credito, analizadas como
TENDENCIA sobre los ultimos trimestres. NO es un retrato fijo: es la DIRECCION
en que se mueve cada metrica.

Por cada metrica ves la lectura de tendencia (direccion, cambio %, rachas) y la
serie cruda (viejo->nuevo) para verificar.

Ratios: cost_of_risk, efficiency_ratio, loan_to_deposit.
USD: net_interest_income, provision_for_credit_losses.
"sin datos"/"insuficiente" = NO disponible, no inventes tendencia.
{bloque_bancos}

=== METRICAS NO DISPONIBLES (LIMITATIONS) ===

ROTCE, NIM y capital ratios (CET1/Tier1) NO estan via XBRL (requieren parse de
10-K, #14/#16/#17). Si tu analisis los necesita, decilo como dato faltante.

=== TU TAREA ===

Aplica tu proceso mental (Marks + Mayo) leyendo TENDENCIAS, no niveles. Clasifica
la fase del ciclo MATIZADA por la direccion de las tendencias. Genera el memo en
JSON estricto, sin texto antes ni despues:

{{
  "fecha": "YYYY-MM-DD",
  "periodo_analizado": "{inputs['periodo_actual']}",
  "regimen_credito": {{
    "clasificacion": "EXPANSION|EUFORIA|CONTRACCION|PANICO|NEUTRAL",
    "direccion_ciclo": "ACELERANDO|DESACELERANDO|ESTABLE",
    "confianza": 0-100,
    "razonamiento": "que fase y hacia donde se mueve, leyendo tendencias de provisiones y apetito de prestamo"
  }},
  "tesis_principal": "que tendencias dominan y que anticipan sobre la macro",
  "senales": [
    {{
      "activo": "JPM|BAC|WFC|C|GS|MS|NU",
      "direccion": "LONG|SHORT|NEUTRAL",
      "conviccion": 1-10,
      "razonamiento": "basado en la TENDENCIA del banco, no en un nivel puntual"
    }}
  ],
  "contradicciones": ["tendencias que no encajan entre si, estilo Mayo"],
  "eventos_clave": ["que mirar el proximo trimestre dado el rumbo"],
  "invalidadores": ["que cambio de tendencia invalidaria esta lectura"]
}}"""

    return prompt


# ----------------- Validador -----------------
def validar_output(output: dict) -> tuple:
    errores = []
    senales_validas = []
    campos_requeridos = [
        "fecha", "regimen_credito", "tesis_principal",
        "senales", "contradicciones", "eventos_clave", "invalidadores",
    ]
    for c in campos_requeridos:
        if c not in output:
            errores.append(f"Falta campo '{c}'")

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
        # direccion_ciclo es nuevo del trimestral
        if "direccion_ciclo" in r:
            if r["direccion_ciclo"] not in {"ACELERANDO", "DESACELERANDO", "ESTABLE"}:
                errores.append(f"regimen_credito: direccion_ciclo invalida '{r['direccion_ciclo']}'")

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
def correr_banking_agent_q(anio_actual: int = None, quarter_actual: int = None, max_reintentos: int = 2) -> dict:
    if anio_actual is None or quarter_actual is None:
        anio_actual, quarter_actual = _resolver_trimestre_anclado_en_datos()
    inputs = cargar_inputs_q(anio_actual, quarter_actual)
    if not inputs["bancos"]:
        return {"error": "No hay datos en banking_financials_q. Corre banking_collector_q.py primero."}

    prompt = construir_prompt(inputs)
    client = get_client()

    output = None
    for intento in range(max_reintentos + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            texto = extract_text(response).strip()
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
        output["senales"] = senales_validas
        if es_valido:
            break
        elif intento >= max_reintentos:
            output["_validacion_errores"] = errores

    output["modelo"] = MODEL
    return output


def adaptar_para_tracker(output: dict) -> dict:
    """Horizonte TRIMESTRAL, fuente banking_desk_q."""
    senales_adaptadas = []
    for s in output.get("senales", []):
        senales_adaptadas.append({
            "activo": s["activo"],
            "direccion": s["direccion"],
            "horizonte": "TRIMESTRAL",
            "conviccion": s["conviccion"],
            "razonamiento": s.get("razonamiento", ""),
        })
    regimen = output.get("regimen_credito", {})
    return {
        "senales": senales_adaptadas,
        "regimen": {"clasificacion": regimen.get("clasificacion", "DESCONOCIDO")},
        "fuente": "banking_desk_q",
    }


def imprimir_memo(output: dict):
    if "error" in output:
        print(f"\nERROR: {output['error']}")
        return
    print("=" * 60)
    print(f"BANKING DESK MEMO TRIMESTRAL - {output.get('fecha', 'N/A')}")
    print(f"Periodo analizado: {output.get('periodo_analizado', 'N/A')}")
    print("=" * 60)
    r = output.get("regimen_credito", {})
    print(f"Regimen: {r.get('clasificacion', 'N/A')} ({r.get('confianza', 0)}%) - "
          f"direccion: {r.get('direccion_ciclo', 'N/A')}")
    print(f"Tesis: {output.get('tesis_principal', '')}")
    print("Senales:")
    for s in output.get("senales", []):
        print(f"  {s['activo']:5s} {s['direccion']:8s} conv {s['conviccion']}/10 - {s.get('razonamiento','')[:90]}")
    if output.get("contradicciones"):
        print("Contradicciones (Mayo):")
        for c in output["contradicciones"]:
            print(f"  - {c}")
    if output.get("eventos_clave"):
        print("Eventos clave:")
        for e in output["eventos_clave"]:
            print(f"  - {e}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        # Override manual (análisis histórico): requiere anio + quarter juntos.
        anio = int(sys.argv[1])
        q = int(sys.argv[2])
    else:
        anio, q = _resolver_trimestre_anclado_en_datos()
    output = correr_banking_agent_q(anio, q)
    imprimir_memo(output)
    from datetime import datetime
    fecha = datetime.now().strftime("%Y-%m-%d")
    archivo = f"data/tesis_banking_q_{fecha}.json"
    Path("data").mkdir(parents=True, exist_ok=True)
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nGuardado en: {archivo}")

    # Registrar senales en el tracker (fuente: banking_desk_q, horizonte TRIMESTRAL)
    # Mismo patron que og_agent.py y banking_agent.py.
    if "error" not in output and output.get("senales"):
        tesis_adaptada = adaptar_para_tracker(output)
        registrar_senales(tesis_adaptada)
