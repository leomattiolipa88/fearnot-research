"""
Test exploratorio 2: navegar la estructura de un fact específico.
Objetivo: entender cómo SEC EDGAR organiza los datos por período.
"""

import requests
import json

CIK = "0000034088"
headers = {
    "User-Agent": "FearNot Research boschibasilio@gmail.comm"
}

url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json"
response = requests.get(url, headers=headers)
data = response.json()

# Vamos a buscar el Revenue (Revenues en taxonomía GAAP)
gaap = data["facts"]["us-gaap"]

# Probemos varios nombres posibles para Revenue
posibles_revenue = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", 
                    "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]

print("=" * 70)
print("Buscando Revenue en SEC EDGAR...")
print("=" * 70)

for nombre in posibles_revenue:
    if nombre in gaap:
        print(f"\n✓ ENCONTRADO: '{nombre}'")
        fact = gaap[nombre]
        print(f"  Label: {fact.get('label')}")
        print(f"  Description: {fact.get('description', 'N/A')[:200]}")
        print(f"  Units disponibles: {list(fact.get('units', {}).keys())}")
        
        # Ver los datos en USD
        if 'USD' in fact['units']:
            datos = fact['units']['USD']
            print(f"\n  Cantidad de períodos reportados: {len(datos)}")
            print(f"\n  Primeros 5 períodos:")
            for d in datos[:5]:
                print(f"    {d}")
            print(f"\n  Últimos 5 períodos (más recientes):")
            for d in datos[-5:]:
                print(f"    {d}")
        break
    else:
        print(f"  ✗ '{nombre}' no encontrado")
