# Loopa VendorScope + NicheRadar Phase 0 Review Summary

## Summary

Phase 0 for both new agents is now implemented as a local, deterministic foundation on top of the existing Loopa Intelligence Platform.

This is not the full production version from the PRDs yet. The completed scope is the foundation layer: database schema, existing-data seeding, deterministic scoring, provenance tables, and review exports.

## What Was Completed

### VendorScope / Vendor-Matchmaking Agent

VendorScope is the vendor-side intelligence agent. Its long-term purpose is to continuously update the vendor catalog, collect vendor-side matchmaking variables, and improve vendor readiness and match scoring.

Completed in Phase 0:

- Added VendorScope database tables:
  - `vendor_intelligence_profiles`
  - `vendor_intelligence_variables`
  - `vendor_score_history`
  - `vendor_alerts`
- Seeded existing Loopa vendor catalog into VendorScope.
- Created the PRD-aligned 80-variable vendor catalog.
- Computed initial deterministic scores:
  - Trust Score
  - Fit Score
  - Operational Score
  - Vendor Quality Score (VQS)
- Generated a vendor review export.

Current VendorScope results:

- Vendors processed: 3,431
- Vendor intelligence profiles: 3,431
- Vendor intelligence variables: 58,327
- Review Ready vendors: 203
- Submission Incomplete vendors: 3,228
- Open review alerts: 6,659
- Average VQS: 60.02
- Max VQS: 99.3

Export:

- `data/vendor_intelligence_export_20260505_114509.csv`

Important note:

Review Ready now means internal QA-ready, not marketplace publish-ready. The safeguard requires core commercial and matching fields: product category, target segment, pricing signal, compliance coverage, website/source anchor, and at least one match variable. Vendors missing these fields remain Submission Incomplete.

All VendorScope match confidence values currently remain conservative because Phase 0 uses only existing catalog data. External verification sources such as WHOIS, G2, Crunchbase, LinkedIn, OpenCorporates, and vendor trust centers are not connected yet.

### NicheRadar / Niche Market ICP Discovery Agent

NicheRadar is the demand-side intelligence agent. Its long-term purpose is to continuously re-score niche markets, identify the true ICP, discover real accounts, and feed sales workflows.

Completed in Phase 0:

- Added NicheRadar database tables:
  - `niche_radar_scores`
  - `niche_radar_variables`
  - `niche_radar_score_history`
  - `account_leads`
- Backfilled all researched niche markets into NicheRadar.
- Computed initial deterministic scores:
  - Vulnerability Score
  - Payability Score
  - Reachability Score
  - NPS_VA
- Computed vendor-supply gate:
  - marketplace vendor count serving niche
  - top pain point coverage percentage
  - average match score for niche
- Generated a NicheRadar review export.

Current NicheRadar results:

- Niche markets processed: 1,032
- NicheRadar scores: 1,032
- NicheRadar variables: 39,216
- Tier 1 - Hunt now: 0
- Tier 2 - Build pipeline: 78
- Tier 3 - Watchlist: 953
- Tier 4 - Defer: 1
- Tier 1 Candidate: 7
- Tier 2 - Priority Watchlist: 18

Export:

- `data/niche_radar_export_20260505_114428.csv`
- `data/niche_radar_nps_top20_20260505.csv`

Important note:

The strict Tier 1 rule is unchanged: `nps_va >= 75 AND reachability >= 60 AND tier1_supply = true`. The result currently has zero Tier 1 niches because no niche satisfies all three conditions together. A separate `priority_watchlist_status` was added so near-cutoff niches can be reviewed without manually promoting them to Tier 1.

NPS_VA distribution:

- Min: 29.35
- Median: 54.14
- Max: 75.62
- Count >= 60: 248
- Count >= 65: 103
- Count >= 70: 32
- Count >= 75: 1

## What Is Not Completed Yet

The following PRD items are not part of Phase 0 and have not been implemented yet:

- External vendor enrichment:
  - WHOIS
  - G2
  - Crunchbase
  - LinkedIn
  - OpenCorporates
  - vendor trust center scraping
- Vendor onboarding prefill invite links
- Vendor portal UX
- Slack / Linear alert automation
- Human review queue UI
- Account discovery by state
- Apollo / ZoomInfo / D&B enrichment
- Email, LinkedIn, or phone contact discovery
- Personalized outbound message generation
- Zoho CRM push
- Automated outreach

## Recommended Review Questions

1. Based on the NPS_VA distribution, should Tier 1 remain at `nps_va >= 75`, or should we test a cutoff of 70 or 65?
2. Should the `Tier 1 Candidate` rule stay as `tier1_supply = true AND reachability >= 60 AND 65 <= nps_va < 75`?
3. Which external VendorScope source should be prioritized first?
   - vendor websites / trust centers
   - WHOIS
   - OpenCorporates
   - G2
   - Crunchbase
   - LinkedIn
4. Which NicheRadar path should come next?
   - account discovery pilot
   - Zoho CRM field mapping
   - Apollo / ZoomInfo enrichment

## Recommended Next Step

Recommended next step: review the NPS_VA distribution and top 20 NicheRadar output with Hamid before changing the Tier 1 cutoff.

The key decision is whether to preserve the strict `nps_va >= 75` cutoff or run a controlled comparison at 70 or 65. Tier 2 items should not be manually promoted into Tier 1 without a scoring-rule change.
