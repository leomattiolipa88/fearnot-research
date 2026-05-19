"""
Sector Router — Decide que mapeo GAAP aplicar para cada ticker.
================================================================

Punto unico de entrada para resolver "que nombres GAAP probar para
el concepto X en la empresa Y".

Logica:
1. Detectar sector del ticker (energy, banking, tech, etc.)
2. Si el sector tiene overrides para el concepto pedido, usarlos PRIMERO
3. Despues fallback a los nombres del mapeo general

Si el ticker no esta clasificado en ningun sector, devuelve solo los
nombres del mapeo general (comportamiento default).

Fuente: arquitectura sector-specific normalization
        (ver SECTOR_RESEARCH_OVERVIEW.md)
"""

from typing import Optional
from gaap_taxonomy import GAAP_TAXONOMY, get_names_for_concept as _get_general_names

# Importar cada sector module
from sector_mappings import energy
# from sector_mappings import banking   # TODO: agregar cuando se implemente
# from sector_mappings import insurance # TODO
# from sector_mappings import tech      # TODO
# from sector_mappings import industrial # TODO
# from sector_mappings import utilities # TODO


# ============================================================
# DETECCION DE SECTOR
# ============================================================
def detect_sector(ticker: str) -> Optional[str]:
    """
    Detecta a que sector pertenece un ticker.

    Returns:
        nombre del sector como string ("energy", "banking", etc.)
        o None si el ticker no esta clasificado.
    """
    ticker_upper = ticker.upper()

    if energy.is_energy_ticker(ticker_upper):
        return "energy"

    # Cuando se agreguen otros sectores:
    # if banking.is_banking_ticker(ticker_upper):
    #     return "banking"
    # if insurance.is_insurance_ticker(ticker_upper):
    #     return "insurance"
    # etc.

    return None


# ============================================================
# RESOLUCION DE NOMBRES GAAP CON ROUTING
# ============================================================
def get_names_for_concept(concept: str, ticker: Optional[str] = None) -> list:
    """
    Devuelve la lista de nombres GAAP a probar para un concepto.

    Si el ticker pertenece a un sector con overrides definidos para
    el concepto, los nombres del sector van PRIMERO. Despues los
    generales como fallback.

    Args:
        concept: nombre del concepto (ej: "revenue", "operating_income")
        ticker: ticker de la empresa (opcional). Si no se pasa,
                devuelve solo los nombres generales.

    Returns:
        Lista de nombres GAAP ordenada por preferencia. Vacia si el
        concepto no existe en taxonomy ni en sector overrides.
    """
    sector_names = []

    if ticker:
        sector = detect_sector(ticker)
        if sector == "energy":
            sector_names = energy.get_energy_gaap_names(concept)
        # Cuando se agreguen otros sectores:
        # elif sector == "banking":
        #     sector_names = banking.get_banking_gaap_names(concept)

    general_names = _get_general_names(concept, ticker)

    # Combinar sin duplicados, manteniendo orden (sector primero)
    seen = set()
    combined = []
    for name in sector_names + general_names:
        if name not in seen:
            combined.append(name)
            seen.add(name)

    return combined


# ============================================================
# HELPERS ADICIONALES
# ============================================================
def get_sector_info(ticker: str) -> dict:
    """
    Devuelve informacion sobre el sector de un ticker.
    Util para debugging y reports.
    """
    sector = detect_sector(ticker)
    info = {
        "ticker": ticker.upper(),
        "sector": sector or "unclassified",
    }

    if sector == "energy":
        info["has_specific_metrics"] = True
        info["sector_metrics"] = list(energy.ENERGY_SPECIFIC_METRICS.keys())
        info["validation_rules"] = list(energy.ENERGY_VALIDATION_RULES.keys())

    return info


if __name__ == "__main__":
    print("Sector Router loaded.")
    print()
    print("Tests de routing:")
    print()

    for ticker in ["XOM", "META", "NU", "VLO", "AMCR"]:
        sector = detect_sector(ticker)
        names_revenue = get_names_for_concept("revenue", ticker)
        print(f"  {ticker:6s}: sector={sector or 'unclassified':12s} "
              f"revenue_names[0..2]={names_revenue[:3]}")

    print()
    print("Info detallada para XOM:")
    info = get_sector_info("XOM")
    for k, v in info.items():
        print(f"  {k}: {v}")
