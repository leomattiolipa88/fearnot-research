"""Configuracion compartida del proyecto.

Centraliza el nombre del modelo Claude que usan todos los agentes
(macro, technical, O&G, synthesizer) para que actualizar la version
sea un solo cambio en un solo lugar.
"""

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
