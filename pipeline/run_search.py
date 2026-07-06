"""
run_search.py
Orchestrates the full systematic search: runs ONE combined query per target
(protocol.py v2.0.0+) against PubMed, deduplicates, logs everything, and
writes ONE curator-ready CSV template for the manual verification step.

This does NOT decide what's true. It surfaces candidates. A human curator
reviews every row before anything is trusted (see extraction_schema.py).

Usage:
    export NCBI_EMAIL="you@example.com"
    export NCBI_API_KEY="..."          # optional but recommended
    python3 run_search.py

Outputs:
    data/cache/                        raw esearch/efetch responses (cached)
    data/search_log.jsonl              every query run, with timestamp + count
    data/candidates_raw.jsonl          all fetched PubMed records, tagged by target
    data/candidates.csv                single curator template (see extraction_schema.py)
    data/prisma_summary.json           identification-stage PRISMA counts
"""
import json
import os
from pathlib import Path

from protocol import TARGETS, PROTOCOL_VERSION, all_queries
from pubmed_client import PubMedClient
from prisma import PrismaTracker
from extraction_schema import init_candidate_csv

DATA_DIR = Path("data")


def main():
    email = os.environ.get("NCBI_EMAIL")
    if not email:
        raise SystemExit(
            "Set NCBI_EMAIL before running (NCBI requires a contact email "
            "for all E-utilities traffic). e.g.:\n"
            "    export NCBI_EMAIL='you@example.com'"
        )

    client = PubMedClient(email=email)
    tracker = PrismaTracker()

    per_target_counts = {}
    all_records = []
    seen_pmids = set()   # one query type now, so a single set is correct again
    dup_count = 0
    candidates = []

    for target, query in all_queries():
        pmids = client.search(query, protocol_version=PROTOCOL_VERSION)
        per_target_counts[target.id] = len(pmids)

        new_pmids = [p for p in pmids if p not in seen_pmids]
        dup_count += len(pmids) - len(new_pmids)
        seen_pmids.update(new_pmids)

        records = client.fetch_summaries(new_pmids, source_query=query, protocol_version=PROTOCOL_VERSION)
        for rec in records:
            candidates.append({
                "target_id": target.id,
                "target_name": target.name,
                "pmid": rec.pmid,
                "doi": rec.doi or "",
                "citation_text": f"{rec.authors}. {rec.title} {rec.journal}. {rec.year}. PMID:{rec.pmid}",
                "source_query": query,
                "protocol_version": PROTOCOL_VERSION,
                "curator": "",
                # compound_name, compound_class, Bacteria, Type, Method,
                # "MIC [ug/mL]", phase_or_status, "ClinicalTrials.gov ID",
                # mechanism, "Reference genome", Gene, Function, Mutations
                # are intentionally left blank — the curator fills these in
                # after reading the paper. init_candidate_csv defaults
                # verification_status to "pending".
            })
            all_records.append({"target_id": target.id, **rec.__dict__})

    tracker.record_identification(per_target_counts)
    tracker.record_deduplication(len(seen_pmids), dup_count)
    tracker.export_summary()
    tracker.print_flow()

    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "candidates_raw.jsonl", "w") as f:
        for r in all_records:
            f.write(json.dumps(r) + "\n")

    init_candidate_csv(DATA_DIR / "candidates.csv", candidates)

    print(f"\nWrote {len(candidates)} candidates -> data/candidates.csv")
    print("\nNext step: open the CSV, review each row against the inclusion/")
    print("exclusion criteria in protocol.py, fill in the extracted fields, and")
    print("set verification_status to 'verified' or 'rejected'. Then run")
    print("merge_into_db.py to promote verified rows into the published JSON.")


if __name__ == "__main__":
    main()
