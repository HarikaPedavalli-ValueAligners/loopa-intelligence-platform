# VendorScope + NicheRadar Initial Scope

Prepared for the Loopa Intelligence Platform after reviewing:

- `Vendor-Matchmaking Agent-PRD.md`
- `ValueAligners-NicheMarket-ICP-Discovery-Agent-PRD.md`
- Current `sales_export_20260502_053515.csv` output

## Current Platform Baseline

The current Loopa platform has completed the Phase 2 data run:

- 1,032 niche markets researched
- 3,096 pain points generated
- 3,431 vendors imported
- 2,434 vendor-pain point matches generated
- Sales export generated and documented with a Project Overview and Data Dictionary
- Local SQLite and Azure SQL have been synced and verified

The current system is strong as a batch intelligence and sales-export pipeline. The two new PRDs move the platform from batch output into continuous marketplace intelligence.

## Agent 1: VendorScope

VendorScope is the supply-side agent. It maintains a continuously refreshed vendor intelligence layer and improves vendor-to-pain-point matching.

### MVP Goal

Build a deterministic vendor intelligence foundation that can enrich the existing vendor table, track matchmaking variables, compute vendor readiness scores, and prepare the system for future vendor onboarding prefill.

### MVP Inputs

- Existing `vendors` table
- Existing `vendor_pain_point_map` table
- Vendor website/domain fields from imported marketplace data
- Current `sales_export` fields, especially:
  - `vendor_name`
  - `vendor_category`
  - `vendor_target_market`
  - `vendor_rating`
  - `match_score`
  - `match_confidence`
  - `match_type`
  - `matched_terms`

### MVP Outputs

- Enriched vendor profile table
- Vendor variable table with source/provenance
- Trust/Fit/Operational score placeholders
- Vendor Quality Score (VQS)
- Readiness status:
  - `discovered`
  - `enriched`
  - `validated`
  - `onboarded`
  - `listed`
  - `paused`
  - `removed`
- Updated match metadata for future sales exports

### Recommended MVP Tables

1. `vendor_intelligence_profiles`
   - one row per vendor
   - stores canonical identity, domain, readiness status, composite scores, and freshness status

2. `vendor_intelligence_variables`
   - one row per vendor variable
   - stores value, source URL, source type, confidence, collected timestamp, refresh cadence, and prior value

3. `vendor_score_history`
   - append-only score snapshots
   - supports score deltas over time

4. `vendor_alerts`
   - stores score changes, missing gates, failed freshness SLA, and other review flags

### Phase 0 Build Tasks

1. Add database schema for the four MVP tables.
2. Seed `vendor_intelligence_profiles` from the existing `vendors` table.
3. Create a controlled vendor variable catalog from the PRD's 80 variables.
4. Implement a local scoring module that computes:
   - Trust Score
   - Fit Score
   - Operational Score
   - VQS
   - match confidence
5. Produce a vendor intelligence export for review.

### Not in MVP

- Full web crawling across Crunchbase, G2, LinkedIn, Gartner, etc.
- Vendor portal prefill UX
- Invite-link token flow
- Automated Slack or Linear alerts
- Human review queue UI

These should be Phase 1 or later because they require external API access, source licensing, product surface decisions, and security review.

## Agent 2: NicheRadar

NicheRadar is the demand-side agent. It continuously updates niche market intelligence, discovers real companies inside high-priority niches, ranks accounts, and eventually produces outreach assets.

### MVP Goal

Re-score the existing 1,032 niche markets using the new PRD framework and produce a clearer Tier 1 list for manual quality review before any account discovery or outreach automation.

### MVP Inputs

- Existing `niche_markets`
- Existing `pain_points`
- Existing `vendor_pain_point_map`
- Current `sales_export`
- Current compliance and recommended cyber theme fields

### MVP Outputs

- NicheRadar score table
- New NPS_VA score:
  - Vulnerability Score
  - Payability Score
  - Reachability Score
- Vendor-supply gate:
  - marketplace vendor count serving niche
  - top pain point coverage percentage
  - average match score for niche
- Refined tier:
  - Tier 1: Hunt now
  - Tier 2: Build pipeline
  - Tier 3: Watchlist
  - Tier 4: Defer
- `niche_radar_export_<date>.csv`

### Recommended MVP Tables

1. `niche_radar_scores`
   - one row per niche
   - stores the three component scores, NPS_VA, refined tier, vendor-supply fields, and freshness

2. `niche_radar_variables`
   - one row per niche variable
   - stores value, source, confidence, and refresh cadence

3. `niche_radar_score_history`
   - append-only score snapshots

4. `account_leads`
   - placeholder for future account discovery output
   - not populated until account data sources are confirmed

### Phase 0 Build Tasks

1. Add database schema for NicheRadar scoring and variable provenance.
2. Backfill the 1,032 existing niches into `niche_radar_scores`.
3. Compute vendor-supply gate from current vendor matches.
4. Produce first Tier 1/Tier 2 candidate list.
5. Export a QA workbook or CSV for manual review with Hamid/Nathan/Waamene.

### Not in MVP

- State-by-state account discovery
- LinkedIn/email message generation
- Zoho CRM push
- Apollo/ZoomInfo/D&B enrichment
- Automated outbound
- Trigger monitoring

These depend on data-provider access, compliance review, sender-domain readiness, and CRM schema decisions.

## Shared Matching Foundation

Both agents should share a controlled taxonomy layer:

- canonical pain point library
- vendor categories
- capability tags
- NAICS mapping
- persona roles
- compliance frameworks

The PRDs call out that the current pain point library has too much granularity. The first taxonomy task should be to collapse current pain point names/categories into a smaller canonical set so vendor capabilities can be matched reliably.

## Recommended Execution Order

1. Lock scope with Hamid: confirm that Phase 0 should be schema + scoring + exports, not external crawling.
2. Create schema migration for VendorScope and NicheRadar MVP tables.
3. Seed VendorScope from existing 3,431 vendors.
4. Seed NicheRadar from existing 1,032 niches.
5. Implement deterministic scoring modules.
6. Generate:
   - `vendor_intelligence_export_<date>.csv`
   - `niche_radar_export_<date>.csv`
7. Review Tier 1/Tier 2 quality manually.
8. Only after review, decide which external connectors to build first.

## Questions for Hamid

1. Should Phase 0 use Azure SQL as the main source of truth, or continue local SQLite development and sync after validation?
2. For VendorScope, which external source should be licensed or prioritized first: Crunchbase, G2, LinkedIn Sales Navigator, OpenCorporates, or vendor websites?
3. For NicheRadar, should we prioritize refined niche scoring first, or account discovery for a small pilot set?
4. Which CRM fields should be added to Zoho for future account-level leads?
5. Should Tier 1 be manually approved before any outreach assets are generated?
6. Should match scores remain on the current 0-1 scale used in the database, or be normalized to 0-100 as the PRD describes?
7. Who owns manual review for vendor gates: Hamid, Trust/Compliance, or another intern/team?

## Recommended Message to Hamid

Hi Hamid, I reviewed both the VendorScope and NicheRadar PRDs. My recommendation is to start with a Phase 0 foundation rather than jumping directly into external crawling or outreach automation.

For VendorScope, Phase 0 would add the vendor intelligence schema, seed it from our existing 3,431 vendors, define the 80-variable catalog, and compute initial Trust/Fit/Operational/VQS scores.

For NicheRadar, Phase 0 would add the niche scoring schema, backfill the existing 1,032 niches, compute the vendor-supply gate from current vendor matches, and produce the first refined Tier 1/Tier 2 candidate list for manual review.

This gives us a stable base before we add paid data providers, Zoho pushes, LinkedIn/email automation, or onboarding prefill links. Please confirm whether this Phase 0 scope matches your preferred direction, and which external data source you want prioritized first after the foundation is in place.
