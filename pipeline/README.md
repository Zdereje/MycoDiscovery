# MycoDiscovery Systematic Search Pipeline

A reproducible, PRISMA-style literature search pipeline for populating the
target-first MycoDiscovery Target Explorer database — built so the methodology
can be described and cited in a publication, not just "we searched PubMed."

**v2.0.0:** one combined, multi-species query per target (*M. tuberculosis*,
*M. abscessus*, *M. avium*, *M. kansasii*, *M. smegmatis*), writing to a
single unified `candidates.csv` — replaced the earlier two-query/two-CSV
(compound + mutation) design, which had a cross-query deduplication bug
(see `protocol.py`'s module docstring for details).

## Why this exists

The earlier `build_target_centric.py` script hardcoded compound/mutation
data I found via ad hoc web searches directly into Python dictionaries.
That's fine for a demo, but it has no audit trail: no record of what was
searched, when, by what exact query, or who verified each fact. This
pipeline replaces that with a documented protocol and provenance chain
suitable for a methods section.

## Pipeline stages

```
protocol.py          Pre-specified, multi-species search query per target +
                      inclusion/exclusion criteria (defined BEFORE
                      screening — standard systematic-review practice)
        |
        v
pubmed_client.py      Runs every query against NCBI PubMed (E-utilities),
                      rate-limited, cached, and logged
        |
        v
run_search.py         Orchestrates the full search, deduplicates hits,
                      writes ONE curator-ready CSV (candidates.csv) + PRISMA counts
        |
        v
   [ HUMAN CURATION — you review each CSV row against the criteria
     in protocol.py and mark verification_status: verified/rejected ]
        |
        v
merge_into_db.py       Promotes ONLY verified rows into the published JSON,
                      preserving PMID/DOI/curator/date on every record
```

Nothing is trusted or published without a human explicitly marking it
`verified` in the CSV. The pipeline surfaces candidates; it does not decide
what's true.

## Setup

```bash
pip install biopython
export NCBI_EMAIL="you@example.com"     # required by NCBI usage policy
export NCBI_API_KEY="..."               # optional — raises rate limit 3/s -> 10/s
```

Get a free API key at https://www.ncbi.nlm.nih.gov/account/settings/ (under
"API Key Management") — takes two minutes and is worth doing before a full
46-target run (92 queries), since it cuts total run time significantly.

**Note on this sandbox:** `eutils.ncbi.nlm.nih.gov` is not in this
environment's allowed network domains, so I couldn't execute `run_search.py`
live here (confirmed: returns HTTP 403 through the egress proxy). I validated
every module's logic with mock data instead (see the merge test in our
conversation). Run this pipeline on a machine with normal internet access —
your own laptop, a server, or wherever you'll be doing the curation work
anyway.

## Running it

```bash
python3 run_search.py
```

This produces:
- `data/search_log.jsonl` — every query, timestamp, and result count (your PRISMA "Identification" data)
- `data/candidates_raw.jsonl` — full raw records (title/abstract/journal/year/DOI) for every hit
- `data/candidates.csv` — one row per candidate paper per target, ready for you to fill in and verify
- `data/prisma_summary.json` — identification/deduplication counts

## Curating

Open both CSVs. For each row:
1. Read the paper (PMID/DOI given)
2. Check it against `INCLUSION_CRITERIA` / `EXCLUSION_CRITERIA` in `protocol.py`
3. Fill in the extracted fields (compound_name, class, mechanism / gene, aa_change, effect)
4. Set `verification_status` to `verified` or `rejected`
5. Use `curator_notes` for any judgment call a second reviewer might question

## Merging into the published database

```bash
python3 merge_into_db.py \
    --json mycodiscovery_targets_v1.json \
    --candidates data/candidates.csv \
    --out mycodiscovery_targets_v2.json
```

Rerun this any time you've curated more rows — it's idempotent and rebuilds
each target's compound/mutation list from the current CSV state.

## Extending the protocol

- **New target discovered later?** Add a `Target(...)` entry to `TARGETS` in `protocol.py`, bump `PROTOCOL_VERSION`.
- **New source (PMC full text, bioRxiv)?** Add a new client module following `pubmed_client.py`'s pattern (log everything, cache everything, never auto-merge).
- **Periodic re-runs:** Since search results change as new papers publish, rerun `run_search.py` periodically (e.g. quarterly). The cache means you'll only pay the NCBI query cost for genuinely new results each time — Biopython/Entrez will return the same PMIDs for old queries from cache, and only new PMIDs trigger fresh `efetch` calls.

## For your methods section

You now have, for every published fact in MycoDiscovery:
- The exact search string that found it (`source_query`)
- The protocol version that generated that string (`protocol_version`)
- PMID and DOI
- Who curated it and when
- The pre-specified inclusion/exclusion criteria it was checked against

That's the provenance chain a peer reviewer will expect to see for a
literature-curated database.
