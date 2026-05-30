"""
Test de cobertura del nucleo de Banking (Phase 2).
====================================================

Verifica que los 3 conceptos del nucleo de banca (net_interest_income,
deposits, loans_held_for_investment) esten correctamente cableados y
traigan datos reales de SEC EDGAR para los 7 bancos del universo.

Dos modos:
  python3 tests/test_banking_coverage.py            -> Test A (routing, rapido, sin red)
  python3 tests/test_banking_coverage.py --live     -> Test A + Test B (descarga SEC, ~1-2 min)

Banca verificada empiricamente FY2024 (2026-05-30):
  - 4 conceptos x 7 bancos. not_found esperados:
    WFC/GS loans (LIMITATIONS #9), NU NII y NU provisions (filer quirk + #10).

Fuente de los conceptos: gaap_taxonomy.py (sector_overrides "bank")
                         + ifrs_taxonomy.py (NU, dispatch IFRS).
NO hay tags en este archivo: solo verificacion. Los tags viven en las taxonomies.
"""

import sys
import time

# Path para correr desde tests/ o desde la raiz
sys.path.insert(0, ".")
sys.path.insert(0, "..")

from sector_router import get_names_for_concept
from ifrs_taxonomy import is_ifrs_filer, get_ifrs_names_for_concept

BANCOS = ["JPM", "BAC", "WFC", "C", "GS", "MS", "NU"]
CONCEPTOS = ["net_interest_income", "deposits", "loans_held_for_investment", "provision_for_credit_losses"]

# not_found ESPERADO a nivel routing (solo el filer quirk de NU;
# a nivel routing WFC/GS SI resuelven el tag).
ESPERADO_ROUTING = {
    ("NU", "net_interest_income"),  # ni siquiera tiene tag (filer quirk IFRS)
}

# Conceptos que SI resuelven tag en routing pero cuyo tag NO tiene valor en el FY actual.
# No son "not_found" (el tag existe) ni "OK" pleno (el dato no fluye). Estado honesto aparte.
TAG_SIN_VALOR_ACTUAL = {
    ("NU", "provision_for_credit_losses"),  # tag FY2023 presente, FY2024 ausente (LIMITATIONS #10)
}

# not_found ESPERADO a nivel dato real (lo que el test live debe confirmar).
ESPERADO_LIVE = {
    ("WFC", "loans_held_for_investment"),  # LIMITATIONS #9
    ("GS",  "loans_held_for_investment"),  # LIMITATIONS #9
    ("NU",  "net_interest_income"),        # filer quirk IFRS
    ("NU",  "provision_for_credit_losses"), # FY2024 not_found (LIMITATIONS #10)
}


def _tags_para(banco, concepto):
    if is_ifrs_filer(banco):
        return get_ifrs_names_for_concept(concepto)
    return get_names_for_concept(concepto, banco)


def test_routing():
    """Test A: verifica que cada banco resuelve el tag correcto. No usa red."""
    print("=" * 74)
    print("TEST A - ROUTING DE TAGS (cableado interno, sin red)")
    print("=" * 74)
    print(f"\n{'Banco':6s} {'Concepto':28s} {'Tag que usaria':38s} Estado")
    print("-" * 74)

    ok = 0; esperados = 0; problemas = []
    for banco in BANCOS:
        for concepto in CONCEPTOS:
            tags = _tags_para(banco, concepto)
            tag = tags[0] if tags else None
            if tag and (banco, concepto) in TAG_SIN_VALOR_ACTUAL:
                estado = "OK (sin valor FY actual)"; ok += 1; tag_str = tag[:36]
            elif tag:
                estado = "OK"; ok += 1; tag_str = tag[:36]
            elif (banco, concepto) in ESPERADO_ROUTING:
                estado = "-- esperado"; esperados += 1; tag_str = "not_found (documentado)"
            else:
                estado = "!! PROBLEMA"; problemas.append((banco, concepto)); tag_str = "not_found (INESPERADO)"
            print(f"{banco:6s} {concepto:28s} {tag_str:38s} {estado}")
        print()

    print("=" * 74)
    print(f"RESUMEN A: {ok} OK | {esperados} not_found esperados | {len(problemas)} problemas")
    if problemas:
        for b, c in problemas:
            print(f"   PROBLEMA: {b} / {c}")
        return False
    print("Cableado correcto.")
    print("=" * 74)
    return True


def _buscar_valor_fy2024(facts, tags):
    if not facts:
        return None
    for tag in tags:
        for ns in ("us-gaap", "ifrs-full"):
            bloque = facts.get("facts", {}).get(ns, {})
            if tag not in bloque:
                continue
            usd = bloque[tag].get("units", {}).get("USD", [])
            cands = [r for r in usd if r.get("end") == "2024-12-31"]
            if cands:
                r = sorted(cands, key=lambda x: x.get("filed", ""))[-1]
                return r["val"]
    return None


def test_live():
    """Test B: descarga de SEC EDGAR y confirma valores reales FY2024."""
    from financials_extractor_v2 import obtener_cik, obtener_facts

    print("\n" + "=" * 74)
    print("TEST B - VALORES REALES FY2024 desde SEC EDGAR")
    print("=" * 74)

    ok = 0; esperados = 0; problemas = []
    for banco in BANCOS:
        print(f"\n{banco}:")
        cik = obtener_cik(banco)
        if not cik:
            print("  ERROR: no pude obtener CIK")
            problemas.append((banco, "CIK"))
            continue
        facts = obtener_facts(cik)
        for concepto in CONCEPTOS:
            tags = _tags_para(banco, concepto)
            val = _buscar_valor_fy2024(facts, tags)
            if val is not None:
                ok += 1
                print(f"  [OK]       {concepto:27s} = ${val/1e9:>9.1f}B")
            elif (banco, concepto) in ESPERADO_LIVE:
                esperados += 1
                print(f"  [esperado] {concepto:27s} = not_found (LIMITATIONS)")
            else:
                problemas.append((banco, concepto))
                print(f"  [!!]       {concepto:27s} = not_found (INESPERADO)")
        time.sleep(0.5)

    print("\n" + "=" * 74)
    print(f"RESUMEN B: {ok} con valor real | {esperados} not_found esperados | {len(problemas)} problemas")
    if problemas:
        for b, c in problemas:
            print(f"   PROBLEMA: {b} / {c}")
        return False
    print("El nucleo de banca fluye de punta a punta.")
    print("=" * 74)
    return True


if __name__ == "__main__":
    ok_a = test_routing()
    if "--live" in sys.argv:
        if ok_a:
            test_live()
        else:
            print("\nTest A fallo - no corro Test B hasta resolver el cableado.")
