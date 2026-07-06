"""
extraction_schema.py
Defines ONE unified candidate-record table (replacing the old two-CSV
compound/mutation split) — matching the exact column layout requested:

  target_id, target_name, compound_name, compound_class, Bacteria, Type,
  Method, MIC [ug/mL], phase_or_status, ClinicalTrials.gov ID, mechanism,
  Reference genome, Gene, Function, Mutations, pmid, doi, citation_text,
  source_query, protocol_version, curator

Three columns are APPENDED beyond that original list: verification_status,
curation_date, curator_notes. These aren't optional extras — they're what
make the "only merge human-verified facts" guarantee in merge_into_db.py
possible at all. Without a verification_status column, there's no way to
distinguish "a curator confirmed this" from "this is an unreviewed search
hit" once everything lives in one flat table. If you want them removed,
say so explicitly — but note that removing verification_status specifically
would mean merge_into_db.py can no longer tell verified from unverified rows,
so it would need a different safeguard in its place, not just deletion.

Column headers are used literally as dict keys (not Python dataclass field
names), since several headers contain spaces/brackets/dots that aren't
valid Python identifiers (e.g. "MIC [ug/mL]", "ClinicalTrials.gov ID").
"""
import csv
from pathlib import Path
from typing import List, Dict

CANDIDATE_FIELDS = [
    "target_id",
    "target_name",
    "compound_name",
    "compound_class",
    "Bacteria",
    "Type",
    "Method",
    "MIC [ug/mL]",
    "phase_or_status",
    "ClinicalTrials.gov ID",
    "mechanism",
    "Reference genome",
    "Gene",
    "Function",
    "Mutations",
    "pmid",
    "doi",
    "citation_text",
    "source_query",
    "protocol_version",
    "curator",
    # Appended for curation integrity — see module docstring above.
    "verification_status",   # "pending" | "verified" | "rejected"
    "curation_date",
    "curator_notes",
]


def init_candidate_csv(path: Path, candidates: List[Dict]):
    """candidates: list of dicts with at least target_id, target_name, pmid,
    doi, citation_text, source_query, protocol_version pre-filled from
    search results. Curator fills in the rest (compound_name, Bacteria,
    Type, Method, MIC, phase_or_status, ClinicalTrials.gov ID, mechanism,
    Reference genome, Gene, Function, Mutations) and sets verification_status
    by hand after reading the paper."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in candidates:
        row = {fn: "" for fn in CANDIDATE_FIELDS}
        row.update(c)
        row["verification_status"] = row.get("verification_status") or "pending"
        rows.append(row)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CANDIDATE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_verified(path: Path) -> List[Dict]:
    """Reads a curated CSV and returns only rows marked verified — this is
    the ONLY function merge_into_db.py should read from."""
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("verification_status", "").strip().lower() == "verified":
                out.append({k: row.get(k, "") for k in CANDIDATE_FIELDS})
    return out
