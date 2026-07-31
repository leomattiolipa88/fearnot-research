"""Configuracion compartida del proyecto.

Centraliza el nombre del modelo Claude que usan todos los agentes
(macro, technical, O&G, synthesizer) para que actualizar la version
sea un solo cambio en un solo lugar.
"""

MODEL = "claude-opus-5"


def extract_text(response):
    """Concatena los bloques de texto de una respuesta de la API,
    ignorando bloques de thinking u otros tipos."""
    return "".join(
        block.text for block in response.content
        if getattr(block, "type", None) == "text"
    )
