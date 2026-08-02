"""
Test: obtener CIK desde ticker usando la tabla pública de SEC.
"""

import requests
import json

HEADERS = {
    "User-Agent": "FearNot Research boschibasilio@gmail.com"
}

# Endpoint que devuelve mapping ticker -> CIK para TODAS las empresas SEC
url = "https://www.sec.gov/files/company_tickers.json"

print("Descargando mapping ticker -> CIK...")
response = requests.get(url, headers=HEADERS)
data = response.json()

print(f"Total empresas en SEC: {len(data)}")
print(f"\nPrimeros 3 ejemplos del JSON:")
for i in list(data.keys())[:3]:
    print(f"  {data[i]}")

# Buscar algunos tickers especificos
tickers_a_buscar = ["MELI", "NU", "BRK-B", "BRK.B", "BRKB"]

print(f"\nBuscando tickers especificos:")
for ticker in tickers_a_buscar:
    encontrado = False
    for key in data:
        if data[key].get("ticker") == ticker:
            print(f"  {ticker:6} -> CIK {data[key]['cik_str']:>10} | {data[key]['title']}")
            encontrado = True
            break
    if not encontrado:
        print(f"  {ticker:6} -> NO ENCONTRADO")
