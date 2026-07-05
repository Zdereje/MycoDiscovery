"""
prisma.py
Tracks counts through the standard systematic-review funnel so you can
build a PRISMA flow diagram for the methods section:

    Identification  -> records found via database searching (raw esearch hits)
    Deduplication   -> unique records after removing duplicate PMIDs across
                       queries (a paper can match both the compound query
                       and the mutation query, or match for multiple targets)
    Screening       -> records with title/abstract reviewed
    Eligibility     -> records assessed in full text against inclusion/
                       exclusion criteria (protocol.py)
    Included        -> records contributing >=1 verified compound or
                       mutation record to the final database

Usage: call record_stage() at each pipeline step; export_summary() writes
a JSON you can hand to a PRISMA diagram generator (e.g. the PRISMA2020
R package, or just draw it manually from these numbers).
"""
import json
from pathlib import Path
from datetime import datetime, timezone

SUMMARY_PATH = Path("data/prisma_summary.json")


class PrismaTracker:
    def __init__(self):
        self.stages = {
            "identification": {"count": 0, "detail": {}},
            "deduplication": {"count": 0, "detail": {}},
            "screening_excluded": {"count": 0, "reasons": {}},
            "eligibility_excluded": {"count": 0, "reasons": {}},
            "included": {"count": 0, "detail": {}},
        }

    def record_identification(self, per_target_counts: dict):
        total = sum(per_target_counts.values())
        self.stages["identification"] = {"count": total, "detail": per_target_counts}

    def record_deduplication(self, unique_count: int, duplicates_removed: int):
        self.stages["deduplication"] = {
            "count": unique_count, "detail": {"duplicates_removed": duplicates_removed}
        }

    def record_exclusion(self, stage: str, reason: str, n: int = 1):
        key = "screening_excluded" if stage == "screening" else "eligibility_excluded"
        self.stages[key]["count"] += n
        self.stages[key]["reasons"][reason] = self.stages[key]["reasons"].get(reason, 0) + n

    def record_included(self, per_target_counts: dict):
        total = sum(per_target_counts.values())
        self.stages["included"] = {"count": total, "detail": per_target_counts}

    def export_summary(self, path: Path = SUMMARY_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stages": self.stages,
        }
        path.write_text(json.dumps(payload, indent=2))
        return payload

    def print_flow(self):
        s = self.stages
        print("PRISMA FLOW SUMMARY")
        print(f"  Identification (database search hits): {s['identification']['count']}")
        print(f"  After deduplication:                   {s['deduplication']['count']}")
        print(f"  Excluded at screening:                 {s['screening_excluded']['count']}")
        for reason, n in s["screening_excluded"]["reasons"].items():
            print(f"      - {reason}: {n}")
        print(f"  Excluded at eligibility (full text):    {s['eligibility_excluded']['count']}")
        for reason, n in s["eligibility_excluded"]["reasons"].items():
            print(f"      - {reason}: {n}")
        print(f"  Included in final database:             {s['included']['count']}")
