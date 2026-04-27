# utils/monitoring.py
# Writes a compact operational status snapshot for scheduler/API/Opsera checks.

import json
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_session
from database.schema import IntelligenceRun, NicheMarket, PainPoint, Vendor, VendorPainPointMap


def build_status() -> dict:
    session = get_session()
    try:
        latest_run = session.query(IntelligenceRun).order_by(IntelligenceRun.id.desc()).first()
        researched_niches = session.query(PainPoint.niche_market_id).distinct().count()
        total_niches = session.query(NicheMarket).count()

        status = {
            "generated_at": datetime.now().isoformat(),
            "status": "ok",
            "counts": {
                "niche_markets": total_niches,
                "researched_niches": researched_niches,
                "unresearched_niches": max(total_niches - researched_niches, 0),
                "pain_points": session.query(PainPoint).count(),
                "vendors": session.query(Vendor).count(),
                "vendor_matches": session.query(VendorPainPointMap).count(),
            },
            "latest_run": None,
            "warnings": [],
        }

        if latest_run:
            status["latest_run"] = {
                "id": latest_run.id,
                "type": latest_run.run_type,
                "status": latest_run.status,
                "total_items": latest_run.total_items,
                "success_count": latest_run.success_count,
                "failure_count": latest_run.failure_count,
                "started_at": latest_run.started_at.isoformat() if latest_run.started_at else None,
                "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
            }
            if latest_run.failure_count:
                status["warnings"].append(f"Latest run has {latest_run.failure_count} failures")

        if total_niches and researched_niches / total_niches < 0.05:
            status["warnings"].append("Less than 5% of niche markets have generated pain points")

        if not status["counts"]["vendor_matches"]:
            status["warnings"].append("No vendor matches saved")

        if status["warnings"]:
            status["status"] = "warning"

        return status
    finally:
        session.close()


def save_status(output_path: str = None) -> str:
    if not output_path:
        output_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "monitoring_status.json",
        )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(build_status(), f, indent=2)

    return output_path


if __name__ == "__main__":
    path = save_status()
    print(f"Monitoring status saved: {path}")
