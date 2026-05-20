# FearNot Research

> *In chaos, fear not.*

A multi-agent macro and sector research system. Three Claude-powered agents read markets, classify regimes, and write daily theses. One synthesizer turns the noise into weekly convictions. Everything is timestamped, JSON-serialized, and auditable.

The world is loud. Most macro commentary is louder. This system was built on the heretical premise that maybe an LLM with structured data and a clear mandate can do better than a thread of takes from people who do not know what a Sahm rule is.

---

## What it does

- **Daily macro thesis** — Classifies the current regime (Goldilocks, Reflation, Stagflation, Recession) from ~28 FRED indicators. Generates LONG/SHORT signals on SPY, TLT, GLD, DXY with conviction scores and invalidation triggers.
- **Technical thesis** — Momentum, breadth, VIX term structure, options flow. Same output shape, different lens.
- **Energy desk** — Oil & gas thesis from EIA data and sector news. Treats commodities as their own asset class because they refuse to behave like equities.
- **Weekly synthesis** — Pulls all three threads into a single conviction book on Mondays.
- **Signal tracker** — Every signal gets an entry price and an expiration horizon. When the horizon hits, it gets evaluated. No revisionism.
- **SEC financials extractor (v2)** — Pulls fundamentals from 10-K/10-Q filings for 13 tickers across Tech and Energy. Handles non-calendar fiscal years (MSFT, NVDA, CRM, MU) without choking.

---

## Architecture

```
Macro Agent      Technical Agent      O&G Agent
    |                  |                  |
    v                  v                  v
tesis.json    tesis_tecnica.json    tesis_og.json
    |                  |                  |
    +------------------+------------------+
                       |
                       v
                  Synthesizer  (runs weekly, Mondays)
                       |
                       v
              convicciones.json
                       |
                       v
                web_exporter.py
                       |
                       v
        fearnot-web/public/web_data.json
                       |
                       v
              fearnot-web.vercel.app
```

Each agent has its own data collector (FRED, EIA, NewsAPI, options flow) and writes a structured JSON thesis. The synthesizer is the only stage allowed to overrule them.

---

## Track record

Every thesis the system has ever generated lives in data/, untouched. No backfills, no edits, no I-would-have-said. Files are timestamped at the moment of generation.

- tesis_YYYY-MM-DD.json — Macro
- tesis_tecnica_YYYY-MM-DD.json — Technical
- tesis_og_YYYY-MM-DD.json — Oil & Gas
- convicciones_YYYY-MM-DD.json — Weekly synthesis

First thesis: **April 7, 2026.** Performance attribution and signal evaluation: coming once the tracker has enough resolved signals to mean anything.

---

## Stack

- **Python 3** — All agents and collectors
- **Claude API** (Anthropic) — Reasoning engine for every agent
- **SQLite** — Local time-series storage
- **FRED / EIA / NewsAPI** — Data sources
- **Next.js + Vercel** — Frontend at [fearnot-web.vercel.app](https://fearnot-web.vercel.app)

Roughly 11,500 lines of Python at first commit. None of them load-bearing for anyone retirement.

---

## Getting started

```
# 1. Clone
git clone https://github.com/leomattiolipa88/fearnot-research.git
cd fearnot-research

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment variables
cp .env.example .env
# Edit .env with your own API keys (Anthropic, FRED, EIA, NewsAPI)

# 4. Run the daily pipeline
./update_web.sh
```

You will need API keys for: Anthropic (Claude), FRED (macro data, free), EIA (energy data, free), and NewsAPI (news, free tier).

---

## Roadmap

The current state is the macro + technical + energy stack. The destination is a desk:

- [x] Macro agent
- [x] Technical agent
- [x] Energy desk (O&G)
- [ ] Commodities agent (beyond O&G: copper, lithium, ags)
- [ ] AI & Tech agent
- [ ] Argentina agent (local macro, sovereign, equities)
- [ ] Multi-agent orchestrator
- [ ] Public dashboard with conviction history and resolved signals

The point is not to be right about everything. The point is to be wrong on the record, in writing, with timestamps.

---

## Disclaimer

This is research, not investment advice. Nothing in this repository is a solicitation to buy or sell any security. The agents are wrong sometimes. Possibly often. Read accordingly. If you are making portfolio decisions based on a JSON file from a public GitHub repo, the problem is upstream of this disclaimer.

---

## Built by

**Basilio Boschi** — Economics, Universidad Torcuato Di Tella (UTDT) · Buenos Aires

GitHub: [@leomattiolipa88](https://github.com/leomattiolipa88)
