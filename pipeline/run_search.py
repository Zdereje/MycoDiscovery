"""
run_search.py
Orchestrates the full systematic search: runs every query in protocol.py
against PubMed, deduplicates, logs everything, and writes curator-ready
CSV templates for the manual verification step.

This does NOT decide what's true. It surfaces candidates. A human curator
reviews every row before anything is trusted (see extraction_schema.py).

Usage:
    export NCBI_EMAIL="you@example.com"
    export NCBI_API_KEY="..."          # optional but recommended
    python3 run_search.py

Outputs:
    data/cache/                        raw esearch/efetch responses (cached)
    data/search_log.jsonl              every query run, with timestamp + count
    data/candidates_raw.jsonl          all fetched PubMed records, tagged by
                                        target + query type
    data/compounds_candidates.csv      curator template for compound review
    data/mutations_candidates.csv      curator template for mutation review
    data/prisma_summary.json           identification-stage PRISMA counts
"""
import json
import os
from pathlib import Path

from protocol import TARGETS, PROTOCOL_VERSION, all_queries
from pubmed_client import PubMedClient
from prisma import PrismaTracker
from extraction_schema import init_compound_csv, init_mutation_csv

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
    seen_pmids = set()
    dup_count = 0

    compound_candidates = []
    mutation_candidates = []

    for target, qtype, query in all_queries():
        pmids = client.search(query, protocol_version=PROTOCOL_VERSION)
        per_target_counts[f"{target.id}:{qtype}"] = len(pmids)

        new_pmids = [p for p in pmids if p not in seen_pmids]
        dup_count += len(pmids) - len(new_pmids)
        seen_pmids.update(new_pmids)

        records = client.fetch_summaries(new_pmids, source_query=query, protocol_version=PROTOCOL_VERSION)
        for rec in records:
            row = {
                "target_id": target.id, "target_name": target.name,
                "pmid": rec.pmid, "doi": rec.doi or "",
                "citation_text": f"{rec.authors}. {rec.title} {rec.journal}. {rec.year}. PMID:{rec.pmid}",
                "source_query": query, "protocol_version": PROTOCOL_VERSION,
                "curator": "", "curation_date": "",
            }
            if qtype == "compound":
                compound_candidates.append({
                    **row, "compound_name": "", "compound_class": "",
                    "phase_or_status": "", "mechanism": "",
                })
            else:
                mutation_candidates.append({
                    **row, "compound_name": "", "gene": target.gene_name,
                    "aa_change": "", "effect": "",
                })
            all_records.append({"target_id": target.id, "query_type": qtype, **rec.__dict__})

    tracker.record_identification(per_target_counts)
    tracker.record_deduplication(len(seen_pmids), dup_count)
    tracker.export_summary()
    tracker.print_flow()

    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "candidates_raw.jsonl", "w") as f:
        for r in all_records:
            f.write(json.dumps(r) + "\n")

    init_compound_csv(DATA_DIR / "compounds_candidates.csv", compound_candidates)
    init_mutation_csv(DATA_DIR / "mutations_candidates.csv", mutation_candidates)

    print(f"\nWrote {len(compound_candidates)} compound candidates -> data/compounds_candidates.csv")
    print(f"Wrote {len(mutation_candidates)} mutation candidates -> data/mutations_candidates.csv")
    print("\nNext step: open both CSVs, review each row against the inclusion/")
    print("exclusion criteria in protocol.py, fill in the extracted fields, and")
    print("set verification_status to 'verified' or 'rejected'. Then run")
    print("merge_into_db.py to promote verified rows into the published JSON.")


if __name__ == "__main__":
    main()
