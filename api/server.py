# api/server.py
# Lightweight local JSON API for Loopa dashboard integration.

import json
import os
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_session
from database.schema import IntelligenceRun, NicheMarket, PainPoint, RunItem, Vendor, VendorPainPointMap


def _to_iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def dashboard_summary() -> dict:
    session = get_session()
    try:
        latest_run = session.query(IntelligenceRun).order_by(IntelligenceRun.id.desc()).first()
        return {
            "generated_at": datetime.now().isoformat(),
            "niche_markets": session.query(NicheMarket).count(),
            "researched_niches": session.query(PainPoint.niche_market_id).distinct().count(),
            "pain_points": session.query(PainPoint).count(),
            "vendors": session.query(Vendor).count(),
            "vendor_matches": session.query(VendorPainPointMap).count(),
            "tier_counts": {
                "tier_1": session.query(NicheMarket).filter_by(priority_tier=1).count(),
                "tier_2": session.query(NicheMarket).filter_by(priority_tier=2).count(),
                "tier_3": session.query(NicheMarket).filter_by(priority_tier=3).count(),
                "unscored": session.query(NicheMarket).filter(NicheMarket.priority_tier == None).count(),
            },
            "latest_run": _run_to_dict(latest_run) if latest_run else None,
        }
    finally:
        session.close()


def top_niches(limit: int = 20, tier: int = None) -> list:
    session = get_session()
    try:
        query = session.query(NicheMarket).filter(NicheMarket.priority_score != None)
        if tier:
            query = query.filter_by(priority_tier=tier)
        query = query.order_by(NicheMarket.priority_score.desc()).limit(limit)
        return [_niche_to_dict(niche) for niche in query.all()]
    finally:
        session.close()


def recent_runs(limit: int = 10) -> list:
    session = get_session()
    try:
        runs = session.query(IntelligenceRun).order_by(IntelligenceRun.id.desc()).limit(limit).all()
        return [_run_to_dict(run) for run in runs]
    finally:
        session.close()


def run_items(run_id: int, limit: int = 100) -> list:
    session = get_session()
    try:
        items = (
            session.query(RunItem, NicheMarket)
            .join(NicheMarket, NicheMarket.id == RunItem.niche_market_id)
            .filter(RunItem.run_id == run_id)
            .order_by(RunItem.id.asc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": item.id,
                "niche_market_id": item.niche_market_id,
                "niche_market": niche.niche_name,
                "status": item.status,
                "attempts": item.attempts,
                "error_message": item.error_message,
                "priority_score": item.priority_score,
                "priority_tier": item.priority_tier,
                "started_at": _to_iso(item.started_at),
                "completed_at": _to_iso(item.completed_at),
            }
            for item, niche in items
        ]
    finally:
        session.close()


def niche_detail(niche_id: int) -> dict:
    session = get_session()
    try:
        niche = session.query(NicheMarket).filter_by(id=niche_id).first()
        if not niche:
            return {"error": "not_found"}

        pain_points = (
            session.query(PainPoint)
            .filter_by(niche_market_id=niche.id)
            .order_by(PainPoint.pain_point_rank.asc())
            .all()
        )

        pain_point_rows = []
        for pain_point in pain_points:
            matches = (
                session.query(VendorPainPointMap, Vendor)
                .join(Vendor, Vendor.id == VendorPainPointMap.vendor_id)
                .filter(VendorPainPointMap.pain_point_id == pain_point.id)
                .order_by(VendorPainPointMap.match_score.desc())
                .limit(3)
                .all()
            )
            pain_point_rows.append({
                "id": pain_point.id,
                "rank": pain_point.pain_point_rank,
                "name": pain_point.pain_point_name,
                "category": pain_point.cyber_category,
                "subcategory": pain_point.cyber_subcategory,
                "severity": pain_point.severity_score,
                "vendor_matches": [
                    {
                        "vendor_name": vendor.vendor_name,
                        "match_score": match.match_score,
                        "confidence": match.confidence_label,
                        "match_type": match.match_type,
                        "notes": match.notes,
                    }
                    for match, vendor in matches
                ],
            })

        data = _niche_to_dict(niche)
        data["pain_points"] = pain_point_rows
        return data
    finally:
        session.close()


def _niche_to_dict(niche: NicheMarket) -> dict:
    return {
        "id": niche.id,
        "niche_name": niche.niche_name,
        "industry_path": " > ".join(
            p for p in [
                niche.industry,
                niche.sub_industry,
                niche.sub_sub_industry,
                niche.sub_sub_sub_industry,
                niche.sub_sub_sub_sub_industry,
            ] if p
        ),
        "naics_code": niche.naics_code,
        "geography": niche.geography,
        "priority_score": niche.priority_score,
        "priority_tier": niche.priority_tier,
        "demand_score": niche.demand_score,
        "outbound_score": niche.outbound_score,
        "primary_buyer_role": niche.primary_buyer_role,
        "likely_compliance": niche.likely_compliance_regimes,
        "recommended_cyber_themes": niche.recommended_cyber_themes,
        "last_updated": _to_iso(niche.last_updated),
    }


def _run_to_dict(run: IntelligenceRun) -> dict:
    return {
        "id": run.id,
        "run_type": run.run_type,
        "status": run.status,
        "total_items": run.total_items,
        "success_count": run.success_count,
        "failure_count": run.failure_count,
        "skipped_count": run.skipped_count,
        "source": run.source,
        "ai_model": run.ai_model,
        "started_at": _to_iso(run.started_at),
        "completed_at": _to_iso(run.completed_at),
    }


class LoopaHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        try:
            if parsed.path == "/health":
                self._send({"status": "ok", "service": "loopa-api"})
            elif parsed.path == "/dashboard/summary":
                self._send(dashboard_summary())
            elif parsed.path == "/niches/top":
                self._send(top_niches(
                    limit=int(params.get("limit", [20])[0]),
                    tier=int(params["tier"][0]) if params.get("tier") else None,
                ))
            elif parsed.path.startswith("/niches/"):
                self._send(niche_detail(int(parsed.path.rsplit("/", 1)[-1])))
            elif parsed.path == "/runs":
                self._send(recent_runs(limit=int(params.get("limit", [10])[0])))
            elif parsed.path.startswith("/runs/") and parsed.path.endswith("/items"):
                run_id = int(parsed.path.split("/")[2])
                self._send(run_items(run_id, limit=int(params.get("limit", [100])[0])))
            else:
                self._send({"error": "not_found"}, status=404)
        except Exception as exc:
            self._send({"error": str(exc)}, status=500)

    def log_message(self, format, *args):
        return

    def _send(self, payload, status: int = 200):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run(host: str = "127.0.0.1", port: int = 8787):
    server = HTTPServer((host, port), LoopaHandler)
    print(f"Loopa API listening on http://{host}:{port}")
    print("Endpoints: /health, /dashboard/summary, /niches/top, /runs")
    server.serve_forever()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Start the Loopa local JSON API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    run(host=args.host, port=args.port)
