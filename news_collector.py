"""
Macro Agent — Colector de Noticias
Usa /v2/top-headlines de NewsAPI (compatible con plan gratuito).
DNA: Soros — los mercados se mueven por narrativas antes que por datos.
"""

import re
import requests
import json
import os
from datetime import datetime
from pathlib import Path

NEWSAPI_HEADLINES = "https://newsapi.org/v2/top-headlines"

# Categorías de NewsAPI disponibles en plan free
CATEGORIAS = ["business", "technology", "general"]

# Fuentes tier 1
FUENTES_TIER1 = [
    "reuters.com", "bloomberg.com", "ft.com",
    "wsj.com", "cnbc.com", "economist.com",
    "apnews.com", "bbc.com"
]

# Palabras clave para filtrar noticias relevantes para mercados
KEYWORDS_MERCADOS = [
    # Política monetaria
    "fed", "federal reserve", "interest rate", "inflation", "cpi", "pce",
    "central bank", "ecb", "bank of japan", "rate hike", "rate cut",
    # Mercados
    "stock", "market", "dow", "s&p", "nasdaq", "rally", "selloff", "crash",
    "oil", "gold", "dollar", "yield", "bond", "treasury",
    # Macro
    "gdp", "recession", "jobs", "unemployment", "payroll", "economy",
    "trade", "tariff", "sanctions", "growth",
    # Tech/AI
    "ai", "artificial intelligence", "nvidia", "chip", "semiconductor",
    "tech", "robot", "automation", "data center",
    # Geopolítica financiera
    "war", "conflict", "opec", "energy", "supply chain",
    "china", "geopolit", "crisis",
]


def fetch_noticias(api_key: str, max_por_categoria: int = 10) -> list:
    """Descarga top headlines por categoría."""
    todos = []

    for categoria in CATEGORIAS:
        try:
            resp = requests.get(
                NEWSAPI_HEADLINES,
                params={
                    "category": categoria,
                    "language": "en",
                    "pageSize": max_por_categoria,
                    "apiKey": api_key,
                },
                timeout=10,
            )
            resp.raise_for_status()
            articulos = resp.json().get("articles", [])

            for art in articulos:
                titulo = art.get("title", "")
                descripcion = art.get("description", "") or ""
                if not titulo or titulo == "[Removed]":
                    continue

                # Filtrar solo noticias relevantes para mercados
                texto = (titulo + " " + descripcion).lower()
                es_relevante = any(kw in texto for kw in KEYWORDS_MERCADOS)
                if not es_relevante:
                    continue

                url = art.get("url", "")
                tier = 1 if any(f in url for f in FUENTES_TIER1) else 2

                todos.append({
                    "categoria":   categoria,
                    "titulo":      titulo,
                    "descripcion": descripcion[:200],
                    "fuente":      art.get("source", {}).get("name", ""),
                    "url":         url,
                    "publicado":   art.get("publishedAt", ""),
                    "tier":        tier,
                })

        except Exception as e:
            print(f"   ⚠️  Error en {categoria}: {e}")
            continue

    # Ordenar: tier 1 primero
    todos.sort(key=lambda x: x["tier"])

    # Deduplicar
    vistos = set()
    resultado = []
    for art in todos:
        key = art["titulo"][:60].lower()
        if key not in vistos:
            vistos.add(key)
            resultado.append(art)

    return resultado


def evaluar_impacto(titulo: str, descripcion: str) -> str:
    texto = (titulo + " " + descripcion).lower()
    palabras_alto = [
        "crash", "crisis", "collapse", "emergency", "shock", "record",
        "historic", "default", "panic", "intervention", "plunge", "surge",
        "unexpected", "surprise", "jump", "tumble"
    ]
    palabras_medio = [
        "rise", "fall", "rally", "selloff", "higher", "lower",
        "beats", "misses", "concern", "warning", "drop"
    ]
    if any(p in texto for p in palabras_alto):
        return "ALTO"
    elif any(p in texto for p in palabras_medio):
        return "MEDIO"
    return "BAJO"


_CATEGORIAS_KEYWORDS = [
    # Orden = prioridad. El primer keyword que matchea como palabra completa gana.
    # Fix 2026-08-01: antes usábamos `in` (substring), y "fed" matcheaba
    # "federation" — titulares tipo "FIFA federation boycott" caían en
    # POLÍTICA MONETARIA. Ahora requerimos word boundary con regex.
    ("POLÍTICA MONETARIA",        ["fed", "central bank", "rate", "inflation", "cpi"]),
    ("TECH Y AI",                 ["ai", "nvidia", "chip", "tech", "robot", "semiconductor"]),
    ("COMMODITIES Y GEOPOLÍTICA", ["oil", "gold", "commodity", "opec", "energy"]),
    ("MERCADOS",                  ["stock", "market", "dow", "nasdaq", "s&p", "rally", "selloff"]),
    ("FX Y TASAS",                ["dollar", "yield", "bond", "treasury", "currency"]),
]


def formatear_para_agente(noticias: list) -> str:
    if not noticias:
        return (
            "Sin noticias relevantes disponibles. "
            "Reducir confianza general en 15 puntos."
        )

    # Clasificar por fuerza macro. Default OTROS explícito: un titular sin
    # match claro no es "macro global", es simplemente no clasificable —
    # y el agente lo debería tratar como ruido, no como señal macro.
    def clasificar(art):
        texto = (art["titulo"] + " " + art["descripcion"]).lower()
        for categoria, keywords in _CATEGORIAS_KEYWORDS:
            for kw in keywords:
                if re.search(r"\b" + re.escape(kw) + r"\b", texto):
                    return categoria
        return "OTROS"

    por_fuerza = {}
    for art in noticias:
        fuerza = clasificar(art)
        if fuerza not in por_fuerza:
            por_fuerza[fuerza] = []
        por_fuerza[fuerza].append(art)

    lineas = [
        "=== CONTEXTO DE MERCADO — HEADLINES DE HOY ===",
        "(Clasificados por fuerza estructural de impacto macro)\n",
    ]

    for fuerza, arts in por_fuerza.items():
        lineas.append(f"▶ {fuerza}:")
        for art in arts[:4]:
            impacto = evaluar_impacto(art["titulo"], art["descripcion"])
            tier_label = "★" if art["tier"] == 1 else "·"
            impacto_label = {"ALTO": "⚡", "MEDIO": "→", "BAJO": "·"}.get(impacto, "·")
            lineas.append(
                f"  {tier_label}{impacto_label} [{art['fuente']}] {art['titulo']}"
            )
            if art["descripcion"]:
                lineas.append(f"     {art['descripcion']}")
        lineas.append("")

    lineas += [
        "★ = Fuente tier 1 | ⚡ = Impacto alto | → = Impacto medio",
        "",
        "INSTRUCCIONES:",
        "- Usá estas noticias para entender POR QUÉ se mueven los indicadores.",
        "- Si una noticia contradice un indicador macro, explicá la divergencia.",
        "- Eventos de impacto ALTO deben reflejarse en los invalidadores.",
    ]

    return "\n".join(lineas)


def guardar_cache(noticias: list, path: str = "data/noticias_cache.json"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"timestamp": datetime.now().isoformat(), "noticias": noticias},
                  f, indent=2, ensure_ascii=False)


def cargar_cache(path: str = "data/noticias_cache.json",
                 max_edad_minutos: int = 30) -> list | None:
    try:
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
        edad = (datetime.now() -
                datetime.fromisoformat(cache["timestamp"])).total_seconds() / 60
        if edad < max_edad_minutos:
            print(f"   Usando cache ({edad:.0f} min)")
            return cache["noticias"]
    except Exception:
        pass
    return None


def obtener_contexto_noticias(api_key: str | None = None) -> str:
    if not api_key:
        api_key = os.environ.get("NEWS_API_KEY", "")
    if not api_key:
        return (
            "⚠️  Sin NEWS_API_KEY. "
            "Reducir confianza general 15 puntos por falta de contexto narrativo."
        )

    noticias = cargar_cache()
    if noticias is None:
        print("   Descargando headlines...")
        noticias = fetch_noticias(api_key)
        if noticias:
            guardar_cache(noticias)
            print(f"   ✓ {len(noticias)} noticias relevantes")
        else:
            return "Sin noticias disponibles. Ser conservador en el análisis."

    return formatear_para_agente(noticias)


if __name__ == "__main__":
    api_key = os.environ.get("NEWS_API_KEY", "")
    if not api_key:
        print("ERROR: export NEWS_API_KEY=tu_key")
        exit(1)

    print("Descargando headlines...\n")
    noticias = fetch_noticias(api_key)
    print(f"{len(noticias)} noticias relevantes encontradas\n")
    print(formatear_para_agente(noticias))
