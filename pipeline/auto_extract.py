"""
auto_extract.py
Lightweight, regex-based auto-extraction from abstract text — runs
automatically inside run_search.py for every fetched paper, so curators
start with a head start instead of a blank row.

IMPORTANT — what this is and isn't:
This is pattern-matching, not reading comprehension. It WILL produce false
positives (e.g. flagging "H37Rv" as a mutation-like token, or picking up a
concentration that isn't actually the compound's MIC) and false negatives
(abstracts that report data in a phrasing these patterns don't anticipate).
Every field it touches gets a note in `auto_extract_notes` saying so.
Nothing here ever sets verification_status — that stays exclusively a
human decision, same as everywhere else in this pipeline.

What it extracts:
  - mic_candidates: numeric value + unit patterns near the word "MIC"
  - mutation_candidates: amino-acid-substitution-shaped tokens (e.g. C387S)
  - is_likely_review: abstract text itself (not just the title) mentions
    "this review" / "we review" / "overview of" etc. — catches cases where
    Publication Type indexing missed it and the title didn't say "review"
"""
import re
from dataclasses import dataclass
from typing import List

MIC_PATTERN = re.compile(
    r'MIC[a-z0-9]*\s*(?:of|was|were|is|:|=|values?)?\s*'
    r'(?:[<>≤≥~]\s*)?'
    r'(\d+\.?\d*(?:\s*[-–to]+\s*\d+\.?\d*)?)\s*'
    r'(µg/mL|ug/mL|μg/mL|mg/L|ng/mL|µM|uM|nM|mM)',
    re.IGNORECASE,
)

# Amino-acid substitution shorthand: letter + 1-4 digits + letter (C387S, Y314C).
# Deliberately permissive — false positives are expected and flagged as such.
MUTATION_PATTERN = re.compile(r'\b([A-Z]\d{1,4}[A-Z])\b')

# Common locus-tag / strain-name false positives to filter out of mutation hits
MUTATION_FALSE_POSITIVES = {
    "H37Rv", "H37Ra", "K562",  # not amino acid substitutions
}

REVIEW_SELF_ID_PATTERNS = re.compile(
    r'\bthis review\b|\bwe review\b|\boverview of\b|\bin this (?:mini-?)?review\b|'
    r'\bsummariz(?:e|es|ed|ing)\b.{0,40}\b(?:literature|studies|advances)\b',
    re.IGNORECASE,
)


@dataclass
class AutoExtractResult:
    mic_candidates: List[str]
    mutation_candidates: List[str]
    is_likely_review: bool
    notes: str


def auto_extract(abstract: str) -> AutoExtractResult:
    if not abstract:
        return AutoExtractResult([], [], False, "No abstract text available to scan.")

    mic_hits = [f"{val.strip()} {unit}" for val, unit in MIC_PATTERN.findall(abstract)]

    raw_mutations = MUTATION_PATTERN.findall(abstract)
    mutation_hits = sorted(set(m for m in raw_mutations if m not in MUTATION_FALSE_POSITIVES))

    is_review = bool(REVIEW_SELF_ID_PATTERNS.search(abstract))

    notes_parts = []
    if mic_hits:
        notes_parts.append(f"AUTO: possible MIC value(s) found: {', '.join(mic_hits)} — verify unit/context, may not be this compound's own MIC.")
    if mutation_hits:
        notes_parts.append(f"AUTO: possible mutation token(s): {', '.join(mutation_hits)} — regex pattern-match only, verify these are real substitutions (not strain names/other codes).")
    if is_review:
        notes_parts.append("AUTO: abstract text itself suggests this is a REVIEW (self-describes as reviewing/summarizing), even if Publication Type or title didn't flag it.")
    if not notes_parts:
        notes_parts.append("AUTO: no MIC/mutation patterns or review self-identification detected in abstract — read manually, absence of a pattern match is not evidence of absence.")

    return AutoExtractResult(
        mic_candidates=mic_hits,
        mutation_candidates=mutation_hits,
        is_likely_review=is_review,
        notes=" | ".join(notes_parts),
    )
