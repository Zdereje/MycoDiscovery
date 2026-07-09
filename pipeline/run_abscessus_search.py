"""
run_abscessus_search.py
A dedicated search for a distinct research question from the main
target-gene pipeline: comprehensively find M. abscessus resistance
mutations for ANY compound (approved or early-discovery), to build a
resource for predicting cross-resistance in drug discovery.

Why this is a separate script rather than folded into run_search.py:
run_search.py answers "what compounds/mutations exist for these 46 preset
targets" — necessarily incomplete for a target not on that list.
This script answers a different question: "what resistance mutations has
anyone ever reported in M. abscessus, regardless of target" — comprehensive
by design, at the cost of needing more curation afterward since it's not
pre-sorted by target.

Recall over precision: no gene restriction at all. The Publication Type
exclusion still applies (protocol.ABSCESSUS_QUERY), but expect some
reviews to still get through — that's what auto_extract.py's
is_likely_review flag is for; it's a downstream triage aid, not a
recall-reducing filter.

Usage:
    export NCBI_EMAIL="you@example.com"
    export NCBI_API_KEY="..."          # optional but recommended
    python3 run_abscessus_search.py

Outputs:
    data/abscessus_search_log.jsonl        every query run, timestamp, count
    data/abscessus_candidates_raw.jsonl    all fetched PubMed records
    data/abscessus_candidates.csv          curator template (same schema as candidates.csv)
    data/abscessus_prisma_summary.json     PRISMA identification-stage counts
"""
import json
import os
from pathlib import Path

from protocol import PROTOCOL_VERSION
from abscessus_protocol import ABSCESSUS_QUERY
from pubmed_client import PubMedClient
from prisma import PrismaTracker
from extraction_schema import init_candidate_csv
from auto_extract import auto_extract

DATA_DIR = Path("data")

# Single-species, gene-unrestricted queries can still return a lot —
# comprehensiveness is the whole point here, so this is set generously.
# PubMed's TOTAL count is reported regardless, so you always know how much
# (if anything) was left un-fetched beyond this cap.
ABSCESSUS_RETMAX = 2000


def main():
    email = os.environ.get("NCBI_EMAIL")
    if not email:
        raise SystemExit(
            "Set NCBI_EMAIL before running. e.g.:\n    export NCBI_EMAIL='you@example.com'"
        )

    client = PubMedClient(email=email)
    tracker = PrismaTracker()

    print(f"Query:\n  {ABSCESSUS_QUERY}\n")
    print(f"Running (retmax={ABSCESSUS_RETMAX})...")
    pmids, total = client.search_with_count(
        ABSCESSUS_QUERY, protocol_version=PROTOCOL_VERSION, retmax=ABSCESSUS_RETMAX
    )
    print(f"PubMed reports {total} total matching papers.")
    print(f"Fetching the top {len(pmids)} (by relevance)...")
    if total > ABSCESSUS_RETMAX:
        print(f"NOTE: {total - ABSCESSUS_RETMAX} papers exist beyond what was fetched — "
              f"raise ABSCESSUS_RETMAX if you need full coverage, but curating "
              f"{total} rows by hand is a lot; consider whether relevance-ranked "
              f"top-{ABSCESSUS_RETMAX} is a reasonable working set first.")

    tracker.record_identification({"abscessus_resistance": total})
    tracker.record_deduplication(len(pmids), 0)
    tracker.export_summary(DATA_DIR / "abscessus_prisma_summary.json")
    tracker.print_flow()

    records = client.fetch_summaries(pmids, source_query=ABSCESSUS_QUERY, protocol_version=PROTOCOL_VERSION)

    candidates = []
    all_records = []
    n_flagged_review = 0
    for rec in records:
        extracted = auto_extract(rec.abstract, species_hint="Mycobacterium abscessus")
        if extracted.is_likely_review:
            n_flagged_review += 1
        candidates.append({
            "target_id": "abscessus_broad",
            "target_name": "M. abscessus cross-resistance search — identify specific gene/target during curation",
            "compound_name": extracted.compound_name,
            "compound_class": extracted.compound_class,
            "Bacteria": extracted.bacteria,  # always at least "Mycobacterium abscessus" via species_hint
            "Method": extracted.method,
            "MIC [ug/mL]": extracted.mic,
            "phase_or_status": extracted.phase_or_status,
            "ClinicalTrials.gov ID": extracted.clinicaltrials_id,
            "mechanism": extracted.mechanism,
            "Gene": extracted.gene,
            "Function": extracted.function,
            "Mutations": extracted.mutations,
            "pmid": rec.pmid,
            "doi": rec.doi or "",
            "citation_text": f"{rec.authors}. {rec.title} {rec.journal}. {rec.year}. PMID:{rec.pmid}",
            "abstract": rec.abstract,
            "auto_extract_notes": extracted.notes,
            "source_query": ABSCESSUS_QUERY,
            "protocol_version": PROTOCOL_VERSION,
            "curator": "",
        })
        all_records.append({"pmid": rec.pmid, **rec.__dict__})

    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / "abscessus_candidates_raw.jsonl", "w") as f:
        for r in all_records:
            f.write(json.dumps(r) + "\n")

    init_candidate_csv(DATA_DIR / "abscessus_candidates.csv", candidates)

    print(f"\nWrote {len(candidates)} candidates -> data/abscessus_candidates.csv")
    print(f"Of these, {n_flagged_review} were auto-flagged as likely reviews based on abstract "
          f"self-description (Publication Type alone didn't catch them) — check "
          f"auto_extract_notes column, these are good fast-reject candidates.")
    print("\nNext: curate as usual — read abstract + auto_extract_notes columns, fill in")
    print("compound_name/Gene/mechanism/Mutations, set verification_status.")


if __name__ == "__main__":
    main()
