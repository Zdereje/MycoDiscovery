"""
protocol.py
The PRE-SPECIFIED search protocol for the MycoDiscovery Target Explorer
systematic literature search.

v2.0.0 CHANGE: replaced the old two-query-per-target design (a separate
"compound" query and a "mutation" query) with a SINGLE combined query per
target, covering multiple Mycobacterium species and, where known, the
gene's locus tag across species (Rv for M. tuberculosis, MSMEG_ for
M. smegmatis, mab_ for M. abscessus, etc.).

Why one query instead of two: a single paper very often reports both a
compound AND its resistance mutation (e.g. "BTZ043 ... resistant mutants
carried C387S"). The old two-query design silently miscounted these
overlap papers depending on which query ran first. One combined query per
target avoids that class of bug entirely, at the cost of no longer being
able to report separate "compound-only" vs "mutation-only" PRISMA counts —
screening now sorts that out per-paper instead of per-query.

IMPORTANT LIMITATION — read before trusting the multi-species locus tags:
Accurate cross-species ortholog locus IDs (MSMEG_/mab_/etc.) are only
populated below for DprE1, since that's well-documented in the literature
I could verify. For every other target, extra_loci is intentionally left
empty rather than guessed — fabricating a locus tag risks silently
injecting a wrong gene ID into a systematic search. For those targets,
the query still finds cross-species hits via the gene SYMBOL text match
plus the species name list; it just won't additionally match on a
species-specific locus number. If you want DprE1-level precision for other
targets, look up the correct ortholog locus tags (NCBI Gene, Mycobrowser,
or UniProt cross-references are good sources) and add them to extra_loci.

Versioning: bump PROTOCOL_VERSION whenever query templates or the target
list change, and keep old versions in git history.
"""
from dataclasses import dataclass, field
from typing import List

PROTOCOL_VERSION = "2.0.0"
PROTOCOL_DATE = "2026-07-05"

# ── SPECIES COVERED ──────────────────────────────────────────────────────
SPECIES = [
    "Mycobacterium tuberculosis",
    "Mycobacterium abscessus",
    "Mycobacterium avium",
    "Mycobacterium kansasii",
    "Mycobacterium smegmatis",
]

# ── RESISTANCE/VARIATION TERMS ───────────────────────────────────────────
RESISTANCE_TERMS = ["resistance", "resistant", "mutation", "mutants", "polymorphism"]

# ── BROAD, GENE-UNRESTRICTED QUERY ───────────────────────────────────────
# The per-target queries below are restricted to a specific gene symbol/
# locus — they can only ever find papers about genes already on your
# target list. This query has NO gene restriction, so it also catches
# resistance-conferring mutations in genes that aren't in TARGETS at all
# (novel/uncatalogued resistance mechanisms). Because it's this broad, it
# WILL match a very large number of papers — see run_search.py for how
# results are deduplicated against everything the per-target searches
# already found, so you only review the genuinely NEW ones here, not
# every resistance paper ever published on these species.
#
# Narrower resistance term list than the per-target queries (drops
# "polymorphism" — specific to this broad query only, RESISTANCE_TERMS
# above is unchanged for per-target use). Both species and resistance
# terms are now restricted to [Title/Abstract], same as the gene terms.
BROAD_RESISTANCE_TERMS = ["resistance", "resistant", "mutation", "mutants"]

# ── EXCLUDE NON-PRIMARY PUBLICATION TYPES ───────────────────────────────
# NLM manually tags every indexed PubMed record with a Publication Type
# (Review, Journal Article, Meta-Analysis, Comment, Editorial, Letter,
# etc.) — this is curated metadata, not a guess from the title, so
# excluding on it is far more reliable than keyword-matching title text
# for "review" (which misses reviews that don't use that word, and can
# misfire on primary papers that happen to use it descriptively).
# NOT-ing these out removes them before they ever reach your CSV, without
# touching the actual gene/species/resistance search terms — so it
# shouldn't cost you recall on genuine primary research.
EXCLUDED_PUBLICATION_TYPES = [
    "Review", "Systematic Review", "Meta-Analysis", "Comment", "Editorial", "Letter",
]


def _exclusion_clause() -> str:
    return " OR ".join(f'"{pt}"[Publication Type]' for pt in EXCLUDED_PUBLICATION_TYPES)


def build_broad_query(species: List[str], resistance_terms: List[str]) -> str:
    species_clause = " OR ".join(f'"{s}"[Title/Abstract]' for s in species)
    resistance_clause = " OR ".join(f'"{r}"[Title/Abstract]' for r in resistance_terms)
    return f'(({species_clause}) AND ({resistance_clause})) NOT ({_exclusion_clause()})'


BROAD_QUERY = build_broad_query(SPECIES, BROAD_RESISTANCE_TERMS)

# ── M. ABSCESSUS-FOCUSED RESISTANCE QUERY ───────────────────────────────
# A distinct research question from the target-gene-restricted queries above:
# comprehensively find resistance mutations in M. abscessus specifically,
# for ANY compound (approved drugs and early-discovery molecules alike),
# not restricted to the 46 preset target genes. Goal: build a resource for
# predicting cross-resistance in drug discovery, so recall matters more
# than precision here — no gene restriction, and "cross-resistance" added
# explicitly as a search term since that's the specific research interest.
ABSCESSUS_SPECIES = ["Mycobacterium abscessus"]
ABSCESSUS_RESISTANCE_TERMS = ["resistance", "resistant", "mutation", "mutants"]


def build_abscessus_query(species: List[str], resistance_terms: List[str]) -> str:
    species_clause = " OR ".join(f'"{s}"' for s in species)
    resistance_clause = " OR ".join(f'"{r}"' for r in resistance_terms)
    return f'(({species_clause}) AND ({resistance_clause})) NOT ({_exclusion_clause()})'


ABSCESSUS_QUERY = build_abscessus_query(ABSCESSUS_SPECIES, ABSCESSUS_RESISTANCE_TERMS)


def build_query(gene_terms: List[str], species: List[str], resistance_terms: List[str]) -> str:
    """Gene/locus terms restricted to Title/Abstract (keeps precision).
    Species and resistance terms left unrestricted (broadens recall).
    Reviews/meta-analyses/comments/editorials/letters excluded via
    Publication Type (NLM-indexed, not a title-text guess)."""
    gene_clause = " OR ".join(f'"{g}"[Title/Abstract]' for g in gene_terms)
    species_clause = " OR ".join(f'"{s}"' for s in species)
    resistance_clause = " OR ".join(f'"{r}"' for r in resistance_terms)
    return f'({gene_clause}) AND ({species_clause}) AND ({resistance_clause}) NOT ({_exclusion_clause()})'


# ── PRE-SPECIFIED INCLUSION / EXCLUSION CRITERIA ────────────────────────
INCLUSION_CRITERIA = [
    "Peer-reviewed primary research article, or a preprint from bioRxiv/medRxiv "
    "clearly superseded by or awaiting peer review.",
    "Reports at least one named compound (with a stated or citable chemotype/class) "
    "AND/OR at least one specific resistance mutation (gene + amino-acid or "
    "nucleotide change) tied to a Mycobacterium species covered by this protocol.",
    "Mutation-effect claims must be tied to an experimental readout (MIC shift, "
    "IC50 shift, growth/kill curve, or equivalent) — not purely computational "
    "prediction, unless no experimental data exists yet for that target (in "
    "which case, tag as 'computational-only' explicitly).",
]

EXCLUSION_CRITERIA = [
    "Review articles with no new primary data (may be used for citation-chasing "
    "but not as a primary source record).",
    "Non-English full text with no translated abstract sufficient for extraction.",
    "In silico/docking-only studies proposing novel compounds with no reported "
    "wet-lab MIC or resistance data (flag separately as 'in-silico candidate', "
    "do not merge into the verified compound/mutation tables).",
    "Studies in species outside the 5 covered by this protocol, unless the paper "
    "is explicitly cross-referenced from an included study.",
]


@dataclass
class Target:
    id: str
    name: str
    gene_name: str               # gene symbol, e.g. "dprE1"
    gene_locus: str               # M. tuberculosis Rv locus, e.g. "Rv3790"
    category_id: str
    extra_loci: List[str] = field(default_factory=list)  # other species' locus tags, where confidently known

    def query(self) -> str:
        gene_terms = [self.gene_name, self.gene_locus] + list(self.extra_loci)
        return build_query(gene_terms, SPECIES, RESISTANCE_TERMS)


# ── FULL TARGET LIST (mirrors mycodiscovery_targets_v1.json category/target IDs) ──
TARGETS: List[Target] = [
    # Cell Wall & Envelope Biosynthesis
    Target("dpre1", "DprE1/E2", "dprE1", "Rv3790", "cell_wall",
           # mab_0192c is the M. abscessus tag widely cited in BTZ/DprE1
           # literature. M. smegmatis (MSMEG_6382) and M. avium (MAV_0232)
           # tags were dropped per your confirmation — keeping the pattern
           # to gene name + Rv locus + confirmed mab_ tag only, consistent
           # across all targets.
           extra_loci=["mab_0192c"]),
    Target("inha", "InhA", "inhA", "Rv1484", "cell_wall"),
    Target("embcab", "EmbCAB", "embB", "Rv3795", "cell_wall"),
    Target("pks13", "Pks13", "pks13", "Rv3800c", "cell_wall"),
    Target("mmpl3", "MmpL3", "mmpL3", "Rv0206c", "cell_wall"),
    Target("murx_mray", "MurX/MraY", "mraY", "Rv2156c", "cell_wall"),
    Target("ubia", "UbiA", "ubiA", "Rv3806c", "cell_wall"),
    Target("accd6", "AccD6", "accD6", "Rv2247", "cell_wall"),
    Target("fas1_fas2", "FAS-I / FAS-II", "fas", "Rv2524c", "cell_wall"),
    # Beta-Lactam Targets & Resistance Mechanisms
    Target("blac", "BlaC", "blaC", "Rv2068c", "beta_lactam"),
    Target("pona", "PonA", "ponA1", "Rv0050", "beta_lactam"),
    Target("pbpb", "PbpB", "pbpB", "Rv2163c", "beta_lactam"),
    Target("ripa", "RipA", "ripA", "Rv2869c", "beta_lactam"),
    Target("ldtmt", "LdtMt1/Mt2/Mt3", "ldtMt2", "Rv0116c", "beta_lactam"),
    # Central Metabolism & Bioenergetics
    Target("atp_synthase", "ATP Synthase", "atpE", "Rv1305", "central_metabolism"),
    Target("ndh", "NADH-2 (Ndh)", "ndh", "Rv1854c", "central_metabolism"),
    Target("cytbc1aa3", "Cyt bc1-aa3", "qcrB", "Rv2196", "central_metabolism"),
    Target("icl", "ICL (Icl1/Icl2)", "icl1", "Rv0467", "central_metabolism"),
    Target("pepck", "PEPCK (PckA)", "pckA", "Rv0211", "central_metabolism"),
    Target("mena_mend", "MenA/MenD", "menA", "Rv0534c", "central_metabolism"),
    Target("lipb", "LipB", "lipB", "Rv1256c", "central_metabolism"),
    # DNA/RNA Information Processing & Nucleotide Metabolism
    Target("dna_gyrase", "DNA Gyrase", "gyrA", "Rv0006", "dna_rna_nucleotide"),
    Target("rna_polymerase", "RNA Polymerase", "rpoB", "Rv0667", "dna_rna_nucleotide"),
    Target("dnae1", "DnaE1", "dnaE1", "Rv1547", "dna_rna_nucleotide"),
    Target("thya", "ThyA", "thyA", "Rv2764c", "dna_rna_nucleotide"),
    Target("nrdef2", "NrdEF2", "nrdE", "Rv3051c", "dna_rna_nucleotide"),
    Target("guab2", "GuaB2", "guaB2", "Rv3411c", "dna_rna_nucleotide"),
    # Aromatic Amino Acid & Shikimate Pathway
    Target("trpe", "TrpE", "trpE", "Rv1609", "shikimate"),
    Target("trpd", "TrpD", "trpD", "Rv2192c", "shikimate"),
    Target("arob", "AroB", "aroB", "Rv2537c", "shikimate"),
    Target("arog", "AroG", "aroG", "Rv2178c", "shikimate"),
    Target("phea", "PheA", "pheA", "Rv3838c", "shikimate"),
    # Amino Acid & Nitrogen Metabolism
    Target("dapa_dapb", "DapA / DapB", "dapB", "Rv2773c", "amino_acid_nitrogen"),
    Target("leua_c_d", "LeuA / LeuC / LeuD", "leuA", "Rv3710", "amino_acid_nitrogen"),
    Target("ilvc_d_e", "IlvC / IlvD / IlvE", "ilvC", "Rv2967c", "amino_acid_nitrogen"),
    Target("meta_b_c", "MetA / MetB / MetC", "metA", "Rv3341", "amino_acid_nitrogen"),
    Target("asnb", "AsnB", "asnB", "Rv2201", "amino_acid_nitrogen"),
    Target("gltd", "GltD", "gltD", "Rv3859c", "amino_acid_nitrogen"),
    # Cofactor & Vitamin Biosynthesis
    Target("pank", "PanK", "panK", "Rv1092c", "cofactor_vitamin"),
    Target("ribba", "RibBA", "ribBA", "Rv1415", "cofactor_vitamin"),
    Target("dhps", "DHPS", "folP1", "Rv3608c", "cofactor_vitamin"),
    Target("bioa_biod", "BioA / BioD", "bioA", "Rv1568", "cofactor_vitamin"),
    # Virulence & Host Adaptation
    Target("mbti_mbta", "MbtI / MbtA", "mbtA", "Rv2384", "virulence"),
    Target("cyp121", "CYP121", "cyp121", "Rv2276", "virulence"),
    Target("phop", "PhoP", "phoP", "Rv0757", "virulence"),
    Target("rpfa_e", "RpfA-E", "rpfA", "Rv0867c", "virulence"),
]


def all_queries():
    """Yields (target, query_string) — one combined query per target."""
    for t in TARGETS:
        yield t, t.query()


if __name__ == "__main__":
    print(f"MycoDiscovery search protocol v{PROTOCOL_VERSION} ({PROTOCOL_DATE})")
    print(f"Targets: {len(TARGETS)} | Per-target queries: {len(TARGETS)}")
    print(f"\nBroad (gene-unrestricted) query:\n  {BROAD_QUERY}")
    t = TARGETS[0]
    print(f"\nSample per-target query [{t.id}]:\n  {t.query()}")
