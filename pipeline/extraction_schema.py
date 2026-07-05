"""
extraction_schema.py
Defines the CURATED record formats — what a human curator fills in after
reading a candidate paper — and CSV I/O for that curation step.

Why a separate CSV step instead of extracting straight into JSON:
  - Curation is inherently manual/judgment-based (deciding whether a paper's
    mutation claim is well-supported, matching gene nomenclature, etc.).
    A flat CSV is the easiest format for a human (or a second reviewer) to
    open in Excel/Sheets, review, and mark verified/rejected.
  - Keeping raw-candidate -> curated-CSV -> published-JSON as three distinct
    stages means you always know, for any published record, exactly which
    paper it came from, who curated it, and when — the provenance chain a
    reviewer or reader will ask about.

Two CSV files, matching the two query types in protocol.py:
  compounds_candidates.csv   — one row per (target, compound) candidate
  mutations_candidates.csv   — one row per (target, compound, mutation) candidate

Curator workflow:
  1. Run run_search.py -> produces data/candidates_raw.jsonl (all PubMed hits)
  2. Curator manually reads abstracts/full text, fills in the CSV templates
     below (init_compound_csv / init_mutation_csv give you the header row
     pre-filled with candidate PMIDs to review)
  3. Set `verification_status` to "verified" or "rejected" per row, with
     `curator_notes` explaining any judgment call
  4. Run merge_into_db.py -> only "verified" rows get merged into
     mycodiscovery_targets_v1.json
"""
import csv
from dataclasses import dataclass, fields
from pathlib import Path
from typing import List


@dataclass
class CompoundCandidate:
    target_id: str
    target_name: str
    compound_name: str
    compound_class: str
    phase_or_status: str
    mechanism: str
    pmid: str
    doi: str
    citation_text: str          # full formatted citation, e.g. "Author A et al., Journal. Year;Vol(Issue):Pages."
    source_query: str           # exact query string that surfaced this candidate
    protocol_version: str
    curator: str
    curation_date: str
    verification_status: str    # "pending" | "verified" | "rejected"
    curator_notes: str


@dataclass
class MutationCandidate:
    target_id: str
    compound_name: str
    gene: str
    aa_change: str
    effect: str
    pmid: str
    doi: str
    citation_text: str
    source_query: str
    protocol_version: str
    curator: str
    curation_date: str
    verification_status: str
    curator_notes: str


def _write_csv(path: Path, rows: List[dict], fieldnames: List[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def init_compound_csv(path: Path, candidates: List[dict]):
    """candidates: list of dicts with at least target_id, target_name, pmid,
    doi, citation_text, source_query, protocol_version pre-filled from search
    results. Curator fills in compound_name/class/phase/mechanism and sets
    verification_status by hand."""
    fieldnames = [f.name for f in fields(CompoundCandidate)]
    rows = []
    for c in candidates:
        row = {fn: "" for fn in fieldnames}
        row.update(c)
        row["verification_status"] = row.get("verification_status") or "pending"
        rows.append(row)
    _write_csv(path, rows, fieldnames)


def init_mutation_csv(path: Path, candidates: List[dict]):
    """Same idea as init_compound_csv, for the mutation-query candidates."""
    fieldnames = [f.name for f in fields(MutationCandidate)]
    rows = []
    for c in candidates:
        row = {fn: "" for fn in fieldnames}
        row.update(c)
        row["verification_status"] = row.get("verification_status") or "pending"
        rows.append(row)
    _write_csv(path, rows, fieldnames)


def read_verified(path: Path, schema) -> List[dict]:
    """Reads a curated CSV and returns only rows marked verified — this is
    the ONLY function merge_into_db.py should read from."""
    fieldnames = {f.name for f in fields(schema)}
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("verification_status", "").strip().lower() == "verified":
                out.append({k: v for k, v in row.items() if k in fieldnames})
    return out
