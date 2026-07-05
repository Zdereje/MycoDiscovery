"""
protocol.py
The PRE-SPECIFIED search protocol for the MycoMUT Target Explorer systematic
literature search.

Why this file exists (for the methods section of a future publication):
Systematic reviews require a documented, reproducible search strategy defined
BEFORE screening begins — not queries improvised ad hoc while reading results.
This file is that pre-specification. Every query MycoMUT's search pipeline runs
is generated from this file, so the exact search strings are always fully
recoverable and auditable, and any reviewer/collaborator can rerun the same
protocol and get the same query set.

Versioning: bump PROTOCOL_VERSION whenever query templates or the target list
change, and keep old versions in git history — a systematic review methods
section should state which protocol version produced which results.

Databases: this protocol targets PubMed (via NCBI E-utilities) only, for v1.
PMC full-text and bioRxiv/medRxiv preprint search are natural extensions —
see the `sources` field per target if/when you add them.
"""
from dataclasses import dataclass, field
from typing import List

PROTOCOL_VERSION = "1.0.0"
PROTOCOL_DATE = "2026-07-05"

# ── QUERY TEMPLATES ──────────────────────────────────────────────────────
# Two independent query classes per target, run separately (not OR-combined)
# so compound-discovery hits and resistance-mutation hits can be screened
# and reported as distinct PRISMA streams, matching how the target-centric
# schema separates "compounds" from "mutations".

COMPOUND_QUERY_TEMPLATE = (
    '("{gene_name}"[Title/Abstract] OR "{gene_locus}"[Title/Abstract]) '
    'AND ("Mycobacterium tuberculosis"[Title/Abstract] OR "M. tuberculosis"[Title/Abstract]) '
    'AND ("inhibitor"[Title/Abstract] OR "inhibitors"[Title/Abstract] '
    'OR "inhibition"[Title/Abstract] OR "lead compound"[Title/Abstract])'
)

MUTATION_QUERY_TEMPLATE = (
    '("{gene_name}"[Title/Abstract] OR "{gene_locus}"[Title/Abstract]) '
    'AND ("Mycobacterium tuberculosis"[Title/Abstract] OR "M. tuberculosis"[Title/Abstract]) '
    'AND ("resistance"[Title/Abstract] OR "resistant"[Title/Abstract] '
    'OR "mutation"[Title/Abstract] OR "mutant"[Title/Abstract] OR "SNP"[Title/Abstract])'
)

# ── PRE-SPECIFIED INCLUSION / EXCLUSION CRITERIA ────────────────────────
# State these BEFORE screening (standard PRISMA practice) so screening
# decisions are auditable against a fixed rule, not made up per-paper.

INCLUSION_CRITERIA = [
    "Peer-reviewed primary research article, or a preprint from bioRxiv/medRxiv "
    "clearly superseded by or awaiting peer review.",
    "Reports at least one named compound (with a stated or citable chemotype/class) "
    "AND/OR at least one specific resistance mutation (gene + amino-acid or "
    "nucleotide change) tied to Mycobacterium tuberculosis complex or a named "
    "nontuberculous mycobacterial species.",
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
    "Studies in species outside the Mycobacterium genus, unless the paper is "
    "explicitly cross-referenced from an included Mycobacterium study.",
]


@dataclass
class Target:
    id: str
    name: str
    gene_name: str          # e.g. "dprE1" — used in query construction
    gene_locus: str         # e.g. "Rv3790"
    category_id: str

    def compound_query(self) -> str:
        return COMPOUND_QUERY_TEMPLATE.format(gene_name=self.gene_name, gene_locus=self.gene_locus)

    def mutation_query(self) -> str:
        return MUTATION_QUERY_TEMPLATE.format(gene_name=self.gene_name, gene_locus=self.gene_locus)


# ── FULL TARGET LIST (mirrors mycomut_targets_v1.json category/target IDs) ──
# gene_name is the lowercase gene symbol used in PubMed title/abstract text;
# for multi-gene target groups (e.g. "EmbCAB"), the dominant/most-searched
# individual gene symbol is used as the primary query term, with the group
# name added as a secondary OR term where useful — edit per curator judgment
# as you review actual query yield.

TARGETS: List[Target] = [
    # Cell Wall & Envelope Biosynthesis
    Target("dpre1", "DprE1/E2", "dprE1", "Rv3790", "cell_wall"),
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
    """Yields (target, query_type, query_string) for every target — the full,
    exact set of queries this protocol version specifies."""
    for t in TARGETS:
        yield t, "compound", t.compound_query()
        yield t, "mutation", t.mutation_query()


if __name__ == "__main__":
    print(f"MycoMUT search protocol v{PROTOCOL_VERSION} ({PROTOCOL_DATE})")
    print(f"Targets: {len(TARGETS)} | Queries: {len(TARGETS) * 2}")
    for t, qtype, q in all_queries():
        print(f"[{t.id}] ({qtype}) {q}")
