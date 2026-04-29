# Loopa to ICP App Integration

This note captures the current integration decision point between the Loopa
Python intelligence pipeline and the Value Aligners signed-in app.

## Current State

- Loopa source data lives in SQLite locally and has been synced to Azure SQL.
- The signed-in app's ICP routes use MongoDB models under `MVP_Cybersecurity_React/azure-deploy`.
- The app-side `NicheMarket` model expects fields such as `niche_market_name`, `sector`, `sector_code`, `naics_code`, `priority_tier`, compliance regimes, cyber themes, and several 1-5 scoring dimensions.
- Loopa's canonical model stores richer research fields in SQL: hierarchy, scores, ICP fields, compliance tags, pain points, vendors, and vendor matches.

## Integration Options

1. **Expose Loopa API to the app**
   - Keep Azure SQL as the source of truth.
   - Add authenticated endpoints for top niches, niche detail, pain points, and vendor matches.
   - Point app ICP pages to the Loopa API where live intelligence is needed.

2. **Sync Loopa SQL data into MongoDB**
   - Keep the existing app API and Mongo models.
   - Add a sync job that maps Loopa SQL rows into the app's `NicheMarket` collection.
   - Use this when minimal app changes are preferred.

3. **Hybrid**
   - Sync summary niche rows into MongoDB for fast ICP account enrichment.
   - Fetch full pain-point and vendor-match detail from Loopa API on demand.

## Recommended Next Step

Start with option 2 for compatibility: build a one-way sync from Loopa SQL to
MongoDB `NicheMarket`, then evaluate whether detailed drill-downs should call
the Loopa API directly.

Minimum mapping:

| App Mongo field | Loopa SQL source |
| --- | --- |
| `niche_market_name` | `niche_markets.niche_name` |
| `sector` | `niche_markets.industry` |
| `sector_code` | `niche_markets.sector_code` |
| `naics_code` | `niche_markets.naics_code` |
| `ownership_sector` | `niche_markets.ownership_sector` |
| `primary_buyer_role` | `niche_markets.primary_buyer_role` |
| `likely_compliance_regimes` | split `niche_markets.likely_compliance_regimes` |
| `conditional_compliance_regimes` | split `niche_markets.conditional_compliance_regimes` |
| `recommended_cyber_themes` | split `niche_markets.recommended_cyber_themes` |
| `total_priority_score` | `niche_markets.priority_score` |
| `priority_tier` | map `1/2/3` to `Tier 1/2/3` |

Open field decision: the app has eight 1-5 dimension scores that are not a
direct one-to-one match with Loopa's two-layer scoring variables. Map them only
after Hamid confirms whether the app should preserve the current ICP formula or
switch to Loopa's Demand/Outbound/Priority model.
