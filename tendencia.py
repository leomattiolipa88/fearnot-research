from typing import Optional


def analizar_tendencia(valores_por_trimestre: list) -> dict:
    """
    Analiza la tendencia de una metrica a lo largo de trimestres.

    Args:
        valores_por_trimestre: lista de (frame_label, valor) ORDENADA de mas
            VIEJO a mas NUEVO. Ej: [("CY2024Q4", 0.81), ("CY2025Q1", 0.85),
            ("CY2025Q2", 0.92), ("CY2025Q3", 1.05)]. Valores None se ignoran.

    Returns:
        dict con:
        - direccion: "subiendo" | "bajando" | "estable" | "insuficiente"
        - cambio_pct: cambio porcentual del primero al ultimo (None si no calculable)
        - trimestres_consecutivos: cuantos trimestres seguidos en la misma direccion
        - secuencia: los valores limpios usados
        - lectura: frase corta interpretable
    """
    # Filtrar None, mantener orden
    limpios = [(f, v) for f, v in valores_por_trimestre if v is not None]

    if len(limpios) < 2:
        return {
            "direccion": "insuficiente",
            "cambio_pct": None,
            "trimestres_consecutivos": 0,
            "secuencia": [v for _, v in limpios],
            "lectura": "Datos insuficientes para tendencia (se necesitan 2+ trimestres).",
        }

    valores = [v for _, v in limpios]
    primero, ultimo = valores[0], valores[-1]

    # Cambio porcentual punta a punta
    cambio_pct = None
    if primero != 0:
        cambio_pct = (ultimo - primero) / abs(primero) * 100

    # Contar trimestres consecutivos en la misma direccion (desde el final hacia atras)
    # Comparamos cada par consecutivo
    direcciones = []
    for i in range(1, len(valores)):
        delta = valores[i] - valores[i-1]
        if abs(delta) < abs(valores[i-1]) * 0.01:  # cambio <1% = estable
            direcciones.append("estable")
        elif delta > 0:
            direcciones.append("subiendo")
        else:
            direcciones.append("bajando")

    # Direccion dominante reciente: mirar la racha desde el final
    ult_dir = direcciones[-1]
    consecutivos = 1
    for d in reversed(direcciones[:-1]):
        if d == ult_dir:
            consecutivos += 1
        else:
            break

    # Direccion global: basada en el cambio punta a punta
    if cambio_pct is None:
        direccion = "estable"
    elif abs(cambio_pct) < 2:
        direccion = "estable"
    elif cambio_pct > 0:
        direccion = "subiendo"
    else:
        direccion = "bajando"

    # Lectura interpretable
    n = len(valores)
    if direccion == "estable":
        lectura = f"Estable a lo largo de {n} trimestres (cambio {cambio_pct:+.1f}%)."
    else:
        racha = ""
        if consecutivos >= 2 and ult_dir == direccion:
            racha = f" {consecutivos} trimestres consecutivos {ult_dir}."
        lectura = f"{direccion.capitalize()} {cambio_pct:+.1f}% en {n} trimestres.{racha}"

    return {
        "direccion": direccion,
        "cambio_pct": round(cambio_pct, 1) if cambio_pct is not None else None,
        "trimestres_consecutivos": consecutivos,
        "secuencia": valores,
        "lectura": lectura,
    }
