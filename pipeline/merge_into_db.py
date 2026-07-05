"""
merge_into_db.py
Promotes VERIFIED rows only (verification_status == "verified") from the
curated CSVs into mycomut_targets_v1.json.

This replaces the hardcoded-Python-dict approach from build_target_centric.py
with a provenance-preserving pipeline: every compound/mutation in the
published JSON can be traced back to (a) the exact PubMed query that
surfaced it, (b) the PMID/DOI, (c) who curated it, and (d) when.

Idempotent: rerunning with an updated CSV re-derives the compounds/mutations
arrays per target from scratch (does not append duplicates), so this is safe
to run repeatedly as curation continues over time.

Usage:
    python3 merge_into_db.py \\
        --json mycomut_targets_v1.json \\
        --compounds data/compounds_candidates.csv \\
        --mutations data/mutations_candidates.csv \\
        --out mycomut_targets_v2.json
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

from extraction_schema import read_verified, CompoundCandidate, MutationCandidate


def build_target_data(compound_rows, mutation_rows):
    """Returns {target_id: {compound_name: {..compound fields.., mutations: [...]}}}"""
    targets = defaultdict(dict)

    for row in compound_rows:
        tid = row["target_id"]
        targets[tid][row["compound_name"]] = {
            "name": row["compound_name"],
            "class": row["compound_class"],
            "phase": row["phase_or_status"],
            "mechanism": row["mechanism"],
            "mutations": [],
            "provenance": {
                "pmid": row["pmid"], "doi": row["doi"],
                "source_query": row["source_query"],
                "protocol_version": row["protocol_version"],
                "curator": row["curator"], "curation_date": row["curation_date"],
            },
        }

    for row in mutation_rows:
        tid = row["target_id"]
        cname = row["compound_name"]
        if tid not in targets or cname not in targets[tid]:
            # Mutation references a compound not (yet) verified in the
            # compound CSV — skip but this should be investigated, not
            # silently dropped in a real run.
            print(f"WARNING: mutation row references unverified/unknown "
                  f"compound '{cname}' for target '{tid}' — skipping. "
                  f"PMID:{row.get('pmid')}")
            continue
        targets[tid][cname]["mutations"].append({
            "gene": row["gene"], "aa_change": row["aa_change"], "effect": row["effect"],
            "citation": row["citation_text"],
            "provenance": {
                "pmid": row["pmid"], "doi": row["doi"],
                "source_query": row["source_query"],
                "protocol_version": row["protocol_version"],
                "curator": row["curator"], "curation_date": row["curation_date"],
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
    ap.add_argument("--compounds", required=True, help="Curated compounds CSV")
    ap.add_argument("--mutations", required=True, help="Curated mutations CSV")
    ap.add_argument("--out", required=True, help="Output path for merged JSON")
    args = ap.parse_args()

    db = json.loads(Path(args.json).read_text())

    compound_rows = read_verified(Path(args.compounds), CompoundCandidate)
    mutation_rows = read_verified(Path(args.mutations), MutationCandidate)
    print(f"Verified compound rows: {len(compound_rows)}")
    print(f"Verified mutation rows: {len(mutation_rows)}")

    target_data = build_target_data(compound_rows, mutation_rows)
    merged = merge(db, target_data)

    total_targets = sum(len(c["targets"]) for c in merged["categories"])
    verified_targets = sum(1 for c in merged["categories"] for t in c["targets"] if t["status"] == "verified")
    merged["metadata"]["verified_targets"] = verified_targets
    merged["metadata"]["scaffold_targets"] = total_targets - verified_targets
    merged["metadata"]["total_compounds_catalogued"] = sum(
        len(t.get("compounds", [])) for c in merged["categories"] for t in c["targets"]
    )
    merged["metadata"]["total_mutations_catalogued"] = sum(
        len(cm.get("mutations", [])) for c in merged["categories"] for t in c["targets"]
        for cm in t.get("compounds", [])
    )

    Path(args.out).write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    print(f"Wrote {args.out}")
    print(f"Verified targets: {verified_targets}/{total_targets}")


if __name__ == "__main__":
    main()
