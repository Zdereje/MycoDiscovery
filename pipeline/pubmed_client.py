"""
pubmed_client.py
Thin, well-behaved wrapper around NCBI E-utilities (via Biopython's Bio.Entrez)
for the MycoMUT systematic search.

Design goals (all driven by "this needs to survive peer review"):
  1. Every single query is logged with: exact query string, timestamp,
     PMID count returned, and the protocol version that generated it.
     -> This is your audit trail / PRISMA "Identification" stage data.
  2. Rate-limited to NCBI's published limits (3 req/s without an API key,
     10 req/s with one) so you don't get temporarily blocked.
  3. Caches every raw response to disk (data/cache/) so re-running the
     pipeline doesn't re-hit NCBI for queries you already ran, and so you
     have a permanent local copy of exactly what NCBI returned on the date
     you ran it (searches are NOT static — rerunning next year will find
     new papers, which is expected and fine, but you want to know what you
     had on record when you published).
  4. NEVER auto-merges results into the trusted database. This module only
     retrieves and logs candidate records. A human curator reviews every
     candidate before it's promoted into mycomut_targets_v1.json — see
     extraction_schema.py and merge_into_db.py.

Setup:
    pip install biopython
    export NCBI_EMAIL="you@example.com"        # required by NCBI's usage policy
    export NCBI_API_KEY="..."                  # optional, raises rate limit to 10/s

Usage:
    from pubmed_client import PubMedClient
    client = PubMedClient(email="you@example.com")
    pmids = client.search("dprE1 AND resistance", protocol_version="1.0.0")
    records = client.fetch_summaries(pmids)
"""
import json
import os
import time
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

try:
    from Bio import Entrez
except ImportError as e:
    raise ImportError(
        "Biopython is required: pip install biopython"
    ) from e

CACHE_DIR = Path("data/cache")
LOG_PATH = Path("data/search_log.jsonl")


@dataclass
class PubMedRecord:
    pmid: str
    title: str
    journal: str
    year: str
    doi: Optional[str]
    authors: str
    abstract: str
    retrieved_at: str
    source_query: str
    protocol_version: str


class PubMedClient:
    def __init__(self, email: str, api_key: Optional[str] = None, cache_dir: Path = CACHE_DIR):
        if not email:
            raise ValueError(
                "NCBI requires a contact email for all E-utilities requests. "
                "Pass email='you@example.com' or set NCBI_EMAIL."
            )
        Entrez.email = email
        self.api_key = api_key or os.environ.get("NCBI_API_KEY")
        if self.api_key:
            Entrez.api_key = self.api_key
        self.min_interval = 1.0 / 10 if self.api_key else 1.0 / 3
        self._last_call = 0.0
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ── rate limiting ────────────────────────────────────────────────
    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.time()

    # ── caching ──────────────────────────────────────────────────────
    def _cache_key(self, name: str) -> Path:
        h = hashlib.sha256(name.encode()).hexdigest()[:20]
        return self.cache_dir / f"{h}.json"

    def _log(self, event: dict):
        event["logged_at"] = datetime.now(timezone.utc).isoformat()
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(event) + "\n")

    # ── search (esearch) ─────────────────────────────────────────────
    def search(self, query: str, protocol_version: str, retmax: int = 200,
               use_cache: bool = True) -> List[str]:
        """Returns list of PMIDs for a query. Logs the exact query + count
        for the PRISMA identification-stage record, every time — cache hit
        or not."""
        cache_file = self._cache_key("esearch:" + query)
        if use_cache and cache_file.exists():
            pmids = json.loads(cache_file.read_text())["pmids"]
            self._log({
                "stage": "esearch", "query": query, "protocol_version": protocol_version,
                "n_results": len(pmids), "cache_hit": True,
            })
            return pmids

        self._throttle()
        handle = Entrez.esearch(db="pubmed", term=query, retmax=retmax, sort="relevance")
        result = Entrez.read(handle)
        handle.close()
        pmids = list(result.get("IdList", []))

        cache_file.write_text(json.dumps({"query": query, "pmids": pmids}))
        self._log({
            "stage": "esearch", "query": query, "protocol_version": protocol_version,
            "n_results": len(pmids), "cache_hit": False,
        })
        return pmids

    # ── fetch details (efetch) ──────────────────────────────────────
    def fetch_summaries(self, pmids: List[str], source_query: str = "",
                         protocol_version: str = "", use_cache: bool = True) -> List[PubMedRecord]:
        """Fetches title/abstract/journal/year/authors/DOI for a list of PMIDs.
        Batches in groups of 50 (NCBI-recommended batch size)."""
        records: List[PubMedRecord] = []
        uncached = []
        for pmid in pmids:
            cache_file = self._cache_key("efetch:" + pmid)
            if use_cache and cache_file.exists():
                data = json.loads(cache_file.read_text())
                records.append(PubMedRecord(**data))
            else:
                uncached.append(pmid)

        for i in range(0, len(uncached), 50):
            batch = uncached[i:i + 50]
            self._throttle()
            handle = Entrez.efetch(db="pubmed", id=",".join(batch), rettype="abstract", retmode="xml")
            result = Entrez.read(handle)
            handle.close()

            for article in result.get("PubmedArticle", []):
                rec = self._parse_article(article, source_query, protocol_version)
                cache_file = self._cache_key("efetch:" + rec.pmid)
                cache_file.write_text(json.dumps(asdict(rec)))
                records.append(rec)

        self._log({
            "stage": "efetch", "n_requested": len(pmids),
            "n_fetched_fresh": len(uncached), "protocol_version": protocol_version,
        })
        return records

    @staticmethod
    def _parse_article(article, source_query: str, protocol_version: str) -> PubMedRecord:
        medline = article["MedlineCitation"]
        pmid = str(medline["PMID"])
        art = medline["Article"]
        title = str(art.get("ArticleTitle", ""))
        journal = str(art.get("Journal", {}).get("Title", ""))
        year = ""
        try:
            year = str(art["Journal"]["JournalIssue"]["PubDate"].get("Year", ""))
        except (KeyError, TypeError):
            pass
        abstract_parts = art.get("Abstract", {}).get("AbstractText", [])
        abstract = " ".join(str(p) for p in abstract_parts)
        authors = ", ".join(
            f"{a.get('LastName', '')} {a.get('Initials', '')}".strip()
            for a in art.get("AuthorList", []) if "LastName" in a
        )
        doi = None
        for eid in article.get("PubmedData", {}).get("ArticleIdList", []):
            if eid.attributes.get("IdType") == "doi":
                doi = str(eid)
        return PubMedRecord(
            pmid=pmid, title=title, journal=journal, year=year, doi=doi,
            authors=authors, abstract=abstract,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            source_query=source_query, protocol_version=protocol_version,
        )
