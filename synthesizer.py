"""
FearNot - Synthesizer Agent (Opus 4.7)

El CIO del fondo. NO genera mas analisis individual.
LEE los memos de los agentes especializados (macro, technical, O&G)
y SINTETIZA convicciones de alta calidad cuando multiples analisis convergen.

DNA: Druckenmiller (concentration) + Soros (reflexivity) + Taleb (asymmetry)
     + Tudor Jones (risk management)

Filosofia: scarcity of conviction.
Si no hay convicciones de calidad esta semana, no se publica nada.
"""

import json
import os
import sqlite3
import anthropic
from datetime import datetime, date, timedelta
from pathlib import Path

from config import MODEL

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
SYSTEM_PROMPT = """Sos el CIO de Asymmetric Global Macro Fund, un fondo multi-agente con DNA de Druckenmiller, Soros, Taleb y Tudor Jones. Tu trabajo NO es generar mas analisis - vos NO miras indicadores ni precios directamente. Tu trabajo es leer los memos de tus traders especializados (macro, technical, O&G energy desk) y SINTETIZAR convicciones de alta calidad cuando multiples analisis convergen.

REGLAS NO NEGOCIABLES:

1. SCARCITY OF CONVICTION. Druckenmiller tuvo 5-6 trades por ano en sus mejores periodos. Si no encontras convicciones de calidad, NO INVENTES. Devolve el JSON vacio con razonamiento explicito.

2. THE THREE FILTERS. Una conviction se publica solo si pasa los tres:
   - Multiple agents agree (minimo 2 razones independientes desde analisis distintos)
   - Causal chain explicable (si no podes explicarlo en 3 frases, no lo entendes)
   - Asymmetric risk/reward (downside acotado, upside material)

3. CREATIVITY OVER AGGREGATION. Tu valor no es resumir lo que ya dicen los agentes. Tu valor es ver lo que NINGUNO de ellos ve solo. Busca:
   - Cadenas causales laterales (A -> B -> C -> trade)
   - Contradicciones productivas entre agentes (si dicen cosas opuestas, que significa?)
   - Reflexividad (la creencia del mercado va a alterar la realidad fundamental?)

4. ACCOUNTABILITY RADICAL. Cada conviction debe tener:
   - Invalidators concretos (eventos especificos, no abstracciones)
   - "What I could be wrong about" honesto
   - Position size sugerido (Small / Standard / Concentrated)

5. ANTI-HALLUCINATION. Solo afirma cosas que esten en los inputs que recibis. Si necesitas un dato que no esta, decilo explicitamente. No inventes precios, no inventes catalysts, no inventes razonamientos de los agentes que no escribieron eso.

6. RECONOCE CORRELACIONES. Si el O&G agent dice "todo LONG energy", esa es una apuesta correlacionada, no diversificada. Una conviction LONG XOM y otra LONG VLO son fundamentalmente la misma apuesta. Selecciona la mejor expresion, no las dos.

PROCESO MENTAL OBLIGATORIO:

Paso 1: Lee todos los inputs sin juzgar (macro + technical + O&G).
Paso 2: Identifica activos donde 2+ agentes apuntan en la misma direccion.
Paso 3: Para cada uno, escribi mentalmente la cadena causal completa.
Paso 4: Evalua los tres filtros honestamente.
Paso 5: Si pasa, genera la conviction con la estructura completa.
Paso 6: Si ningun trade pasa, devolve el JSON vacio con tu razonamiento.

ESTRUCTURA DEL OUTPUT (JSON estricto):

{
  "fecha": "YYYY-MM-DD",
  "tipo": "WEEKLY",
  "convicciones": [
    {
      "ticker": "STRING",
      "direccion": "LONG|SHORT",
      "horizonte": "WEEKS|MONTHS|QUARTERS",
      "conviccion": 7-10,
      "position_size": "SMALL|STANDARD|CONCENTRATED",
      "thesis_three_sentences": ["frase 1", "frase 2", "frase 3"],
      "fundamental_case": {
        "macro_context": "STRING",
        "sectoral_dynamics": "STRING",
        "technical_setup": "STRING",
        "why_this_expression": "STRING"
      },
      "agents_aligned": ["nombre_agente: razon"],
      "entry_strategy": "STRING",
      "stop_loss_logic": "STRING",
      "profit_target_logic": "STRING",
      "invalidators": ["punto 1", "punto 2", "punto 3"],
      "what_we_could_be_wrong_about": "STRING"
    }
  ],
  "reasoning_when_no_convictions": "STRING (vacio si hay convicciones)",
  "synthesis_observations": "STRING (1-2 parrafos sobre patrones interesantes que viste, aunque no ameriten conviction)"
}

Conviction range:
- 7: edge presente pero no excepcional, position size SMALL
- 8: setup claro con risk/reward favorable, position size STANDARD
- 9: alta confianza, multiple agents strongly aligned, STANDARD o CONCENTRATED
- 10: fat pitch - Druckenmiller mode, CONCENTRATED

Si dudas entre 7 y 8, elegi 7. Si dudas si publicar, no publiques."""


# ----------------- Inicializar tabla de convicciones -----------------
def init_convictions_table(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS convicciones (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha             TEXT NOT NULL,
            tipo              TEXT NOT NULL,
            ticker            TEXT NOT NULL,
            direccion         TEXT NOT NULL,
            horizonte         TEXT NOT NULL,
            conviccion        INTEGER NOT NULL,
            position_size     TEXT NOT NULL,
            thesis_json       TEXT NOT NULL,
            fundamental_json  TEXT NOT NULL,
            invalidators_json TEXT NOT NULL,
            agents_aligned    TEXT,
            entry_strategy    TEXT,
            stop_loss_logic   TEXT,
            profit_target     TEXT,
            wrong_about       TEXT,
            precio_entrada    REAL,
            fecha_evaluacion  TEXT,
            precio_salida     REAL,
            retorno_pct       REAL,
            evaluado          INTEGER DEFAULT 0,
            UNIQUE(fecha, ticker)
        )
    """)
    conn.commit()
    return conn


# ----------------- Cargar inputs -----------------
def cargar_inputs() -> dict:
    """
    Lee tesis macro, tecnica, O&G mas recientes,
    indicadores y convicciones recientes.
    """
    data_dir = Path("data")
    inputs = {
        "fecha_analisis": date.today().isoformat(),
        "tesis_macro": None,
        "tesis_tecnica": None,
        "tesis_og": None,
        "indicadores_macro": {},
        "indicadores_tecnicos": {},
        "convicciones_recientes": [],
    }

    # Tesis macro mas reciente
    tesis_macro_files = sorted(
        [f for f in data_dir.glob("tesis_2*.json") if "tecnica" not in f.name and "og" not in f.name],
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

    # Tesis O&G mas reciente
    tesis_og_files = sorted(data_dir.glob("tesis_og_*.json"), reverse=True)
    if tesis_og_files:
        try:
            with open(tesis_og_files[0], encoding="utf-8") as f:
                inputs["tesis_og"] = json.load(f)
        except Exception as e:
            print(f"   Error leyendo tesis O&G: {e}")

    # Indicadores macro y tecnicos del DB
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        for nombre in ["yield_curve", "vix", "hy_spread", "usdjpy_mkt",
                       "dxy", "yield_10y", "sahm_rule", "unemployment",
                       "breakeven_5y5y", "jobless_claims"]:
            row = conn.execute("""
                SELECT valor, fecha_publicacion FROM indicadores
                WHERE nombre = ?
                ORDER BY fecha_descarga DESC LIMIT 1
            """, (nombre,)).fetchone()
            if row:
                inputs["indicadores_macro"][nombre] = {
                    "valor": row["valor"],
                    "fecha": row["fecha_publicacion"],
                }

        # Tecnicos por activo
        for row in conn.execute("""
            SELECT * FROM senales_tecnicas
            WHERE fecha = (SELECT MAX(fecha) FROM senales_tecnicas)
        """):
            inputs["indicadores_tecnicos"][row["activo"]] = dict(row)

        # Indicadores de mercado tecnicos
        mercado_row = conn.execute("""
            SELECT * FROM indicadores_tecnicos_mercado
            ORDER BY fecha DESC LIMIT 1
        """).fetchone()
        if mercado_row:
            inputs["indicadores_tecnicos"]["mercado"] = dict(mercado_row)

        # Convicciones de las ultimas 4 semanas
        cuatro_semanas_atras = (date.today() - timedelta(days=28)).isoformat()
        for row in conn.execute("""
            SELECT fecha, ticker, direccion, conviccion, position_size
            FROM convicciones
            WHERE fecha >= ?
            ORDER BY fecha DESC
        """, (cuatro_semanas_atras,)):
            inputs["convicciones_recientes"].append(dict(row))

        conn.close()
    except Exception as e:
        print(f"   Error leyendo DB: {e}")

    return inputs


# ----------------- Construir prompt -----------------
def construir_prompt(inputs: dict) -> str:
    convicciones_recientes_str = ""
    if inputs["convicciones_recientes"]:
        convicciones_recientes_str = (
            "\n\nIMPORTANTE: Estas son las convicciones que ya emitiste en las ultimas 4 semanas. "
            "Evita repetir el mismo trade salvo que la tesis haya cambiado significativamente:\n"
            + json.dumps(inputs["convicciones_recientes"], indent=2, ensure_ascii=False)
        )

    prompt = f"""Fecha del analisis: {inputs['fecha_analisis']}

=== MEMO DEL AGENTE MACRO ===

{json.dumps(inputs['tesis_macro'], indent=2, ensure_ascii=False) if inputs['tesis_macro'] else "(Sin tesis macro disponible)"}

=== MEMO DEL AGENTE TECNICO ===

{json.dumps(inputs['tesis_tecnica'], indent=2, ensure_ascii=False) if inputs['tesis_tecnica'] else "(Sin tesis tecnica disponible)"}

=== MEMO DEL ENERGY DESK (O&G + LPG) ===

{json.dumps(inputs['tesis_og'], indent=2, ensure_ascii=False) if inputs['tesis_og'] else "(Sin tesis O&G disponible)"}

=== INDICADORES MACRO ACTUALES ===

{json.dumps(inputs['indicadores_macro'], indent=2, ensure_ascii=False)}

=== INDICADORES TECNICOS ACTUALES ===

{json.dumps(inputs['indicadores_tecnicos'], indent=2, ensure_ascii=False)}{convicciones_recientes_str}

=== TU TAREA ===

Aplica el proceso mental de tu system prompt. Identifica activos donde MULTIPLES agentes apuntan en la misma direccion con razones independientes. El energy desk (O&G) es ahora un agente mas - sus senales sobre WTI, Brent, Natgas, refiners (VLO, CRAK), E&P (XOM, CVX, OXY, EOG, VIST) cuentan igual que los demas.

CUIDADO CON CORRELACIONES: si el O&G agent tiene 12 senales LONG en energy, esas son la misma apuesta direccional. Selecciona la mejor expresion (1-2 trades), no todas.

Aplica los TRES FILTROS estrictamente. Si encontras 1-3 convicciones de calidad, generalas con la estructura JSON completa. Si no encontras nada que pase los filtros, devolve el JSON vacio con razonamiento explicito en 'reasoning_when_no_convictions'.

Recorda: scarcity of conviction. Druckenmiller tuvo 5-6 trades por ano. La regla por defecto es NO publicar."""

    return prompt


# ----------------- Validador -----------------
def validar_output(output: dict) -> tuple[bool, list]:
    errores = []

    if "convicciones" not in output:
        errores.append("Falta campo 'convicciones'")
        return False, errores

    convs = output["convicciones"]
    for i, c in enumerate(convs):
        prefix = f"Conviccion {i+1}"

        for campo in ["ticker", "direccion", "horizonte", "conviccion",
                      "position_size", "thesis_three_sentences",
                      "fundamental_case", "invalidators",
                      "what_we_could_be_wrong_about"]:
            if campo not in c:
                errores.append(f"{prefix}: falta '{campo}'")

        if c.get("conviccion") and not (7 <= c["conviccion"] <= 10):
            errores.append(f"{prefix}: conviccion fuera de rango 7-10")

        if c.get("direccion") not in ["LONG", "SHORT"]:
            errores.append(f"{prefix}: direccion debe ser LONG o SHORT")

        if c.get("position_size") not in ["SMALL", "STANDARD", "CONCENTRATED"]:
            errores.append(f"{prefix}: position_size invalido")

        if c.get("horizonte") not in ["WEEKS", "MONTHS", "QUARTERS"]:
            errores.append(f"{prefix}: horizonte invalido")

        thesis = c.get("thesis_three_sentences", [])
        if not isinstance(thesis, list) or len(thesis) != 3:
            errores.append(f"{prefix}: thesis_three_sentences debe tener 3 frases")

        if len(c.get("invalidators", [])) < 2:
            errores.append(f"{prefix}: minimo 2 invalidators")

    return len(errores) == 0, errores


# ----------------- Registrar convicciones -----------------
def registrar_convicciones(output: dict) -> int:
    import yfinance as yf

    conn = init_convictions_table()
    n_registradas = 0

    for conv in output.get("convicciones", []):
        ticker = conv["ticker"]

        precio_entrada = None
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="2d")
            if not hist.empty:
                precio_entrada = float(hist["Close"].iloc[-1])
        except Exception as e:
            print(f"   No se pudo obtener precio de {ticker}: {e}")

        dias_horizonte = {"WEEKS": 7, "MONTHS": 30, "QUARTERS": 90}
        dias = dias_horizonte.get(conv["horizonte"], 30)
        fecha_eval = (date.today() + timedelta(days=dias)).isoformat()

        try:
            conn.execute("""
                INSERT OR REPLACE INTO convicciones
                (fecha, tipo, ticker, direccion, horizonte, conviccion, position_size,
                 thesis_json, fundamental_json, invalidators_json, agents_aligned,
                 entry_strategy, stop_loss_logic, profit_target, wrong_about,
                 precio_entrada, fecha_evaluacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                output["fecha"],
                output["tipo"],
                ticker,
                conv["direccion"],
                conv["horizonte"],
                conv["conviccion"],
                conv["position_size"],
                json.dumps(conv["thesis_three_sentences"], ensure_ascii=False),
                json.dumps(conv["fundamental_case"], ensure_ascii=False),
                json.dumps(conv["invalidators"], ensure_ascii=False),
                json.dumps(conv.get("agents_aligned", []), ensure_ascii=False),
                conv.get("entry_strategy", ""),
                conv.get("stop_loss_logic", ""),
                conv.get("profit_target_logic", ""),
                conv.get("what_we_could_be_wrong_about", ""),
                precio_entrada,
                fecha_eval,
            ))
            n_registradas += 1
        except Exception as e:
            print(f"   Error registrando {ticker}: {e}")

    conn.commit()
    conn.close()
    return n_registradas


# ----------------- Funcion principal -----------------
def correr_synthesizer(max_reintentos: int = 2) -> dict:
    print("=" * 60)
    print(f"Synthesizer Agent (Opus 4.7) - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    print("\n[1/4] Cargando inputs de los agentes...")
    inputs = cargar_inputs()
    print(f"      Tesis macro: {'OK' if inputs['tesis_macro'] else 'FALTA'}")
    print(f"      Tesis tecnica: {'OK' if inputs['tesis_tecnica'] else 'FALTA'}")
    print(f"      Tesis O&G: {'OK' if inputs['tesis_og'] else 'FALTA'}")
    print(f"      Indicadores macro: {len(inputs['indicadores_macro'])}")
    print(f"      Indicadores tecnicos: {len(inputs['indicadores_tecnicos'])}")
    print(f"      Convicciones recientes: {len(inputs['convicciones_recientes'])}")

    if not inputs["tesis_macro"] or not inputs["tesis_tecnica"]:
        return {"error": "Faltan tesis macro o tecnica - corre los agentes primero"}

    print("\n[2/4] Construyendo prompt para Opus...")
    prompt = construir_prompt(inputs)

    print("\n[3/4] Llamando a Claude Opus 4.7 (puede tardar 1-2 min)...")
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
    es_valido, errores = validar_output(output)
    if not es_valido:
        print(f"      Advertencias: {errores}")
        output["advertencias_validacion"] = errores
    else:
        print("      Output validado correctamente")

    output["metadata"] = {
        "timestamp": datetime.now().isoformat(),
        "modelo": MODEL,
        "agentes_input": ["macro", "technical", "og_energy"],
    }

    # Persistir convicciones a SQLite (web_exporter lee desde aqui)
    if "convicciones" in output and output["convicciones"]:
        print(f"\n[5/5] Persistiendo {len(output['convicciones'])} convicciones a SQLite...")
        n = registrar_convicciones(output)
        print(f"      Registradas: {n}/{len(output['convicciones'])}")

    return output


# ----------------- Imprimir convicciones -----------------
def imprimir_convicciones(output: dict):
    if "error" in output:
        print(f"\nError: {output['error']}")
        return

    print("\n" + "=" * 60)
    print("CONVICCIONES DE LA SEMANA")
    print("=" * 60)

    convs = output.get("convicciones", [])
    if not convs:
        print("\nNINGUNA CONVICTION ESTA SEMANA")
        razon = output.get("reasoning_when_no_convictions", "")
        if razon:
            print(f"\nRazonamiento del CIO:")
            print(f"   {razon}")
    else:
        for i, c in enumerate(convs, 1):
            print(f"\n--- CONVICTION #{i} ---")
            print(f"\n{c['ticker']:6s} | {c['direccion']:5s} | "
                  f"{c['horizonte']:8s} | Conv: {c['conviccion']}/10 | "
                  f"Size: {c['position_size']}")

            print(f"\nTHESIS:")
            for j, frase in enumerate(c["thesis_three_sentences"], 1):
                print(f"   {j}. {frase}")

            print(f"\nFUNDAMENTAL CASE:")
            fc = c["fundamental_case"]
            print(f"   Macro:     {fc.get('macro_context', '')}")
            print(f"   Sectoral:  {fc.get('sectoral_dynamics', '')}")
            print(f"   Technical: {fc.get('technical_setup', '')}")
            print(f"   Why this:  {fc.get('why_this_expression', '')}")

            print(f"\nAGENTS ALIGNED:")
            for a in c.get("agents_aligned", []):
                print(f"   - {a}")

            print(f"\nENTRY: {c.get('entry_strategy', '')}")
            print(f"STOP:  {c.get('stop_loss_logic', '')}")
            print(f"TARGET: {c.get('profit_target_logic', '')}")

            print(f"\nINVALIDATORS:")
            for inv in c.get("invalidators", []):
                print(f"   - {inv}")

            print(f"\nWHAT WE COULD BE WRONG ABOUT:")
            print(f"   {c.get('what_we_could_be_wrong_about', '')}")

    obs = output.get("synthesis_observations", "")
    if obs:
        print(f"\n--- SYNTHESIS OBSERVATIONS ---")
        print(f"{obs}")

    print("\n" + "=" * 60)


# ----------------- Main -----------------
if __name__ == "__main__":
    output = correr_synthesizer()
    imprimir_convicciones(output)

    fecha = datetime.now().strftime("%Y-%m-%d")
    archivo = f"data/convicciones_{fecha}.json"
    Path("data").mkdir(parents=True, exist_ok=True)
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nGuardado en: {archivo}")

    if "error" not in output and output.get("convicciones"):
        print("\nRegistrando convicciones en tracker...")
        n = registrar_convicciones(output)
        print(f"   {n} convicciones registradas con precio de entrada")
