"""
run_search.py
Orchestrates the full systematic search in TWO stages:

  1. Per-target queries — one gene/species/resistance-restricted query per
     TARGET (protocol.py TARGETS), same as before.
  2. Broad query — ONE additional query with NO gene restriction at all
     (protocol.BROAD_QUERY), meant to catch resistance-conferring mutations
     in genes that aren't on the preset target list. Since this is broad,
     it will match far more papers than practical to fetch exhaustively —
     see BROAD_QUERY_RETMAX below. Results are deduplicated against every
     PMID already found in stage 1, so you only review genuinely NEW
     candidates here, not every resistance paper on these species.

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

from protocol import TARGETS, PROTOCOL_VERSION, all_queries, BROAD_QUERY
from pubmed_client import PubMedClient
from prisma import PrismaTracker
from extraction_schema import init_candidate_csv
from auto_extract import auto_extract

DATA_DIR = Path("data")

# Fallback source for the "Function" column when auto-extraction finds
# nothing in the abstract text itself — this is background fact about the
# TARGET (not something extracted from this specific paper), so it's safe
# to always fill from here. Looks for the published JSON at the
# conventional repo path (../data/ relative to pipeline/); falls back to
# an empty map (Function stays blank) if not found, rather than erroring.
def _load_function_map() -> dict:
    candidate_paths = [
        Path("../data/mycodiscovery_targets_v1.json"),
        Path("data/mycodiscovery_targets_v1.json"),
    ]
    for p in candidate_paths:
        if p.exists():
            db = json.loads(p.read_text())
            return {
                t["id"]: t["function"]
                for cat in db["categories"] for t in cat["targets"]
            }
    print("NOTE: mycodiscovery_targets_v1.json not found at expected paths — "
          "Function column will only be filled where auto-extraction finds "
          "something directly in the abstract, not from target metadata.")
    return {}


FUNCTION_MAP = _load_function_map()

# How many broad-query results to actually fetch full details for. PubMed's
# TOTAL hit count for this query will almost certainly be far larger — the
# script reports that total so you can see how much is being left unfetched,
# rather than silently pretending this is exhaustive. Raise this if you want
# more coverage, but curating thousands of rows by hand isn't realistic —
# treat the broad query as a supplementary discovery mechanism, not a
# substitute for the targeted per-gene searches.
BROAD_QUERY_RETMAX = 500


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
    candidates = []

    for target, query in all_queries():
        pmids = client.search(query, protocol_version=PROTOCOL_VERSION)
        per_target_counts[target.id] = len(pmids)

        new_pmids = [p for p in pmids if p not in seen_pmids]
        dup_count += len(pmids) - len(new_pmids)
        seen_pmids.update(new_pmids)

        records = client.fetch_summaries(new_pmids, source_query=query, protocol_version=PROTOCOL_VERSION)
        for rec in records:
            extracted = auto_extract(rec.abstract, species_hint="")
            candidates.append({
                "target_id": target.id,
                "target_name": target.name,
                "compound_name": extracted.compound_name,
                "compound_class": extracted.compound_class,
                "Bacteria": extracted.bacteria,
                "Method": extracted.method,
                "MIC [ug/mL]": extracted.mic,
                "phase_or_status": extracted.phase_or_status,
                "ClinicalTrials.gov ID": extracted.clinicaltrials_id,
                "mechanism": extracted.mechanism,
                # Gene/Function fall back to the KNOWN target identity (from
                # protocol.py) when auto-extraction finds nothing in the
                # abstract text — this is background fact about the target,
                # not an extraction, so it's safe to always fill.
                "Gene": extracted.gene or target.gene_name,
                "Function": extracted.function or FUNCTION_MAP.get(target.id, ""),
                "Mutations": extracted.mutations,
                "pmid": rec.pmid,
                "doi": rec.doi or "",
                "citation_text": f"{rec.authors}. {rec.title} {rec.journal}. {rec.year}. PMID:{rec.pmid}",
                "abstract": rec.abstract,
                "auto_extract_notes": extracted.notes,
                "source_query": query,
                "protocol_version": PROTOCOL_VERSION,
                "curator": "",
                # Type, "Reference genome" still intentionally blank — no
                # reliable auto-extraction signal for these yet.
                # verification_status still defaults to "pending" in
                # init_candidate_csv — auto-filled fields are NOT auto-verified.
            })
            all_records.append({"target_id": target.id, **rec.__dict__})

    tracker.record_identification(per_target_counts)
    tracker.record_deduplication(len(seen_pmids), dup_count)

    # ── STAGE 2: broad, gene-unrestricted query ─────────────────────
    # Finds resistance-mutation papers for genes NOT in TARGETS at all.
    # Deduplicated against everything stage 1 already found — only
    # genuinely new PMIDs get fetched and added to the CSV.
    print(f"\nRunning broad query (gene-unrestricted, retmax={BROAD_QUERY_RETMAX})...")
    broad_pmids, broad_total = client.search_with_count(
        BROAD_QUERY, protocol_version=PROTOCOL_VERSION, retmax=BROAD_QUERY_RETMAX
    )
    print(f"PubMed reports {broad_total} total matching papers for the broad query.")
    print(f"Fetched the top {len(broad_pmids)} (by relevance) to check against target-based results.")

    new_from_broad = [p for p in broad_pmids if p not in seen_pmids]
    already_found_by_targets = len(broad_pmids) - len(new_from_broad)
    print(f"{already_found_by_targets} of those were already found by a per-target query (skipped).")
    print(f"{len(new_from_broad)} are genuinely new — not caught by any preset target's query.")

    broad_records = client.fetch_summaries(new_from_broad, source_query=BROAD_QUERY, protocol_version=PROTOCOL_VERSION)
    for rec in broad_records:
        extracted = auto_extract(rec.abstract)
        candidates.append({
            "target_id": "unlisted",
            "target_name": "NOT on preset target list — identify gene/target from paper during curation",
            "compound_name": extracted.compound_name,
            "compound_class": extracted.compound_class,
            "Bacteria": extracted.bacteria,
            "Method": extracted.method,
            "MIC [ug/mL]": extracted.mic,
            "phase_or_status": extracted.phase_or_status,
            "ClinicalTrials.gov ID": extracted.clinicaltrials_id,
            "mechanism": extracted.mechanism,
            # No target fallback here (this is the gene-UNRESTRICTED query,
            # by design there's no preset target to fall back to) — Gene/
            # Function only fill when auto-extraction actually found
            # something in the abstract text itself.
            "Gene": extracted.gene,
            "Function": extracted.function,
            "Mutations": extracted.mutations,
            "pmid": rec.pmid,
            "doi": rec.doi or "",
            "citation_text": f"{rec.authors}. {rec.title} {rec.journal}. {rec.year}. PMID:{rec.pmid}",
            "abstract": rec.abstract,
            "auto_extract_notes": extracted.notes,
            "source_query": f"[broad] {BROAD_QUERY}",
            "protocol_version": PROTOCOL_VERSION,
            "curator": "",
        })
        all_records.append({"target_id": "unlisted", "query_label": "broad", **rec.__dict__})

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
