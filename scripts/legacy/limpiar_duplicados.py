"""
Limpia señales duplicadas en la DB según Modelo B (Position Holder).

Lógica:
- Para cada combinación (activo, direccion, horizonte), iterar señales por fecha
- Conservar la primera. Marcar como "duplicada" cualquier señal dentro
  de los N días siguientes (N = horizonte en días)
- Cuando pasa el horizonte, la siguiente señal cuenta como nueva apertura

Uso:
    python3 limpiar_duplicados.py            # DRY RUN (no modifica nada)
    python3 limpiar_duplicados.py --execute  # Ejecuta la limpieza real
"""

import sqlite3
import sys
from datetime import datetime, timedelta
from collections import defaultdict

DB_PATH = "data/macro.db"

DIAS_POR_HORIZONTE = {
    "SEMANAL": 5,
    "MENSUAL": 21,
    "TRIMESTRAL": 63,
}


def analizar_y_marcar(execute=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    senales = conn.execute("""
        SELECT id, fecha_senal, activo, direccion, horizonte,
               precio_entrada, evaluado, fuente
        FROM senales
        ORDER BY activo, direccion, horizonte, fecha_senal, id
    """).fetchall()

    # Agrupar por (activo, direccion, horizonte)
    grupos = defaultdict(list)
    for s in senales:
        key = (s["activo"], s["direccion"], s["horizonte"])
        grupos[key].append(dict(s))

    a_conservar = []
    a_borrar = []

    for key, grupo in grupos.items():
        activo, direccion, horizonte = key
        dias_horizonte = DIAS_POR_HORIZONTE.get(horizonte, 21)

        # Ordenar por fecha + id (estable)
        grupo.sort(key=lambda x: (x["fecha_senal"], x["id"]))

        # Lógica de ventana
        ultima_apertura = None
        for s in grupo:
            fecha = datetime.strptime(s["fecha_senal"], "%Y-%m-%d").date()

            if ultima_apertura is None:
                # Primera señal del grupo: conservar
                a_conservar.append(s)
                ultima_apertura = fecha
            else:
                dias_desde_apertura = (fecha - ultima_apertura).days
                if dias_desde_apertura >= dias_horizonte:
                    # Pasó el horizonte: esta es una NUEVA apertura
                    a_conservar.append(s)
                    ultima_apertura = fecha
                else:
                    # Dentro del horizonte: es duplicado conceptual
                    a_borrar.append(s)

    # Reporte
    print("=" * 70)
    print(f"ANÁLISIS DE DUPLICADOS — Modelo B (Position Holder)")
    print("=" * 70)
    print(f"\nTotal señales en DB:        {len(senales)}")
    print(f"Señales únicas (conservar): {len(a_conservar)}")
    print(f"Señales a borrar:           {len(a_borrar)}")
    print(f"Reducción:                  {len(a_borrar)/len(senales)*100:.1f}%")

    # Desglose por grupo
    print(f"\n{'Activo':<8} {'Dir':<8} {'Horiz':<12} {'Total':>6} {'Únicas':>7} {'Borrar':>7}")
    print("-" * 60)
    for key in sorted(grupos.keys()):
        activo, direccion, horizonte = key
        total_grupo = len(grupos[key])
        conservar_grupo = sum(1 for s in a_conservar
                              if (s["activo"], s["direccion"], s["horizonte"]) == key)
        borrar_grupo = total_grupo - conservar_grupo
        if total_grupo > 1:
            print(f"{activo:<8} {direccion:<8} {horizonte:<12} {total_grupo:>6} {conservar_grupo:>7} {borrar_grupo:>7}")

    # Detalle de las primeras 15 señales que vamos a borrar
    print(f"\n{'='*70}")
    print(f"MUESTRA DE SEÑALES A BORRAR (primeras 15):")
    print(f"{'='*70}")
    print(f"{'ID':<6} {'Fecha':<12} {'Activo':<8} {'Dir':<8} {'Horiz':<12} {'Evaluado':<10}")
    for s in a_borrar[:15]:
        evaluado_str = "SÍ" if s["evaluado"] else "no"
        print(f"{s['id']:<6} {s['fecha_senal']:<12} {s['activo']:<8} "
              f"{s['direccion']:<8} {s['horizonte']:<12} {evaluado_str:<10}")

    # Warning si vamos a borrar señales evaluadas
    evaluadas_a_borrar = [s for s in a_borrar if s["evaluado"]]
    if evaluadas_a_borrar:
        print(f"\n⚠️  ATENCIÓN: {len(evaluadas_a_borrar)} de las señales a borrar ya fueron evaluadas.")
        print(f"   Su data de retorno se perderá. Es intencional bajo Modelo B")
        print(f"   (eran evaluaciones de duplicados, no de trades reales nuevos).")

    # Ejecución real
    if execute:
        print(f"\n{'='*70}")
        print("EJECUTANDO LIMPIEZA...")
        print(f"{'='*70}")
        ids_a_borrar = [s["id"] for s in a_borrar]
        placeholders = ",".join("?" * len(ids_a_borrar))
        conn.execute(f"DELETE FROM senales WHERE id IN ({placeholders})", ids_a_borrar)
        conn.commit()
        print(f"✓ {len(a_borrar)} señales borradas.")
        print(f"✓ {len(a_conservar)} señales conservadas.")
    else:
        print(f"\n{'='*70}")
        print("DRY RUN — Ninguna señal fue borrada.")
        print("Para ejecutar la limpieza real: python3 limpiar_duplicados.py --execute")
        print(f"{'='*70}")

    conn.close()


if __name__ == "__main__":
    execute = "--execute" in sys.argv
    analizar_y_marcar(execute=execute)
