# Loopa Data Quality Agent Enforcement Summary

## Purpose

The Data Quality Agent is now a deterministic gate on top of the three Loopa inputs/tools Hamid called out:

- Loopa core data: niche markets, pain points, vendors, and vendor-pain-point matches.
- VendorScope: vendor intelligence profiles, readiness status, and review-ready safeguards.
- NicheRadar: NPS_VA scoring, tiering, vendor-supply gate, and priority watchlist status.

This keeps the data quality layer inside the Loopa pipeline before any downstream enrichment, account discovery, sales export, or outreach workflow consumes the outputs.

## Enforcement Points

### VendorScope

`agents/vendor_scope_agent.py` now automatically runs:

```bash
.venv/bin/python agents/data_quality_agent.py --target vendor_scope
```

after VendorScope scoring completes.

If any critical findings are found, VendorScope exits with a non-zero status and blocks the vendor intelligence export.

Vendor intelligence exports now include:

- `dq_status`
- `dq_run_id`
- `dq_quality_score`

Limited smoke runs using `--limit` skip DQ enforcement so partial test runs are not incorrectly treated as full-catalog failures.

### NicheRadar

`agents/niche_radar_agent.py` now automatically runs:

```bash
.venv/bin/python agents/data_quality_agent.py --target niche_radar
```

after NicheRadar scoring completes.

If any critical findings are found, NicheRadar exits with a non-zero status and blocks the NicheRadar export.

NicheRadar exports now include:

- `dq_status`
- `dq_run_id`
- `dq_quality_score`

Limited smoke runs using `--limit` skip DQ enforcement so partial test runs are not incorrectly treated as full-catalog failures.

### Loopa Core / Sales Export

`utils/sales_exporter.py` now automatically runs:

```bash
.venv/bin/python agents/data_quality_agent.py --target core
```

before building the sales export.

If any critical findings are found, the sales export is blocked.

Sales exports now include:

- `dq_status`
- `dq_run_id`
- `dq_quality_score`

## Current Verified Result

Latest full Data Quality run:

- Target: `all`
- Status: `pass`
- Quality score: `100.0`
- Rows checked: `14,456`
- Critical findings: `0`
- Warnings: `0`

Per target:

- `core`: pass, 9,993 rows checked
- `vendor_scope`: pass, 3,431 rows checked
- `niche_radar`: pass, 1,032 rows checked

## Checks Covered

Core checks:

- Required niche identity fields.
- Niche score ranges.
- Pain point rank and severity sanity.
- Vendor-pain-point foreign key consistency.
- Vendor match score range consistency.

VendorScope checks:

- One intelligence profile per vendor.
- Vendor score ranges.
- Review Ready safeguard consistency.
- Provenance variable presence.

NicheRadar checks:

- One score per researched niche.
- NPS_VA / vulnerability / payability / reachability score ranges.
- Vendor-supply gate consistency.
- Tier rule consistency.
- Priority watchlist consistency.
- Provenance variable presence.

## Recommended Next Step

With the DQ gate now built and enforced, the next product step is a controlled Phase 1 pilot:

1. Pick 2-3 niches from `Tier 1 Candidate` / `Tier 2 - Priority Watchlist`.
2. Build the first account-level export schema.
3. Pilot account discovery for a small number of states before connecting paid Apollo / ZoomInfo workflows.
