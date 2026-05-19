# AI/Tech Development Roadmap — FearNot Research, Global Macro Pivot, Quant/AI-Lab Internships

**Honest mentor framing up front:** This is a decision-ready 6–12 month plan for an 18-year-old UTDT Economics student building FearNot Research and aiming at US/EU quant and AI-lab internships for 2026–2027. The single biggest finding to internalize: **your Italian passport is the most valuable single asset in your stack** — it bypasses the US-work-authorization wall that filters out most Argentine candidates and puts you on equal footing with EU undergrads at Jane Street London/Amsterdam, Optiver Amsterdam, IMC Amsterdam, Citadel London, and HRT London. Plan the EU path as primary, US as the stretch.

UTDT does not appear on standard target-school lists for US quant shops, and a targeted research pass found **no public, indexed UTDT alumni at Jane Street, Citadel, Two Sigma, HRT, Optiver, IMC, or DRW** as quant traders/researchers. UTDT's documented US pipeline is Economics PhD → academia (MIT, Harvard, Stanford GSB, Fed/IMF), not direct undergrad → quant. Your differentiators must therefore be: (1) a real, technical, finance-specific product shipped publicly (FearNot), (2) verifiable open-source contributions, and (3) an olympiad-substitute credential (Kaggle medal, published replication, or a non-trivial merged PR). This roadmap is built around that reality.

---

## PART 1 — LEARNING ROADMAP (Next 6–12 months, 14 h/week)

### Strategic frame: ruthless cuts before the curriculum

- **Skip deep reinforcement learning for trading.** Per IG South Africa's Nov 2024 piece *"Is the Impact of AI on Hedge Funds Overhyped?"* citing Eurekahedge's own index data: "From December 2009 to July 2024, the [Eurekahedge AI Hedge Fund] index produced a 9.8% annualised return, versus 13.7% for the S&P 500." HRT's own AI Lab blog ("In Trading, Machine Learning Benchmarks Don't Track What You Care About") states they evaluate ML papers on "simplicity, reproducibility, and generality" and rarely apply them directly. Dave Cliff (Bristol CS), in *"Methods Matter: A Trading Agent with No Intelligence Routinely Outperforms AI-Based Traders"* (arxiv 2011.14346), shows "some of the reportedly best-performing public-domain AI/ML trading strategies can routinely be out-performed by extremely simple trading strategies that involve no AI or ML at all." Allocate **zero** hours to deep RL-for-trading until you have a working classical ML pipeline.
- **Skip Stanford CS336 full sequence.** CS336 (Spring 2025/2026, Tatsunori Hashimoto & Percy Liang) trains Transformers from scratch including a Triton FlashAttention2 implementation — ~80h lectures + 200h assignments. Your ROI is in *using and orchestrating* LLMs, not building them. Exception: if you target a frontier-lab residency, do **Assignment 1 only** (tokenizer + transformer architecture, ~40h).
- **Skip distributed systems / Kubernetes / Spark.** You are one person with a single-machine workload. Returns are near zero for 12 months.
- **Skip framework loyalty.** LangChain/LangGraph/CrewAI/AutoGen ship breaking changes regularly. Invest in the durable layer: evals, prompt design, RAG architecture, system design.

### Tier 1 — CRITICAL (weeks 1–14)

#### 1.1 RAG architecture & retrieval for financial documents (4 weeks → operational)

**Why it matters:** This is the single highest-leverage skill for FearNot. The corpus is your XBRL/GAAP mapping + 10-K/10-Q/8-K/earnings transcripts. Snowflake's engineering team (May 2025, *"Long-Context Isn't All You Need"*) showed that on 10-Ks, "markdown-aware chunking … tends to outperform naïve fixed-size splits as well as semantic chunking by 5–10 percentage points," and document-level metadata prepended to every chunk closes most of the residual gap. Anthropic's official **Contextual Retrieval** post (anthropic.com/news/contextual-retrieval, Sep 19 2024) reports: "Contextual Embeddings reduced the top-20-chunk retrieval failure rate by 35% (5.7% → 3.7%)"; adding Contextual BM25 reaches **49%**, and adding reranking reaches **67% (5.7% → 1.9%)**. A 2026 medium write-up by "steven b" on financial RAG documents an empirical leap from **52.6% to 87.7% recall** by making chunking table-aware. Hedge fund and AI-lab interviewers will ask about your chunking strategy specifically.

**Expected skill level at end:** Operational — architect, instrument, and debug a production-grade RAG pipeline over SEC filings, with informed embedding-model selection, hybrid retrieval, and rerankers. **Not** deep on vector-index internals (HNSW math).

**Resources (verified):**
- Read in order: Snowflake "Long-Context Isn't All You Need: How Retrieval & Chunking Impact Finance RAG" (snowflake.com/en/engineering-blog/impact-retrieval-chunking-finance-rag/).
- Anthropic Contextual Retrieval (Sep 19, 2024) for chunk-level context prepending.
- The `anthropics/claude-cookbooks` repo (~43k stars on GitHub) — specifically the `skills/` and `patterns/agents/` directories, including `creating-financial-models`.
- For evaluation: the **FinanceBench** benchmark (Patronus AI) and Vals AI's Finance Agent benchmark — per Anthropic's "Agents for financial services" (May 2026), Claude Opus 4.7 leads Vals AI **Finance Agent v1.1 at 64.37%**; note Vals AI's **Finance Agent v2** (released 2026) shows scores ~14 points lower across all models (GPT 5.5 at 51.76%, Claude Opus 4.7 at 51.51%). Replicate one of these.

**Concrete first project (weeks 3–4):** Take 5 years of 10-K/10-Q for 10 S&P 500 companies; build (a) layout-aware chunking that preserves tables, (b) metadata enrichment (ticker, year, section), (c) hybrid retrieval (BM25 + dense), (d) a reranker. Target ≥85% recall@10 on a 50-question QA test set you author. Defaults: chunk size ~750 tokens with 100-token overlap (markdown-aware); embeddings `text-embedding-3-large` (3072d) or open-source `bge-large-en-v1.5` for zero API cost. **This is a public GitHub repo. This is the artifact you show in interviews.**

**Connection to FearNot:** This is FearNot's information layer. **Follow-up #1: dedicated deep-dive on financial RAG.**

#### 1.2 LLM evaluations and prompt observability (2 weeks → operational)

**Why:** Without evals you cannot improve; without observability you cannot debug. Every credible AI-engineering interviewer will ask "how do you know your system works?" Your answer must name a golden dataset, an LLM-as-judge with a calibrated rubric, and a CI regression test.

**Resources (verified):**
- **Hamel Husain, "What We've Learned From A Year of Building with LLMs"** (hamel.dev / O'Reilly).
- **OpenAI Evals** repo (github.com/openai/evals) for spec patterns.
- **Anthropic, "Building Effective Agents"** (Erik Schluntz & Barry Zhang, Dec 2024) + the `claude-cookbooks/patterns/agents` reference implementations.
- **Langfuse** (MIT-licensed, free self-hosted, broadest framework support) — your default for FearNot. Per ClickHouse's blog (clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability), the acquisition was announced **January 16, 2026**, alongside a $400M Series D at a $15B valuation led by Dragoneer Investment Group; the OSS code remains actively maintained.

**Operational target:** Reusable harness with (a) golden Q&A set tied to your XBRL/GAAP mapping, (b) LLM-as-judge rubric, (c) Langfuse traces on every FearNot agent run, (d) CI script that fails if accuracy on golden set drops >2pp.

#### 1.3 Multi-agent orchestration (3 weeks → operational)

**Why:** FearNot is by construction a multi-agent system. The 2025–2026 market has consolidated: **LangGraph** for production stateful workflows, **CrewAI** for fast role-based prototypes, **Pydantic AI** for type safety, **DSPy** when you have labeled data and want auto-optimized prompts. **AutoGen has effectively died in production** — the DEV community 2026 review states it has "near-zero security mechanisms, suitable for academic research and rapid experimentation, not for enterprise production"; Microsoft itself rewrote it under the new Agent Frameworks team.

**Decision for FearNot:** Start with **raw Anthropic SDK + Pydantic** for type-safe message schemas. Graduate to **LangGraph** only when you hit explicit needs for checkpointing, human-in-the-loop, or long-running stateful workflows. Avoid **CrewAI** for a global-macro system — role-based prompts inflate token count ~30–50% vs hand-tuned LangGraph (per the PE Collective 2026 comparison), and global macro is graph-shaped (data → factors → cross-asset views), not role-shaped.

**Honest take on DSPy:** **Not hype.** The official site (dspy.ai/community/use-cases) lists production deployments at Shopify, Databricks, Dropbox, JetBlue, Moody's, Replit, AWS, Sephora, VMware. Read the docs + RAG tutorial in one weekend; use the **GEPA** optimizer once you have eval data. But don't make DSPy your first agent — ship raw SDK first.

**Resources:** Anthropic cookbook `patterns/agents`; LangGraph docs (langchain-ai.github.io/langgraph); DSPy docs (`stanfordnlp/dspy` GitHub examples/); Victor Dibia's `autogen-vs-crewai-vs-langgraph` newsletter for decision frames.

#### 1.4 López de Prado: Financial ML done right (4 weeks → operational on key chapters)

**Why:** *Advances in Financial Machine Learning* (Wiley 2018, Marcos López de Prado, then Head of ML at AQR Capital, currently Cornell ORIE 5256 instructor) is the canon your future quant interviewers cite. Skip what you don't need. Critical chapters: **2 (financial data structures), 3 (labeling, triple-barrier), 4 (sample weights), 5 (fractional differentiation), 7 (cross-validation in finance), 13–14 (backtest overfitting, deflated Sharpe).**

**Resources:**
- The book itself. Pair with **skfolio** (skfolio.org, MIT license) — clean `CombinatorialPurgedCV` implementation directly usable. Avoid mlfinlab (Hudson & Thames went paid mid-2020).
- SSRN: López de Prado *"Advances in Financial Machine Learning (Chapter 1)"* (ssrn.com/abstract=3104847) — free, read before buying the book.
- Cornell ORIE 5256 lecture materials at quantresearch.org/Lectures.htm — publicly accessible.

**Project deliverable:** Build a CPCV harness in skfolio. Run a deliberately overfit MA-crossover and **demonstrate that CPCV correctly flags it as overfit while naïve k-fold rates it as profitable.** This is a portfolio piece.

### Tier 2 — HIGH (weeks 15–24)

#### 2.1 Classical ML for tabular finance (3 weeks → operational)

XGBoost, LightGBM, regularization, time-series CV. One-stop: **Stanford CS229 (Andrew Ng, Fall 2024 offering, ~80h lectures on YouTube + Stanford Online)**. Do **psets 2 (logistic regression, GLMs) and 4 (EM, factor analysis)** — the high-ROI psets for finance. Skip CS229's deep-learning units.

**Better focused alternative:** **fast.ai "Practical Deep Learning for Coders" Part 1** (Jeremy Howard) — lessons 5–6 on tabular/structured data, faster to operational. Pair with scikit-learn's User Guide on cross-validation, pipelines, feature selection.

#### 2.2 Time-series, factor models & backtesting (3 weeks → operational)

**Backtesting decision for FearNot / Asymmetric Global Macro Fund (multi-asset):**
- **vectorbt** for vectorized strategy research (Numba-JIT, millions of trades/sec). The right tool for parameter sweeps and cross-asset factor research.
- **nautilus_trader** only when you go to live execution and need event-driven simulation matching production semantics. Overkill until you have edge to deploy.
- **Skip Zipline-reloaded** (mostly equity, Quantopian legacy, dependency hell).
- **Skip Backtrader** (slower, smaller community, fine for discretionary swing but not your profile).

**Resources:**
- **López de Prado, *Machine Learning for Asset Managers*** (Cambridge 2020) — short, dense; chapter on the false strategy theorem and HRP is essential.
- **AQR (Asness/Moskowitz/Pedersen) papers on SSRN** — read 3–4 originals on momentum, value, low-vol. Ground truth for factor construction.
- **Andrew Patton (Duke), Coursera "Financial Engineering and Risk Management"** — solid GARCH and copula content.
- Avoid YouTube/Medium quant tutorials — most are statistically incompetent. Stay academic + López de Prado.

#### 2.3 Stats & linear algebra refreshers, quant-focused (2 weeks → operational)

Targeted exercises, not a full course:
- **Gilbert Strang, *Introduction to Linear Algebra* (5th ed)** — chapters 4 (orthogonality), 6 (eigenvalues), 7 (SVD), 9 (linear transformations). SVD + eigendecomposition underlie PCA, factor models, and embeddings.
- **Joe Blitzstein, Harvard Stat 110** (YouTube + book *Introduction to Probability*) — best free probability course. Cover discrete RVs, Markov chains (lectures 12–16), inequalities. Quant brain-teasers come from chapters 1–7.
- **Max Dama, *Quantitative Primer*** (free PDF, HFT-prep classic).

### Tier 3 — NICE-TO-HAVE

- **Light fine-tuning / LoRA exposure (1 week, exposure only):** One weekend on the HuggingFace PEFT tutorial + `unsloth` to LoRA-tune a 7B on a small financial QA set. Vocabulary, not depth.
- **MLOps basics:** You have Vercel + Next.js + SQLite. Add **Modal Labs** (modal.com — serverless GPU inference) and **GitHub Actions** for CI/eval gates. That's all you need. Skip Kubernetes/Airflow/MLflow.

### SKIP-FOR-NOW

Deep RL for trading; CS336 full sequence; C++/HFT systems (you're macro, not HFT); local LLM hosting at scale; computer vision; building NLP from scratch.

### Realistic month-by-month sequence (14 h/week)

- **Month 1 (wks 1–4) — RAG for financial documents:** Snowflake post + Anthropic Contextual Retrieval + Sarthak chunking guide; build layout-aware chunking + metadata + hybrid retrieval over 10 S&P 500 10-Ks; ship public GitHub repo with 50-question eval.
- **Month 2 (wks 5–8) — LdP essentials + evals harness:** chapters 2–4, 7, 13–14 of *AFML*; ship skfolio CPCV demo; integrate Langfuse end-to-end in FearNot.
- **Month 3 (wks 9–12) — Multi-agent orchestration in FearNot:** refactor to clean tool-use boundaries, type-safe Pydantic message contracts, optional LangGraph migration if state requires it; ship a public Anthropic-cookbook-style README.
- **Month 4 (wks 13–16) — Classical ML + factor models:** CS229 psets 2, 4; build XGBoost + Lasso cross-asset factor baseline on yfinance/Polygon; blog post comparing factor model vs LLM-derived signals.
- **Month 5 (wks 17–20) — Backtesting + stats:** vectorbt walk-forward on macro strategies (DXY momentum, EM carry, vol breakouts); Stat 110 lectures 1–16 + Strang chapters 6–7; deflated Sharpe writeup of a real strategy.
- **Month 6 (wks 21–24) — Synthesis project:** combine RAG + factor model + multi-agent orchestration into a single FearNot release with public technical blog, signed-off evals, and a recorded video walkthrough. **This is the artifact you cold-email recruiters with.**

**Follow-up research flags from PART 1:**
1. Dedicated RAG architecture deep-dive for FearNot (chunking, embeddings, hybrid search, reranking) — **HIGHEST PRIORITY.**
2. CPCV implementation patterns for global macro (multi-asset, regime-aware purging) — MEDIUM.
3. Anthropic Skills + Claude Code Plugins specifically for finance (the `anthropics/financial-services` repo has 10 production agent templates overlapping with FearNot) — MEDIUM.
4. DSPy + GEPA for FearNot once eval data exists — LOW-MEDIUM.

---

## PART 2 — PERSONAL TOOLS AND STACK

### A. Second Brain / Knowledge Management

**Honest assessment:** "Second brain" is 80% productivity trap, 20% genuinely valuable for your profile. Trap: tinkering with Obsidian instead of building. Value: structured notes for earnings calls / 10-Ks / Druckenmiller interviews, dated thesis evolution, calibrated personal trade lessons. **Cap setup at 4 hours total.**

**Recommendation: Obsidian + local-first vault + Claude Code integration.**

Why over alternatives:
- **vs Notion:** good for shared docs, terrible for long-form linked text + offline access.
- **vs Logseq:** outliner-first, weaker for long-form.
- **vs Reflect / Tana:** Tana has best native AI but $14/mo + your data on their servers — wrong for proprietary investment research.
- **Obsidian:** plain markdown on disk; works natively with Claude Code/git/scripts.

**Plugins (minimal):**
- `Dataview` — query notes as a database.
- `Templater` — repeatable note templates.
- `Smart Connections` — local embeddings (`nomic-embed-text-v1.5`); notes never leave your machine.
- `Excalidraw` — only if you draw diagrams.
- **Skip:** calendar/tasks plugins (use real apps), most "AI" plugins that ship to OpenAI.

**Vault structure for cross-domain:**
```
vault/
├── 00-inbox/
├── 01-companies/    # MOC per company
├── 02-macro/        # macro themes, frameworks
├── 03-trades/       # one note per trade
├── 04-theses/       # investment theses, dated
├── 05-readings/     # book/paper notes
├── 06-fearnot/      # design docs, decisions
├── 07-learning/     # course notes
├── 08-people/       # contacts, post-meeting notes
└── _templates/
```
Use **MOCs (Maps of Content)** over folders for cross-cutting topics (e.g., "Druckenmiller principles" MOC).

**Claude API integration over the vault:**
- Start with Karpathy's "LLM wiki" pattern: Claude Code reads your markdown files directly with a `CLAUDE.md` at the vault root defining structure + style. Works for ≤2000 notes.
- Outgrowing that: DuckDB + vector extension approach (motherduck.com/blog/obsidian-rag-duckdb-motherduck/) with `bge-m3` (multilingual — handles your Spanish + English).

### B. Personal Productivity

Your time is dominated by UTDT classes, FearNot dev, portfolio decisions, and internship application sprints. You need calendar + tasks + reading queue — not a Notion mega-system.

**Minimum viable stack:**
1. **Google Calendar** with **time-blocking discipline** (Cal Newport-style). Block 2 daily learning hours; treat like a class.
2. **Tasks: Things 3** ($50 one-time) or **TickTick** ($28/yr). GTD-light. Skip Todoist if price-conscious.
3. **Readwise Reader** ($7/mo student tier exists) — articles, PDFs, Twitter, RSS, YouTube transcripts. Daily Review surfaces old highlights. Syncs to Obsidian via official plugin.
4. **Gmail** with canned responses + filters. Don't over-engineer.

**Anti-recommendations:** Skip Sunsama, Motion, Reclaim, Roam, Mem, Heptabase — wrong stage.

**Time-blocking template (14 h/week):**
- Mon/Wed/Fri: 2h focused tech learning (mornings before UTDT)
- Tue/Thu: 2h FearNot dev
- Sat: 3h deep block (shipping or thesis writing)
- Sun: 1h review (consolidation, week-ahead planning)

### C. Dev Tools

**IDE setup:**
- **Cursor (editor) + Claude Code (terminal panel)** is the dominant 2026 pattern (Anthropic reported Claude Code revenue at $2.5B+ annualized by early 2026). Cursor's June 2025 credit-billing has produced surprise overages (some reports of $1,400+ single-cycle bills) — **set hard spend caps day one.**
- **Budget-constrained path:** **Claude Code Max ($100/mo)** alone with VS Code as editor. The IDE wrapper isn't worth Cursor's extra cost for your workload.
- **VS Code essentials:** Python, Pylance, Ruff (replaces black + isort + flake8), Jupyter, GitLens, Error Lens.

**Agentic framework for FearNot:**
- **Default: raw Anthropic SDK + Pydantic** for tool schemas (per `claude-cookbooks/patterns/agents`).
- **Graduate to LangGraph** when you need checkpointing, human-in-the-loop, or explicit state graphs.
- **Use DSPy** for one specific subsystem (e.g., financial QA) once you have labeled data.
- **Skip CrewAI** — wrong abstraction for graph-shaped problems.
- **Skip AutoGen** — effectively dead in production.
- **Pydantic AI** — fine alternative to raw SDK for type safety without LangGraph complexity.

**Local LLMs (Ollama, LM Studio, llama.cpp) — honest answer: NO for your case.** (1) Your laptop can't run a model competitive with Claude Sonnet/Haiku on financial reasoning (Claude Opus 4.7 at 64.37% on Vals AI Finance Agent v1.1 vs Llama 70B locally ~30%). (2) Anthropic Sonnet/Haiku is trivially priced at your usage (~$50–100/mo covers heavy dev). (3) Local setup is a time sink. Only revisit for a one-weekend `unsloth` + LoRA exercise for résumé vocabulary.

**Eval / observability — final pick:**
- **Langfuse (self-hosted, MIT)** — default. Free, framework-agnostic, Docker-deployable. ClickHouse acquired it Jan 16, 2026 (Series D, $400M, $15B valuation, led by Dragoneer); OSS unchanged.
- **Braintrust** for CI eval gating only if Langfuse's eval UI isn't enough. Free tier: 1M spans/mo + 10K evals — generous enough for a personal project.
- **Skip:** LangSmith (LangChain lock-in, $39/seat + per-trace), W&B Weave (built for ML training, not LLM apps), Helicone (proxy-only, no evals).

**Vector database for FearNot:**
- **pgvector on Supabase or Postgres** — production default. You already use SQLite locally; pgvector means one DB, mixed SQL + vector filters (essential for ticker/year/section filtering on 10-K chunks). Per Timescale's May 2025 benchmark, pgvectorscale hits 471 QPS at 99% recall on 50M vectors — 11.4× Qdrant at same recall.
- **Qdrant** — when you outgrow pgvector or need best-in-class payload filtering. Rust, self-hostable. Used by Discord, Perplexity, Mozilla, Bosch.
- **Chroma** — fastest prototype (`pip install chromadb`). 2025 Rust rewrite delivers 4× perf gains.
- **Skip Pinecone** — managed, expensive, vendor lock-in at your scale.
- **Skip Weaviate/Milvus** — operational overhead exceeds value at your scale.

**Decision: pgvector for production FearNot, Chroma for prototypes.**

### D. Trading / Research-Specific

**Backtesting (verified):**
- **vectorbt** — global macro, multi-asset, parameter sweeps. vectorbtpro is $1000+ — skip until deployed.
- **nautilus_trader** — when you go live (event-driven, production-grade, Rust core).
- **QuantConnect/LEAN** — C#-first; only if you want hosted infrastructure + broker integrations.

**Data sources beyond yfinance/FRED:**
- **Polygon.io** — best retail-tier US equity + options; $29/mo Starter, $79/mo Developer. **Recommended primary** for FearNot.
- **Tiingo** — fundamentals + EOD + news; $10/mo. Good complement.
- **Alpaca** — broker API, free historical data; useful if you go live on US equities.
- **Stooq** — free EOD globally; some gaps.
- **Norgate** — survivorship-bias-free historical; ~$50/mo; worth it once you do serious backtesting.
- **IBKR API (TWS)** with `ib_insync` — only retail-accessible broker for genuine global multi-asset (FX, futures, EU equities). Open an account.
- **Macro:** FRED (you have), World Bank API (free), BIS (free CSV), IMF SDMX (free, awkward), OECD SDMX. LATAM: **CEPAL/ECLAC**, **BCRA** (Argentine central bank).
- **TradingEconomics API** (~$80/mo) — only if you need consolidated real-time global indicators.
- **Skip:** Refinitiv Eikon, Bloomberg (institutional, unobtainable); Quandl/Nasdaq Data Link (degraded post-acquisition).

**Bloomberg alternatives — honest:**
- **Koyfin Plus or Pro ($39–$79/mo)** — highest-ROI retail terminal. Per the **Kitces 2025 AdvisorTech Study**, financial advisors rated Koyfin **9/10 for satisfaction and value**, ranking it the highest-rated platform in the Investment Research & Analytics category ahead of YCharts, Kwanti, FactSet, Morningstar, and Bloomberg Terminal. **Recommended pay.**
- **Fiscal.ai (formerly FinChat) Plus ($29/mo)** — AI-powered fundamental research, strong KPI/segment data. Worth it for FearNot prototyping as a sanity-check baseline.
- **TradingView Pro ($14/mo)** — charting and macro overlays.
- **TIKR Plus ($19.95/mo)** — global screener (100k+ stocks across 92 countries, 136 exchanges) if Koyfin is too pricey.
- **Skip:** Atom Finance, gurufocus, Roic.ai — not differentiated.
- **stockanalysis.com** — free, surprisingly good for basic fundamentals.

**Decision for a $30k portfolio:** Pay for **Koyfin Plus + TradingView Pro** (~$53/mo total). Add Fiscal.ai if LLM-derived KPI extraction is part of FearNot's value. Everything else is hobby spending masquerading as edge.

**Trading journal:**
- Skip Edgewonk, TradesViz, Tradervue — built for high-frequency day traders.
- **Custom Obsidian template:** one note per trade with date, instrument, thesis, sizing rationale, conviction (1–5), pre-mortem ("what invalidates this?"), post-mortem at exit. Macro tags (`#carry`, `#vol-rally`, `#DM-vs-EM`). Dataview month-end aggregates win rate, holding period, conviction calibration. The value is **calibration of your conviction over time**, not P&L (your broker tracks that).

**Follow-up research flags from PART 2:**
5. Polygon vs Tiingo vs Norgate quality + survivorship bias comparison — MEDIUM (do before any paid data subscription).
6. pgvector + Postgres production architecture for FearNot v2 — MEDIUM (do when scaling past 100k vectors).

---

## PART 3 — SIGNAL FOR EMPLOYERS / PORTFOLIO PROJECTS

### What your CV must demonstrate

For 2026–2027 internship recruiting:
1. **Real product shipped** — FearNot, public, with eval scores and a serious technical README.
2. **Olympiad-substitute credential** — Kaggle Silver+, published Substack/paper, or a non-trivial merged OSS PR.
3. **Verifiable technical depth beyond LLM API calls** — a CPCV implementation, a factor-model writeup, or a public eval harness.
4. **Macro/finance domain depth** — a Substack with ≥10 long-form pieces.

US NYC-only quant shops (Jane Street, Two Sigma, Citadel, HRT, Optiver Chicago, IMC, DRW) will screen you out at résumé stage from UTDT alone. The **Italian passport + EU offices is the practical path.**

### Personal projects worth building

**Tier 1 (ship these):**
1. **FearNot itself** — ship it publicly with a README that reads like an Anthropic engineering post.
2. **CPCV demonstration repo** — small, sharp. Reference LdP *AFML* ch. 7. Show overfit MA-crossover passes naïve k-fold but fails CPCV. Reproducible notebook.
3. **Financial RAG benchmark replication** — replicate FinanceBench or Vals AI Finance Agent (v1.1 or v2) with your pipeline. Substack post: "I got to X% on FinanceBench with $0 in infra cost."
4. **One macro thesis per quarter on Substack, in English** — Druckenmiller-style: thesis, asymmetry, falsifiers, position sizing.

**Tier 2 (only if Tier 1 ships):**
5. Kaggle competition with public notebook + medal attempt.
6. Toy reproduction of Asness/Moskowitz/Pedersen 2013 *"Value and Momentum Everywhere"* on your own data.

**Anti-projects:** personal robo-advisor (not differentiated); crypto trading bot (instant disqualifier at serious shops); LangChain demo with no eval; "ChatGPT for X" wrapper without RAG/evals/proprietary data.

### Papers worth replicating (verified accessible)

- López de Prado et al., *"The Probability of Backtest Overfitting"* (J. Computational Finance 2017, SSRN). Deflated Sharpe.
- López de Prado, *"Building Diversified Portfolios that Outperform Out-of-Sample"* (JPM 2016, SSRN) — HRP.
- Asness/Moskowitz/Pedersen, *"Value and Momentum Everywhere"* (JF 2013).
- HRT Beat blog, *"In Trading, Machine Learning Benchmarks Don't Track What You Care About"* — cite in interviews.
- Anthropic, *"Building Effective Agents"* (Schluntz/Zhang) — replicate one pattern.
- Snowflake + Stanford, *"Long-Context Isn't All You Need"* — replicate one experiment.

Skip: Renaissance/Medallion HFT papers (microstructure data inaccessible); Bridgewater *Principles* (not technical); Two Sigma research blog (mostly PR).

### Open-source contributions — strategic targets (priority order)

1. **anthropics/claude-cookbooks** (~43k stars) — finance directory. Submit a notebook on financial RAG with your eval harness. **Highest strategic value — puts you in Anthropic's GitHub network.**
2. **anthropics/financial-services** (~25k stars) — submit a sector or sub-agent skill template. Direct visibility to Anthropic's finance team.
3. **stanfordnlp/dspy** — production at Shopify, Databricks, AWS, Moody's. Merged PR signals genuine ML engineering.
4. **pola-rs/polars** — Polars is replacing pandas at quant shops; even a small PR has signal.
5. **skfolio** — smaller, financial, less competition.
6. **vectorbt** — small team, possibly higher chance of meaningful contribution.
7. **scikit-learn** — high prestige but crowded; first-issue-label PRs still doable.
8. **nautilus-trader/nautilus_trader** — for live execution; less ML-research signal.

Skip: huggingface/transformers (too crowded; your PR will be a typo fix); langchain (moving target, low signal); openai-cookbook (lower signal than anthropic-cookbook for your profile).

### Standing out as a LATAM student — the playbook

Reality check: documented LATAM-to-US-quant first-person success stories are scarce in public records. The pipeline is real but unindexed. Your moves:

**1. Build in public, in English: Substack + GitHub + Twitter/X.**
- Substack: long-form macro theses + technical writeups. Target weekly cadence, monthly minimum.
- GitHub: every project public; README quality is half the signal.
- Twitter/X: share project updates; engage with quant + AI-engineering corners (@QCResearcher, @MacroAlf, @hamelhusain, @swyx). Build-in-public is **not hype** for your profile — without it, recruiters who Google you find nothing. 6–12 month slow burn expected before inbound.

**2. EU offices first, US second.**
- **Jane Street London & Amsterdam — First Year Trading and Technology Program (FTTP)** — per janestreet.com/join-jane-street/programs-and-events/fttp/: explicitly **does NOT require US work authorization.** Opens ~Sep 2026 for Summer 2027.
- **Optiver Amsterdam** internships — open to EU citizens.
- **IMC Amsterdam** — same.
- **Citadel London** — UK office accepts EU work rights.
- **HRT London** — same.
- **Susquehanna Dublin** — newer office, less competition.

Your Italian passport materially changes the odds. Put EU work rights at the top of your CV.

**3. Cold outreach playbook.**
- Identify the specific researcher/PM whose published work overlaps with what you've built.
- 5-sentence email: (1) credentialing sentence ("UTDT economics student building FearNot, a multi-agent financial research system"), (2) what you did that's relevant to them ("I replicated your CPCV approach on macro data and found X"), (3) link to artifact, (4) one specific 2-minute question, (5) "no need to reply if too busy."
- **Do NOT ask for a job.** Ask for technical feedback. Jobs come from second touches.
- LinkedIn DMs to recruiters do occasionally lead to phone screens (corroborated by Blind/WSO posts), but researcher cold emails have higher hit rates at lower volume.
- Cadence: 5 well-targeted cold emails per week ≫ 50 generic ones.

**4. LATAM-specific signal channels:**
- **MercadoLibre tech roles** — MELI's Fury platform is real Java/microservices; an MELI internship is recognized at US tech firms (less so quant, but useful for AI-lab pivot).
- **OpenAI Residency** — 6-month paid program, in-person SF, visa-sponsored, explicit about welcoming international quantitative/scientific candidates. Per openai.com/residency and corroborating job listings, base salary is **$18,300/month ($219,600 annualized)**. **Apply when you finish UTDT, not before** (residency targets recent grads).
- **Allen AI (Ai2) internships** — open to international undergrads with visa sponsorship per allenai.org/internships: *"International candidates are welcome to apply. Pay is competitive, and visa sponsorship is available."*
- **Anthropic** — official careers FAQ: *"We don't currently offer internships."* Full-time only, with visa sponsorship. Plan for full-time post-graduation.
- **Fulbright Argentina + EducationUSA Buenos Aires** — financing path if you pursue a US master's. "Friends of Fulbright" runs 5–7 week US programs for 3rd/4th-year Argentine students.
- **No verified evidence** of Jane Street, Optiver, HRT, IMC running Buenos Aires or São Paulo undergrad recruiting events 2024–2025. Optiver's São Paulo presence is **data-center engineering only**, not a recruiting trading desk.

### Communities worth joining

- **QuantConnect Discord** — active, technical, real practitioner discussions on LEAN.
- **Wilmott forums** — mature, theory-heavy; lurk for a quarter before posting.
- **r/quant** — uneven but real recruiter activity.
- **Anthropic Discord** (via developer signup) — for AI-engineering side.
- **Latent Space Discord** (Swyx) — AI-engineering practitioners.
- **DSPy Discord** — small, technical, maintainers present.
- **Argentina-local:** Buenos Aires Python meetup; MachineLearningAr (Telegram); Aprendizaje Profundo BA. Small but useful for connecting with Argentines who've made the jump abroad.

**Skip:** Telegram crypto-quant groups (S/N ~0); generic ML/finance subreddits; AI Twitter spaces without specific topics.

### Follow-up research flags from PART 3

7. **Manual UTDT LinkedIn alumni scan** at Jane Street/Citadel/Two Sigma/HRT/Optiver/IMC/DRW/Bridgewater (cannot be done via search engines, but is the highest-leverage hour you can spend on networking) — **HIGH PRIORITY.**

---

## Consolidated follow-up research priorities (priority order)

1. **[HIGHEST] Financial RAG architecture for FearNot** — chunking strategies for SEC filings, embedding-model comparison (`text-embedding-3-large` vs `bge-large-en-v1.5` vs `voyage-3-large`), hybrid search tuning, reranker selection (Cohere Rerank 3 vs BGE-reranker), eval harness construction.
2. **[HIGH] Manual UTDT LinkedIn alumni scan** at top US/EU quant + AI labs to map the real (private) network you can target with warm intros.
3. **[MEDIUM-HIGH] CPCV + deflated Sharpe implementation** for multi-asset global macro — regime-aware purging, embargo sizing for cross-asset signals.
4. **[MEDIUM] Anthropic Claude Skills + Plugins for finance** — map the 10 templates in `anthropics/financial-services` to FearNot, identify fork/contribute/replicate targets.
5. **[MEDIUM] DSPy + GEPA optimizer for FearNot's financial QA subsystem** — only after labeled eval data exists.
6. **[MEDIUM] Polygon vs Tiingo vs Norgate quality + survivorship comparison** — before paid subscription.
7. **[LOW-MEDIUM] EU quant internship cycle calendar** — exact application windows for Jane Street London FTTP, Optiver Amsterdam, IMC Amsterdam, Citadel London, HRT London for Summer 2027 (typically open Aug–Oct of prior year — missing the window kills the cycle).

---

## Closing — honest mentor tone

The thing that will move your career most in the next 12 months is not picking the right vector database or the perfect agent framework — it is **shipping FearNot publicly with serious evals, writing about it clearly in English on Substack, and applying to the EU offices of the major quant firms on the strength of your Italian passport.** Everything above serves that. The biggest risk is spending 6 months tooling and 0 months shipping. Set a hard rule: **every Sunday, something new is public** — a commit, a blog post, an eval result, a thesis. Without external artifacts visible to recruiters, none of this study time converts into interviews. The window for Summer 2027 EU quant internship applications opens roughly **August–October 2026** — earlier than most students realize. Plan backwards from there.
