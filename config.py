"""Configuracion compartida del proyecto.

Centraliza el nombre del modelo Claude que usan todos los agentes
(macro, technical, O&G, synthesizer) para que actualizar la version
sea un solo cambio en un solo lugar.
"""

from datetime import date, timedelta

MODEL = "claude-opus-5"

# Techo generoso para max_tokens en todas las llamadas a Claude.
# Los thinking blocks de Opus 5 se pagan de este mismo presupuesto; el techo
# alto previene que thinking + respuesta corten el JSON a la mitad. Es límite,
# no compra — solo se factura lo efectivamente generado.
MAX_TOKENS = 16000


def extract_text(response):
    """Concatena los bloques de texto de una respuesta de la API,
    ignorando bloques de thinking u otros tipos."""
    return "".join(
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    )


# --- Reloj del desk bancario -------------------------------------------------
# Los 7 bancos del universo (JPM, BAC, WFC, C, GS, MS, NU) cierran el 31-dic:
# el último FY completo es siempre el año calendario anterior. Los 10-Q se
# presentan ~30-40 días tras el cierre del trimestre; se usa 45 de colchón
# para decidir cuál es el "trimestre actual" seguro para consultar.

def fiscal_year_actual() -> int:
    """Último fiscal year completo. Los 7 bancos del universo cierran
    el 31-dic, así que es el año calendario anterior."""
    return date.today().year - 1


def trimestre_actual() -> tuple[int, int]:
    """Último trimestre calendario cuyos 10-Q ya están presentados.
    Los bancos presentan ~30-40 días tras el cierre; usamos 45 de
    colchón: retrocedemos 45 días y tomamos el último trimestre
    COMPLETO a esa fecha. Refinamiento futuro (TECHNICAL_DEBT):
    sondear el frame más nuevo y caer al anterior si viene vacío."""
    ref = date.today() - timedelta(days=45)
    q_ref = (ref.month - 1) // 3 + 1
    fin_dia = 31 if q_ref in (1, 4) else 30
    fin_q_ref = date(ref.year, q_ref * 3, fin_dia)
    if ref >= fin_q_ref:
        return (ref.year, q_ref)
    if q_ref == 1:
        return (ref.year - 1, 4)
    return (ref.year, q_ref - 1)
