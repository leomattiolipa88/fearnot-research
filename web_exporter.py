"""
FearNot - Web Exporter

Genera /data/web_data.json con todos los datos que la web consume:
- Tesis macro
- Tesis tecnica
- Tesis O&G (Energy Pulse)
- Senales por activo (consenso entre agentes)
- Indicadores macro clave
- Convicciones del Synthesizer
- Eventos clave / news
- Invalidadores
"""

import json
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path

DB_PATH = "data/macro.db"
OUTPUT_PATH = "data/web_data.json"


def cargar_tesis_mas_reciente(prefijo: str) -> dict:
    """Carga la tesis JSON mas reciente que matchea el prefijo."""
    data_dir = Path("data")
    if prefijo == "macro":
        archivos = sorted(
            [f for f in data_dir.glob("tesis_2*.json")
             if "tecnica" not in f.name and "og" not in f.name],
            reverse=True,
        )
    elif prefijo == "tecnica":
        archivos = sorted(data_dir.glob("tesis_tecnica_*.json"), reverse=True)
    elif prefijo == "og":
        archivos = sorted(data_dir.glob("tesis_og_*.json"), reverse=True)
    else:
        return {}

    if not archivos:
        return {}

    try:
        with open(archivos[0], encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"   Error leyendo {archivos[0]}: {e}")
        return {}


def cargar_convicciones_recientes() -> list:
    """Carga las convicciones activas (ultimas 4 semanas)."""
    convicciones = []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        cuatro_semanas_atras = (date.today() - timedelta(days=28)).isoformat()

        rows = conn.execute("""
            SELECT * FROM convicciones
            WHERE fecha >= ?
            ORDER BY fecha DESC, conviccion DESC
        """, (cuatro_semanas_atras,)).fetchall()

        for row in rows:
            conv = dict(row)
            try:
                conv["thesis"] = json.loads(conv.pop("thesis_json"))
            except:
                conv["thesis"] = []
            try:
                conv["fundamental_case"] = json.loads(conv.pop("fundamental_json"))
            except:
                conv["fundamental_case"] = {}
            try:
                conv["invalidators"] = json.loads(conv.pop("invalidators_json"))
            except:
                conv["invalidators"] = []
            try:
                conv["agents_aligned"] = json.loads(conv.pop("agents_aligned") or "[]")
            except:
                conv["agents_aligned"] = []

            convicciones.append(conv)

        conn.close()
    except Exception as e:
        print(f"   Error cargando convicciones: {e}")

    return convicciones


def cargar_track_record() -> list:
    """Carga TODAS las convicciones cerradas (evaluado=1), sin filtro de fecha.
    Esto alimenta la seccion historica del Track Record en la web."""
    convicciones = []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM convicciones
            WHERE evaluado = 1
            ORDER BY fecha DESC
        """).fetchall()

        for row in rows:
            conv = dict(row)
            # Parsear campos JSON (ignorar si fallan)
            for json_field, output_field in [
                ("thesis_json", "thesis"),
                ("fundamental_json", "fundamental_case"),
                ("invalidators_json", "invalidators"),
            ]:
                try:
                    conv[output_field] = json.loads(conv.pop(json_field, "[]") or "[]")
                except (json.JSONDecodeError, TypeError):
                    conv[output_field] = []
            try:
                conv["agents_aligned"] = json.loads(conv.pop("agents_aligned", "[]") or "[]")
            except (json.JSONDecodeError, TypeError):
                conv["agents_aligned"] = []
            convicciones.append(conv)

        conn.close()
    except Exception as e:
        print(f"   Error cargando track record: {e}")

    return convicciones


def cargar_convicciones_activas() -> list:
    """Carga convicciones NO evaluadas (evaluado=0), sin filtro de fecha.
    Estas son convicciones publicadas que aun no vencieron - 'pending'."""
    convicciones = []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM convicciones
            WHERE evaluado = 0
            ORDER BY fecha DESC
        """).fetchall()

        for row in rows:
            conv = dict(row)
            for json_field, output_field in [
                ("thesis_json", "thesis"),
                ("fundamental_json", "fundamental_case"),
                ("invalidators_json", "invalidators"),
            ]:
                try:
                    conv[output_field] = json.loads(conv.pop(json_field, "[]") or "[]")
                except (json.JSONDecodeError, TypeError):
                    conv[output_field] = []
            try:
                conv["agents_aligned"] = json.loads(conv.pop("agents_aligned", "[]") or "[]")
            except (json.JSONDecodeError, TypeError):
                conv["agents_aligned"] = []
            convicciones.append(conv)

        conn.close()
    except Exception as e:
        print(f"   Error cargando convicciones activas: {e}")

    return convicciones


def construir_performance_summary() -> dict:
    """Llama a tracker.calcular_performance_convicciones() y empaqueta para el JSON."""
    try:
        from tracker import calcular_performance_convicciones
        return calcular_performance_convicciones(DB_PATH)
    except Exception as e:
        print(f"   Error calculando performance summary: {e}")
        return {"n_evaluadas": 0, "error": str(e)}


def construir_senales_consensuadas(tesis_macro: dict, tesis_tecnica: dict) -> list:
    """Combina senales de macro y tecnico, marcando consenso."""
    senales_dict = {}

    for s in tesis_macro.get("senales", []):
        activo = s.get("activo", "").upper()
        if activo:
            senales_dict[activo] = {
                "activo": activo,
                "macro": {
                    "direccion": s.get("direccion", "NEUTRAL"),
                    "conviccion": s.get("conviccion", 5),
                    "razonamiento": s.get("razonamiento", ""),
                },
                "tecnico": None,
            }

    for s in tesis_tecnica.get("senales", []):
        activo = s.get("activo", "").upper()
        if activo:
            tec = {
                "direccion": s.get("direccion", "NEUTRAL"),
                "conviccion": s.get("conviccion", 5),
                "razonamiento": s.get("razonamiento", ""),
            }
            if activo in senales_dict:
                senales_dict[activo]["tecnico"] = tec
            else:
                senales_dict[activo] = {
                    "activo": activo,
                    "macro": None,
                    "tecnico": tec,
                }

    senales = []
    for activo, data in senales_dict.items():
        macro_dir = data["macro"]["direccion"] if data["macro"] else None
        tec_dir = data["tecnico"]["direccion"] if data["tecnico"] else None

        if macro_dir and tec_dir:
            if macro_dir == tec_dir:
                consenso = "CONVERGENTE"
            elif "NEUTRAL" in [macro_dir, tec_dir]:
                consenso = "PARCIAL"
            else:
                consenso = "DIVERGENTE"
        else:
            consenso = "PARCIAL"

        data["consenso"] = consenso
        senales.append(data)

    return sorted(senales, key=lambda x: x["activo"])


def construir_energy_pulse(tesis_og: dict) -> dict:
    """Estructura los datos del energy desk para la web."""
    if not tesis_og:
        return None

    return {
        "fecha": tesis_og.get("fecha", ""),
        "regimen_oil": tesis_og.get("regimen_oil", {}),
        "regimen_natgas": tesis_og.get("regimen_natgas", {}),
        "regimen_lpg": tesis_og.get("regimen_lpg", {}),
        "tesis_principal": tesis_og.get("tesis_principal", ""),
        "senales": tesis_og.get("senales", []),
        "eventos_clave": tesis_og.get("eventos_clave", []),
        "contradicciones": tesis_og.get("contradicciones_observadas", ""),
        "invalidadores": tesis_og.get("invalidadores", []),
        "data_gaps": tesis_og.get("data_gaps", ""),
    }


def cargar_indicadores_clave() -> dict:
    """Carga los ultimos valores de indicadores macro clave."""
    indicadores = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        for nombre in ["yield_curve", "vix", "hy_spread", "dxy",
                       "yield_10y", "sahm_rule", "unemployment", "breakeven_5y5y"]:
            row = conn.execute("""
                SELECT valor, fecha_publicacion FROM indicadores
                WHERE nombre = ?
                ORDER BY fecha_descarga DESC LIMIT 1
            """, (nombre,)).fetchone()
            if row:
                indicadores[nombre] = {
                    "valor": row["valor"],
                    "fecha": row["fecha_publicacion"],
                }
        conn.close()
    except Exception as e:
        print(f"   Error cargando indicadores: {e}")

    return indicadores


def calcular_confianza_consolidada(senales: list, regimen_conf: int) -> int:
    if not senales:
        return regimen_conf
    convs = []
    for s in senales:
        if s["macro"]:
            convs.append(s["macro"]["conviccion"])
        if s["tecnico"]:
            convs.append(s["tecnico"]["conviccion"])
    if not convs:
        return regimen_conf
    promedio_senales = sum(convs) / len(convs) * 10
    return int((regimen_conf + promedio_senales) / 2)


def exportar():
    """Genera el web_data.json completo."""
    print("=" * 60)
    print(f"Web Exporter - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    print("\n[1/6] Cargando tesis macro...")
    tesis_macro = cargar_tesis_mas_reciente("macro")
    print(f"      Fecha: {tesis_macro.get('fecha', 'N/A')}")

    print("\n[2/6] Cargando tesis tecnica...")
    tesis_tecnica = cargar_tesis_mas_reciente("tecnica")
    print(f"      Fecha: {tesis_tecnica.get('fecha', 'N/A')}")

    print("\n[3/6] Cargando tesis O&G (Energy Desk)...")
    tesis_og = cargar_tesis_mas_reciente("og")
    print(f"      Fecha: {tesis_og.get('fecha', 'N/A')}")

    print("\n[4/6] Construyendo senales y energy pulse...")
    senales = construir_senales_consensuadas(tesis_macro, tesis_tecnica)
    energy_pulse = construir_energy_pulse(tesis_og)
    print(f"      {len(senales)} senales macro/tecnico")
    if energy_pulse:
        print(f"      Energy Pulse: {len(energy_pulse['senales'])} senales O&G")

    print("\n[5/6] Cargando convicciones del Synthesizer...")
    convicciones = cargar_convicciones_recientes()
    print(f"      {len(convicciones)} convicciones activas")

    print("\n[6/9] Cargando indicadores clave...")
    indicadores = cargar_indicadores_clave()
    print(f"      {len(indicadores)} indicadores")

    print("\n[7/9] Cargando track record (convicciones cerradas)...")
    track_record = cargar_track_record()
    print(f"      {len(track_record)} convicciones evaluadas en histórico")

    print("\n[8/9] Cargando convicciones pending (no evaluadas)...")
    convicciones_pending = cargar_convicciones_activas()
    print(f"      {len(convicciones_pending)} convicciones pending")

    print("\n[9/9] Calculando performance summary...")
    performance_summary = construir_performance_summary()
    print(f"      n_evaluadas: {performance_summary.get('n_evaluadas', 0)} | "
          f"win_rate: {performance_summary.get('win_rate', 'N/A')}%")

    regimen = tesis_macro.get("regimen", {})

    web_data = {
        "metadata": {
            "fecha": date.today().isoformat(),
            "generado": datetime.now().isoformat(),
            "tesis_macro_fecha": tesis_macro.get("fecha", ""),
            "tesis_tecnica_fecha": tesis_tecnica.get("fecha", ""),
            "tesis_og_fecha": tesis_og.get("fecha", "") if tesis_og else "",
        },
        "regimen": {
            "clasificacion": regimen.get("clasificacion", "INDETERMINADO"),
            "confianza": regimen.get("confianza", 50),
            "razonamiento": regimen.get("razonamiento", ""),
        },
        "tesis_principal": tesis_macro.get("tesis_principal", ""),
        "senales": senales,
        "convicciones": convicciones,
        "energy_pulse": energy_pulse,
        "indicadores_clave": indicadores,
        "eventos_clave": tesis_macro.get("eventos_clave", []),
        "invalidadores": tesis_macro.get("invalidadores", []),
        "confianza_consolidada": calcular_confianza_consolidada(
            senales, regimen.get("confianza", 50)
        ),
        # ----- Track Record (added 2026-05-29) -----
        "track_record": track_record,
        "convicciones_pending": convicciones_pending,
        "performance_summary": performance_summary,
    }

    Path("data").mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(web_data, f, indent=2, ensure_ascii=False)

    print(f"\nGuardado en: {OUTPUT_PATH}")
    print(f"   Regimen macro: {web_data['regimen']['clasificacion']} ({web_data['regimen']['confianza']}%)")
    if energy_pulse:
        print(f"   Regimen oil: {energy_pulse['regimen_oil'].get('clasificacion', 'N/A')}")
        print(f"   Regimen natgas: {energy_pulse['regimen_natgas'].get('clasificacion', 'N/A')}")
        print(f"   Regimen lpg: {energy_pulse['regimen_lpg'].get('clasificacion', 'N/A')}")
    print(f"   Senales: {len(senales)}")
    print(f"   Convicciones (recientes): {len(convicciones)}")
    print(f"   Track record (cerradas): {len(track_record)}")
    print(f"   Pending (abiertas): {len(convicciones_pending)}")
    print(f"   Confianza consolidada: {web_data['confianza_consolidada']}%")


if __name__ == "__main__":
    exportar()
