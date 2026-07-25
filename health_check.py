#!/usr/bin/env python3
"""Guardián del pipeline diario.

Verifica que los outputs del día (tesis de los tres agentes + web_data.json)
existan, sean JSON válido, tengan tamaño razonable y contengan las claves
mínimas esperadas. Termina con exit 1 si cualquier check falla, exit 0 si
todo está sano.
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
MIN_SIZE_BYTES = 1024

THESIS_SPECS = [
    {
        "prefix": "tesis",
        "required_keys": ["fecha", "regimen", "tesis_principal"],
    },
    {
        "prefix": "tesis_tecnica",
        "required_keys": ["fecha", "regimen_macro_aplicado", "senales"],
    },
    {
        "prefix": "tesis_og",
        "required_keys": [
            "fecha",
            "tesis_principal",
            "regimen_oil",
            "regimen_natgas",
            "regimen_lpg",
        ],
    },
]


def last_business_day(today: date) -> date:
    d = today
    while d.weekday() >= 5:  # 5 = sábado, 6 = domingo
        d -= timedelta(days=1)
    return d


def check_thesis_file(spec: dict, target_date: date) -> tuple[bool, str]:
    fname = f"{spec['prefix']}_{target_date.isoformat()}.json"
    path = DATA_DIR / fname

    if not path.exists():
        return False, f"no existe ({path})"

    size = path.stat().st_size
    if size <= MIN_SIZE_BYTES:
        return False, f"pesa {size} B (<= {MIN_SIZE_BYTES} B)"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"JSON invalido: {e}"

    if not isinstance(data, dict):
        return False, "la raiz no es un objeto JSON"

    if "error" in data:
        return False, f'contiene clave "error" en raiz: {data["error"]!r}'

    missing = [k for k in spec["required_keys"] if k not in data]
    if missing:
        return False, f"faltan claves requeridas: {missing}"

    if data.get("fecha") != target_date.isoformat():
        return (
            False,
            f'fecha en JSON ({data.get("fecha")!r}) != esperada ({target_date.isoformat()})',
        )

    return True, f"OK ({size // 1024} KB)"


def check_web_data(today: date) -> tuple[bool, str]:
    path = DATA_DIR / "web_data.json"
    if not path.exists():
        return False, f"no existe ({path})"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"JSON invalido: {e}"

    meta = data.get("metadata")
    if not isinstance(meta, dict):
        return False, 'falta "metadata" o no es objeto'

    fecha = meta.get("fecha")
    if fecha != today.isoformat():
        return False, f'metadata.fecha ({fecha!r}) != hoy ({today.isoformat()})'

    return True, "OK"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Health check del pipeline diario.")
    p.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "Corre todos los checks contra esta fecha (tesis y web_data.metadata.fecha). "
            "Sin el flag: hoy UTC para web_data y ultimo dia habil para tesis."
        ),
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.date is not None:
        web_date = args.date
        thesis_date = args.date
        print(f"Health check — fecha forzada (--date) = {args.date.isoformat()}")
    else:
        web_date = datetime.now(timezone.utc).date()
        thesis_date = last_business_day(web_date)
        print(
            f"Health check — hoy UTC = {web_date.isoformat()}, "
            f"dia habil de tesis = {thesis_date.isoformat()}"
        )
    print("-" * 60)

    all_ok = True

    for spec in THESIS_SPECS:
        ok, msg = check_thesis_file(spec, thesis_date)
        mark = "OK " if ok else "FAIL"
        print(f"[{mark}] {spec['prefix']}_{thesis_date.isoformat()}.json — {msg}")
        all_ok = all_ok and ok

    ok, msg = check_web_data(web_date)
    mark = "OK " if ok else "FAIL"
    print(f"[{mark}] web_data.json — {msg}")
    all_ok = all_ok and ok

    print("-" * 60)
    if all_ok:
        print("Todos los checks pasaron.")
        return 0
    print("Uno o mas checks fallaron.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
