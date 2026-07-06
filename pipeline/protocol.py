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


def build_query(gene_terms: List[str], species: List[str], resistance_terms: List[str]) -> str:
    """Gene/locus terms restricted to Title/Abstract (keeps precision).
    Species and resistance terms left unrestricted (broadens recall)."""
    gene_clause = " OR ".join(f'"{g}"[Title/Abstract]' for g in gene_terms)
    species_clause = " OR ".join(f'"{s}"' for s in species)
    resistance_clause = " OR ".join(f'"{r}"' for r in resistance_terms)
    return f'({gene_clause}) AND ({species_clause}) AND ({resistance_clause})'


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
           extra_loci=["MSMEG_6382", "mab_0192c"]),  # verified in DprE1 literature
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
    print(f"Targets: {len(TARGETS)} | Queries: {len(TARGETS)} (one per target)")
    for t, q in all_queries():
        print(f"\n[{t.id}]\n  {q}")
