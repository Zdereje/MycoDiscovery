"""
abscessus_protocol.py
A separate, dedicated search definition for a distinct research question
from the main target-gene protocol (protocol.py): comprehensively find
resistance mutations in Mycobacterium abscessus specifically, for ANY
compound (approved drugs and early-discovery molecules alike) — not
restricted to the 46 preset target genes in protocol.py.

Why this is its own file rather than living in protocol.py:
protocol.py's TARGETS/SPECIES/BROAD_QUERY answer "what's known for these 46
preset targets." This file answers a genuinely different question —
"what M. abscessus resistance mutations has anyone ever reported, for any
compound" — used to build a resource for predicting cross-resistance in
drug discovery. Recall matters more than precision here, so there's no
gene restriction at all.

The only thing shared with protocol.py is the Publication Type exclusion
list (protocol.EXCLUDED_PUBLICATION_TYPES / protocol._exclusion_clause) —
reused directly rather than duplicated, so both files stay in sync if that
exclusion list is ever updated.

Used by: run_abscessus_search.py
"""
from typing import List

from protocol import _exclusion_clause, PROTOCOL_VERSION as _BASE_PROTOCOL_VERSION

ABSCESSUS_PROTOCOL_VERSION = "1.0.0"
ABSCESSUS_PROTOCOL_DATE = "2026-07-05"

ABSCESSUS_SPECIES = ["Mycobacterium abscessus"]
ABSCESSUS_RESISTANCE_TERMS = ["resistance", "resistant", "mutation", "mutants"]


def build_abscessus_query(species: List[str], resistance_terms: List[str]) -> str:
    species_clause = " OR ".join(f'"{s}"' for s in species)
    resistance_clause = " OR ".join(f'"{r}"' for r in resistance_terms)
    return f'(({species_clause}) AND ({resistance_clause})) NOT ({_exclusion_clause()})'


ABSCESSUS_QUERY = build_abscessus_query(ABSCESSUS_SPECIES, ABSCESSUS_RESISTANCE_TERMS)


if __name__ == "__main__":
    print(f"M. abscessus cross-resistance protocol v{ABSCESSUS_PROTOCOL_VERSION} ({ABSCESSUS_PROTOCOL_DATE})")
    print(f"(Reuses Publication Type exclusion from main protocol.py v{_BASE_PROTOCOL_VERSION})")
    print(f"\nQuery:\n  {ABSCESSUS_QUERY}")
