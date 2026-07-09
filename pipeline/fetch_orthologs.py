"""
fetch_orthologs.py
Scrapes Mycobrowser (mycobrowser.epfl.ch) for the M. smegmatis MC2-155 and
M. abscessus ATCC_19977 ortholog locus tags for every target in protocol.py.

WHY THIS IS A SEPARATE SCRIPT, NOT SOMETHING I RAN FOR YOU:
mycobrowser.epfl.ch is not reachable from my sandbox (network egress is
restricted to a fixed domain allowlist that doesn't include it). I manually
checked 3 targets (DprE1, InhA, MmpL3) directly and confirmed a real
finding: Mycobrowser's "Orthologs" table has NEVER included an M. abscessus
entry for any of those 3 genes, despite M. abscessus ATCC_19977 being one
of their 11 listed genomes. This looks systematic, not a per-gene gap — but
run this script yourself (you have real internet access) to get the
complete, current picture across all 46 targets rather than trust a 3-gene
sample.

WHAT THIS DOES:
For each target's Rv locus, fetches https://mycobrowser.epfl.ch/genes/{locus}
and parses the "Orthologs" table for the "M. smegmatis MC2-155" and
"M. abscessus ATCC_19977" rows, if present.

WHAT THIS DOES NOT DO:
It does not modify protocol.py automatically. It prints/writes a plain
mapping so you can review it and merge confirmed tags into TARGETS'
extra_loci yourself — same "human checks before it's trusted" principle
as the rest of this pipeline.

Usage:
    pip install requests beautifulsoup4
    python3 fetch_orthologs.py

Output:
    orthologs_found.json   {target_id: {"smegmatis": "MSMEG_####" or null,
                                          "abscessus": "MAB_####" or null}}
    Also prints a ready-to-paste Python snippet for confirmed hits.
"""
import json
import time
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from protocol import TARGETS

BASE_URL = "https://mycobrowser.epfl.ch/genes/{locus}"
DELAY_SECONDS = 1.0   # be polite to EPFL's server — this isn't a high-volume API


def fetch_orthologs_table(locus: str) -> dict:
    """Returns {'M. smegmatis MC2-155': 'MSMEG_####', ...} for whatever rows
    Mycobrowser's Orthologs table actually has for this gene."""
    url = BASE_URL.format(locus=locus)
    resp = requests.get(url, timeout=15, headers={"User-Agent": "MycoDiscovery-research-script/1.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    orthologs = {}
    # Find the "Orthologs" heading, then the table that immediately follows it
    heading = soup.find(lambda tag: tag.name in ("h2", "h3", "h4") and "Ortholog" in tag.get_text())
    if not heading:
        return orthologs

    table = heading.find_next("table")
    if not table:
        return orthologs

    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            species = cells[0].get_text(strip=True)
            locus_tag = cells[1].get_text(strip=True)
            orthologs[species] = locus_tag

    return orthologs


def main():
    results = {}
    for target in TARGETS:
        print(f"Fetching {target.id} ({target.gene_locus})...")
        try:
            orthologs = fetch_orthologs_table(target.gene_locus)
        except requests.RequestException as e:
            print(f"  ERROR: {e}")
            orthologs = {}

        smegmatis = next((v for k, v in orthologs.items() if "smegmatis" in k.lower()), None)
        abscessus = next((v for k, v in orthologs.items() if "abscessus" in k.lower()), None)

        results[target.id] = {
            "gene_name": target.gene_name,
            "gene_locus": target.gene_locus,
            "smegmatis": smegmatis,
            "abscessus": abscessus,
            "all_orthologs_found": orthologs,   # full table, in case other species are useful later
        }
        print(f"  smegmatis: {smegmatis or 'NOT FOUND'} | abscessus: {abscessus or 'NOT FOUND'}")
        time.sleep(DELAY_SECONDS)

    Path("orthologs_found.json").write_text(json.dumps(results, indent=2))
    print("\nWrote orthologs_found.json")

    n_smeg = sum(1 for r in results.values() if r["smegmatis"])
    n_absc = sum(1 for r in results.values() if r["abscessus"])
    print(f"\nSummary: {n_smeg}/{len(TARGETS)} targets have a confirmed M. smegmatis tag")
    print(f"         {n_absc}/{len(TARGETS)} targets have a confirmed M. abscessus tag")

    print("\n--- Ready-to-review snippet for confirmed hits (paste into protocol.py by hand) ---")
    for tid, r in results.items():
        loci = [l for l in (r["smegmatis"], r["abscessus"]) if l]
        if loci:
            print(f'# {tid}: extra_loci={loci!r}  (smegmatis={r["smegmatis"]}, abscessus={r["abscessus"]})')


if __name__ == "__main__":
    main()
