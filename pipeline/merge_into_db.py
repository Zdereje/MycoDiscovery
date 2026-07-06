"""
merge_into_db.py
Promotes VERIFIED rows only (verification_status == "verified") from the
unified candidates.csv into mycodiscovery_targets_*.json.

Schema note: a single compound can legitimately appear in multiple papers
(different assay conditions, different MIC values, different mutations
reported). Rather than flattening that into one row and losing information,
each compound gets a `records` list — one entry per paper — so nothing about
"which paper reported which MIC/mutation" gets silently merged away.

Idempotent: rerunning with an updated CSV re-derives each target's compound
list from scratch, so this is safe to run repeatedly as curation continues.

Usage:
    python3 merge_into_db.py \\
        --json mycodiscovery_targets_v1.json \\
        --candidates data/candidates.csv \\
        --out mycodiscovery_targets_v2.json
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from extraction_schema import read_verified


def build_target_data(rows):
    """Returns {target_id: {compound_name: {..fields.., records: [...]}}}"""
    targets = defaultdict(dict)

    for row in rows:
        tid = row["target_id"]
        cname = row["compound_name"].strip()
        if not cname:
            print(f"WARNING: verified row for target '{tid}' (PMID:{row.get('pmid')}) "
                  f"has no compound_name — skipping. Fill this in during curation.")
            continue

        if cname not in targets[tid]:
            targets[tid][cname] = {
                "name": cname,
                "class": row.get("compound_class", ""),
                "phase": row.get("phase_or_status", ""),
                "clinicaltrials_id": row.get("ClinicalTrials.gov ID", ""),
                "records": [],
            }

        targets[tid][cname]["records"].append({
            "bacteria": row.get("Bacteria", ""),
            "assay_type": row.get("Type", ""),
            "method": row.get("Method", ""),
            "mic_ug_ml": row.get("MIC [ug/mL]", ""),
            "mechanism": row.get("mechanism", ""),
            "reference_genome": row.get("Reference genome", ""),
            "gene": row.get("Gene", ""),
            "function": row.get("Function", ""),
            "mutations": row.get("Mutations", ""),
            "citation": row.get("citation_text", ""),
            "provenance": {
                "pmid": row.get("pmid", ""),
                "doi": row.get("doi", ""),
                "source_query": row.get("source_query", ""),
                "protocol_version": row.get("protocol_version", ""),
                "curator": row.get("curator", ""),
                "curation_date": row.get("curation_date", ""),
            },
        })

    return targets


def merge(db: dict, target_data: dict) -> dict:
    verified_target_ids = set(target_data.keys())
    for category in db["categories"]:
        for target in category["targets"]:
            if target["id"] in verified_target_ids:
                compounds = list(target_data[target["id"]].values())
                target["compounds"] = compounds
                target["status"] = "verified" if compounds else target.get("status", "scaffold")
    return db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="Existing target-centric JSON to merge into")
    ap.add_argument("--candidates", required=True, help="Curated unified candidates CSV")
    ap.add_argument("--out", required=True, help="Output path for merged JSON")
    args = ap.parse_args()

    db = json.loads(Path(args.json).read_text())

    rows = read_verified(Path(args.candidates))
    print(f"Verified rows: {len(rows)}")

    target_data = build_target_data(rows)
    merged = merge(db, target_data)

    total_targets = sum(len(c["targets"]) for c in merged["categories"])
    verified_targets = sum(1 for c in merged["categories"] for t in c["targets"] if t["status"] == "verified")
    merged["metadata"]["verified_targets"] = verified_targets
    merged["metadata"]["scaffold_targets"] = total_targets - verified_targets
    merged["metadata"]["total_compounds_catalogued"] = sum(
        len(t.get("compounds", [])) for c in merged["categories"] for t in c["targets"]
    )
    merged["metadata"]["total_records_catalogued"] = sum(
        len(cm.get("records", [])) for c in merged["categories"] for t in c["targets"]
        for cm in t.get("compounds", [])
    )

    Path(args.out).write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    print(f"Wrote {args.out}")
    print(f"Verified targets: {verified_targets}/{total_targets}")


if __name__ == "__main__":
    main()
