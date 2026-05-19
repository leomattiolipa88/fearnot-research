"""
FearNot - O&G + LPG News Collector

Recolecta noticias del sector energetico via NewsAPI.
Cuatro categorias:
1. OPEC + production decisions
2. Geopolitica energetica (Iran, Venezuela, Russia, Middle East)
3. Operacional (refinery outages, pipelines, hurricanes)
4. LPG / Petrochem (propane, LPG Asia, VLGC, ethylene)

Datos persistidos en data/macro.db tabla noticias_og.
"""

import os
import sqlite3
import requests
from datetime import datetime, date, timedelta
from pathlib import Path

DB_PATH = "data/macro.db"


# ----------------- Cargar API keys -----------------
def cargar_env():
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()


# ----------------- Categorias de queries -----------------
QUERIES = {
    "OPEC y produccion": [
        "OPEC production",
        "Saudi Arabia oil",
        "Russia oil exports",
        "shale oil production USA",
    ],
    "Geopolitica energetica": [
        "Iran oil sanctions",
        "Strait of Hormuz",
        "Venezuela oil",
        "Russia natural gas Europe",
    ],
    "Operacional": [
        "refinery outage",
        "oil pipeline disruption",
        "hurricane oil Gulf Mexico",
        "LNG terminal",
    ],
    "LPG y petrochem": [
        "propane prices",
        "LPG Asia demand",
        "ethylene cracker",
        "VLGC freight rates",
    ],
}


# ----------------- DB helpers -----------------
def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    Path("data").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS noticias_og (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_descarga  TEXT NOT NULL,
            categoria       TEXT NOT NULL,
            query           TEXT NOT NULL,
            titulo          TEXT NOT NULL,
            descripcion     TEXT,
            fuente          TEXT,
            url             TEXT,
            published_at    TEXT,
            UNIQUE(titulo, fecha_descarga)
        )
    """)
    conn.commit()
    return conn


# ----------------- Recolectar noticias -----------------
def recolectar_noticias(conn: sqlite3.Connection):
    api_key = os.environ.get("NEWS_API_KEY", "")
    if not api_key:
        print("ERROR: Falta NEWS_API_KEY en .env")
        return

    base_url = "https://newsapi.org/v2/everything"
    fecha_descarga = datetime.now().isoformat()
    desde = (date.today() - timedelta(days=2)).isoformat()

    total_articulos = 0
    fallos = []

    print("\n" + "=" * 60)
    print(f"O&G News Collector - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    for categoria, queries in QUERIES.items():
        print(f"\n[{categoria}]")
        articulos_categoria = 0

        for query in queries:
            try:
                params = {
                    "q": query,
                    "from": desde,
                    "sortBy": "relevancy",
                    "language": "en",
                    "pageSize": 5,
                    "apiKey": api_key,
                }
                response = requests.get(base_url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()

                if data.get("status") != "ok":
                    fallos.append(f"{query}: {data.get('message', 'unknown error')}")
                    continue

                articulos = data.get("articles", [])
                for art in articulos:
                    titulo = art.get("title", "")[:500]
                    if not titulo or titulo == "[Removed]":
                        continue
                    try:
                        conn.execute("""
                            INSERT OR IGNORE INTO noticias_og
                            (fecha_descarga, categoria, query, titulo,
                             descripcion, fuente, url, published_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            fecha_descarga,
                            categoria,
                            query,
                            titulo,
                            (art.get("description") or "")[:1000],
                            (art.get("source", {}).get("name") or "")[:100],
                            (art.get("url") or "")[:500],
                            art.get("publishedAt", ""),
                        ))
                        articulos_categoria += 1
                        total_articulos += 1
                    except Exception as e:
                        pass  # ignorar duplicados o errores menores

            except Exception as e:
                fallos.append(f"{query}: {e}")

        print(f"      OK {articulos_categoria} articulos")

    conn.commit()

    print("\n" + "=" * 60)
    print(f"Total: {total_articulos} articulos recolectados")
    if fallos:
        print(f"Fallos: {len(fallos)}")
        for f in fallos[:5]:
            print(f"   {f}")
    print("=" * 60)


# ----------------- Main -----------------
def main():
    cargar_env()
    conn = init_db()
    recolectar_noticias(conn)
    conn.close()


if __name__ == "__main__":
    main()
