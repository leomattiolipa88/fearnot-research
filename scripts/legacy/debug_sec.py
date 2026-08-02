"""
Debug: ver TODOS los records de Revenue para entender qué pasa.
"""
import requests
import json

HEADERS = {"User-Agent": "FearNot Research boschibasilio@gmail.com"}
url = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000034088.json"
data = requests.get(url, headers=HEADERS).json()

revenue_records = data["facts"]["us-gaap"]["Revenues"]["units"]["USD"]

# Filtrar solo los FY 2025 (con mi lógica actual)
print("=" * 80)
print("Records donde fy=2025 y fp='FY' (mi filtro actual)")
print("=" * 80)
matching = [r for r in revenue_records if r.get("fy") == 2025 and r.get("fp") == "FY"]
for r in matching:
    val_b = r["val"] / 1e9
    print(f"  start={r['start']} end={r['end']} val=${val_b:.1f}B form={r['form']} filed={r['filed']}")

print()
print("=" * 80)
print("Records donde end='2025-12-31' (filtro correcto)")
print("=" * 80)
correctos = [r for r in revenue_records if r.get("end") == "2025-12-31" and r.get("start") == "2025-01-01"]
for r in correctos:
    val_b = r["val"] / 1e9
    print(f"  start={r['start']} end={r['end']} val=${val_b:.1f}B fy={r['fy']} fp={r['fp']} form={r['form']} filed={r['filed']}")
