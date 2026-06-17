# Loopa Intelligence Platform

Version: 1.0
Owner: Value Aligners
Developer: Harika Chowdary Pedavalli
Last Updated: May 2026

---

## 1. What This Tool Does

The Loopa Intelligence Platform is an automated market intelligence system that researches cybersecurity niche markets, scores them using a two-layer weighted model, matches vendors to pain points, and delivers a ranked sales report every Monday morning with zero manual work.

It answers three questions for the sales team:

- Which industries need cybersecurity the most right now?
- What are their biggest threats?
- Which vendors in our marketplace solve those problems?

---

## 2. How It Works

The platform runs in five stages:

**Stage 1 - Research**
The AI research agent studies each niche market and collects all scoring variables including attack history, market growth, regulatory pressure, and outreach feasibility.

**Stage 2 - Scoring**
Each niche market gets two scores:

Demand Score measures how urgently an industry needs cybersecurity based on attack records, digitalization level, market size, CAGR, and regulatory pressure.

Outbound Score measures how reachable that industry is for cold outreach based on buyer clarity, procurement friction, reachability, and offer fit.

Final Priority Score = Demand Score x Outbound Score / 100

**Stage 3 - Tier Assignment**
- Tier 1: Score 70 and above - top outbound targets
- Tier 2: Score 50 to 69 - secondary targets
- Tier 3: Score below 50 - monitor and revisit

**Stage 4 - Vendor Matching**
The keyword matching engine maps 3,431 vendors from the marketplace to each pain point using category overlap, threat type matching, and customer ratings.

**Stage 5 - Report Generation**
A full ranked sales report is generated showing every niche market, its scores, pain points, and top 3 recommended vendors per pain point.

---

## 3. Project Structure

loopa_intelligence/

agents/

niche_market_agent.py    research and scoring per niche
batch_processor.py       processes all niche markets
vendor_importer.py       imports vendor Excel files
vendor_matcher.py        keyword matching vendors to pain points


database/

schema.py                4 table definitions using SQLAlchemy ORM
db_manager.py            all database read and write operations


utils/

report_generator.py      final sales intelligence report


data/                      reports, Excel files, JSON outputs
scheduler.py               weekly auto-scheduler
config.py                  environment configuration
.env                       API keys and database credentials

---

## 4. Database Schema

**niche_markets**
Stores all niche markets with full scoring variables, ICP details, demand score, outbound score, priority score, and tier.

**pain_points**
Stores top 3 to 5 cyber threats per niche market with severity scores and growth rates.

**vendors**
Stores 3,431 vendors imported from Value Aligners marketplace Excel files.

**vendor_pain_point_map**
Maps vendors to pain points with match scores and reasoning.

---

## 5. Scoring Model

### Demand Score Weights

| Variable | Weight |
|---|---|
| Attack Records | +0.25 |
| Digitalization Level | +0.20 |
| SMB Revenue Contribution | +0.15 |
| CAGR | +0.15 |
| Cybersecurity Readiness | -0.20 |
| Industry Size | +0.10 |
| SMB Percentage | +0.10 |
| Estimated Annual Loss | +0.10 |

### Outbound Score Weights

| Variable | Weight |
|---|---|
| Reachability | +0.35 |
| Buyer Role Clarity | +0.20 |
| Procurement Friction | -0.25 |
| Time to Value | +0.10 |
| Vendor Sprawl | +0.05 |
| Offer Fit | +0.05 |

### Final Formula

Priority Score = Demand Score x Outbound Score / 100

---

## 6. Required Environment Variables

Create a `.env` file in the root directory. Never commit this file to GitHub.

GROQ_API_KEY=your_groq_api_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
AZURE_SQL_SERVER=your_server.database.windows.net
AZURE_SQL_DATABASE=your_database_name
AZURE_SQL_USERNAME=your_username
AZURE_SQL_PASSWORD=your_password
ENVIRONMENT=development

**What works without each key:**

- No GROQ_API_KEY: AI research agent disabled, use manual data entry
- No AZURE credentials: System runs on local SQLite automatically

---

## 7. How to Run Locally

git clone https://github.com/HarikaPedavalli-ValueAligners/loopa-intelligence-platform.git
cd loopa-intelligence-platform
pip install -r requirements.txt

Add your `.env` file with at minimum your GROQ_API_KEY.

**Run in order:**

python database/schema.py
python agents/vendor_importer.py
python agents/batch_processor.py
python agents/vendor_matcher.py
python utils/report_generator.py

**Start weekly auto-scheduler:**

python scheduler.py

**Manual one-time run:**

python scheduler.py --run-now

---

## 8. Current Results

| Metric | Value |
|---|---|
| Niche Markets Ready | 1,012 |
| Test Markets Processed | 20 |
| Pain Points Identified | 60 |
| Vendors Imported | 3,431 |
| Vendor Matches Saved | 180 |
| Vendor Match Success Rate | 100% |
| Weekly Scheduler | Working |

---

## 9. Deployment

### Local (Current)
Running on SQLite. All functionality working.

### Production (Pending)
Switch to Azure SQL with one line change in `database/db_manager.py`:

Current:

engine = create_engine("sqlite:///loopa_intelligence.db")

Replace with:

engine = create_engine(
f"mssql+pyodbc://{username}:{password}@{server}/{database}"
"?driver=ODBC+Driver+17+for+SQL+Server"
)

### Full Deployment Steps
1. Add Azure credentials to .env
2. Update get_engine() in db_manager.py
3. Run: python database/schema.py
4. Run: python scheduler.py --run-now
5. Run: python agents/vendor_importer.py
6. Run: python agents/vendor_matcher.py
7. Run: python utils/report_generator.py
8. Start: python scheduler.py

---

## 10. Pending Items

| Item | Status | Blocked On |
|---|---|---|
| Azure SQL deployment | Pending | Azure credentials from Hamid |
| AI API key switch | Pending | Anthropic or OpenAI key from Hamid |
| Scale to 1,012 markets | Ready to run | Azure SQL + API key |
| Expand to 5-layer hierarchy | In design | Hamid to define variables |

---

## 11. Known Limitations

- SQLite used locally. Switch to Azure SQL for production.
- Groq free tier has rate limits for large batch runs. Use paid API key for 1,012 markets.
- Vendor matching uses keyword overlap. AI-based matching available once API key is provided.
- Report saved as JSON locally. Dashboard integration planned for Phase 2.

---

## 12. Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.14 |
| AI API | Groq LLaMA 3.3 70B |
| Database (Local) | SQLite |
| Database (Production) | Azure SQL |
| ORM | SQLAlchemy |
| Data Processing | Pandas |
| Scheduler | Python schedule library |
| Version Control | GitHub |

---

## 13. GitHub

https://github.com/HarikaPedavalli-ValueAligners/loopa-intelligence-platform

---

## 14. SaaS Wrapper (Multi-Tenant API)

The `saas/` package wraps this platform as a sellable, multi-tenant SaaS. It is
fully additive: the existing scripts and weekly pipeline behave exactly as
before. The entire SaaS surface is gated behind a feature flag and is OFF by
default.

### Feature flag

The wrapper does nothing unless `LOOPA_SAAS_ENABLED=true`. With the flag off,
`saas.app:app` is a 404-only app and the legacy platform is untouched.

```
LOOPA_SAAS_ENABLED=false          # master switch (default OFF)
LOOPA_SAAS_ADMIN_TOKEN=<random>   # required to enable admin endpoints
LOOPA_SAAS_DEFAULT_PLAN=free      # plan for newly provisioned tenants
LOOPA_SAAS_FREE_RATE_PER_MIN=     # optional free-tier rate override
LOOPA_SAAS_DB_PATH=               # optional path for the saas control-plane DB
```

See `.env.example`. The SaaS control plane uses its own SQLite database
(`loopa_saas.db` by default), kept SEPARATE from `loopa_intelligence.db`, so the
existing catalog data is never modified.

### What it adds

- Tenant identity (`saas_tenants`) with per-tenant API keys (`saas_api_keys`,
  hash-only storage, plaintext shown once at mint time).
- Per-tenant data isolation: each tenant sees only the niche markets granted to
  it (allow-list in `saas_tenant_niche`, or `full_catalog=True`). Pain points and
  vendor matches are re-anchored to that allow-list, so there is no way to pivot
  into another tenant's data.
- Subscription tiers (free / pro / enterprise) with feature entitlements and
  quotas (`saas/plans.py`). Unknown plans fall back to free (least privilege).
- A versioned public API under `/api/v1` with bearer-key auth and per-tenant
  rate limiting.

### Plan tiers

| Plan       | Niches/req | Total niches | Rate/min | Vendor matches | Full report | Export |
|------------|-----------|--------------|----------|----------------|-------------|--------|
| free       | 5         | 10           | 30       | no             | no          | no     |
| pro        | 50        | 500          | 120      | yes            | yes         | no     |
| enterprise | 200       | unlimited    | 600      | yes            | yes         | yes    |

### Run the API locally

```
pip install -r requirements.txt
LOOPA_SAAS_ENABLED=true LOOPA_SAAS_ADMIN_TOKEN=dev-token \
  python -m uvicorn saas.app:app --reload
```

Then provision a tenant (admin token required):

```
# create a tenant
curl -XPOST localhost:8000/api/v1/admin/tenants \
  -H "Authorization: Bearer dev-token" \
  -d '{"name":"Acme","plan":"pro","full_catalog":true}'

# mint an API key (plaintext returned once)
curl -XPOST localhost:8000/api/v1/admin/tenants/<tenant_id>/keys \
  -H "Authorization: Bearer dev-token"

# call the tenant API
curl localhost:8000/api/v1/niches -H "Authorization: Bearer lpk_..."
```

Interactive docs: `/api/v1/docs`.

### Tests

```
python -m pytest tests/ -q
```

Tests run entirely against temporary databases with no real secrets, and cover
tenant isolation, entitlement gating, auth, rate limiting, and the feature flag.


