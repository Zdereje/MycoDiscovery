"""
auto_extract.py
Fills as many CSV columns as can be reasonably inferred from abstract text
— compound name/class, Bacteria, Method, MIC, phase_or_status,
ClinicalTrials.gov ID, mechanism, Gene, Function, Mutations — using a mix
of regex and curated lookup tables specific to mycobacterial drug
resistance (generic regex alone can't identify "bedaquiline" or "dprE1"
as meaningful entities; this module knows about them directly).

WHAT THIS STILL IS AND ISN'T:
Every value this produces is a best-guess from pattern-matching and lookup
tables, not verified comprehension of the paper. It fills fields that used
to be left blank, but `verification_status` is NEVER touched by this module
— that stays exclusively a human decision, same as everywhere else in this
pipeline. Treat every filled cell as "here's what a first pass found,
please confirm," not "this is confirmed."

Known limitations, stated plainly:
  - compound_name/Gene lookups only catch names in the curated lists below.
    A paper about a genuinely novel compound with no code name resembling
    known patterns, or a target gene not in GENE_DB, will come back blank
    for that field — that's the "impossible" case your instructions asked
    about, not a bug.
  - mechanism extraction grabs the sentence containing mechanism-indicating
    keywords, not a synthesized understanding — it can grab the wrong
    sentence if a paper's phrasing is unusual.
  - Multiple compounds/genes/mutations in one abstract all get joined into
    one cell (semicolon-separated) rather than creating extra rows — if a
    paper covers several compounds, you'll want to split it into separate
    rows by hand during curation.
"""
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# ── CURATED COMPOUND DATABASE ───────────────────────────────────────────
# name -> class. Matched case-insensitively as whole words/phrases against
# abstract text. Extend this list over time as you encounter compounds not
# yet covered — that's expected, not a design flaw.
COMPOUND_DB: Dict[str, str] = {
    # Approved / repurposed
    "bedaquiline": "Diarylquinoline", "clofazimine": "Riminophenazine",
    "linezolid": "Oxazolidinone", "amikacin": "Aminoglycoside",
    "clarithromycin": "Macrolide", "azithromycin": "Macrolide",
    "rifampicin": "Rifamycin", "rifabutin": "Rifamycin", "rifampin": "Rifamycin",
    "isoniazid": "Isonicotinylhydrazide", "ethambutol": "Ethylenediamine",
    "pyrazinamide": "Nicotinamide analog", "moxifloxacin": "Fluoroquinolone",
    "levofloxacin": "Fluoroquinolone", "ciprofloxacin": "Fluoroquinolone",
    "imipenem": "Carbapenem", "meropenem": "Carbapenem", "cefoxitin": "Cephalosporin",
    "tigecycline": "Glycylcycline", "minocycline": "Tetracycline",
    "doxycycline": "Tetracycline", "delamanid": "Nitroimidazole",
    "pretomanid": "Nitroimidazole", "streptomycin": "Aminoglycoside",
    "kanamycin": "Aminoglycoside", "capreomycin": "Cyclic peptide",
    "ethionamide": "Thioamide", "prothionamide": "Thioamide",
    "para-aminosalicylic acid": "Folate pathway inhibitor",
    "cycloserine": "Cyclic amino acid analog", "dapsone": "Sulfone",
    # Early-discovery / investigational
    "macozinone": "Benzothiazinone", "pbtz169": "Benzothiazinone",
    "btz043": "Benzothiazinone", "tba-7371": "Azaindole",
    "opc-167832": "Carbostyril", "sq109": "Ethylenediamine (MmpL3 inhibitor)",
    "sutezolid": "Oxazolidinone", "tedizolid": "Oxazolidinone",
    "gsk656": "Leucyl-tRNA synthetase inhibitor", "gsk3036656": "Leucyl-tRNA synthetase inhibitor",
    "telacebec": "Imidazopyridine", "q203": "Imidazopyridine",
    "tbi-166": "Riminophenazine analog", "epetraborole": "Oxaborole",
    "tam16": "Benzofuran", "au1235": "Adamantyl urea",
    "nitd-916": "4-hydroxy-2-pyridone",
}

# ── CURATED GENE -> FUNCTION DATABASE ───────────────────────────────────
# Includes both M. tuberculosis and M. abscessus-relevant resistance genes.
# erm(41) and rrl are the dominant M. abscessus macrolide-resistance genes —
# included explicitly given the abscessus cross-resistance research focus.
GENE_DB: Dict[str, str] = {
    "rpob": "RNA polymerase beta subunit (rifamycin target)",
    "katg": "Catalase-peroxidase (isoniazid activation)",
    "inha": "Enoyl-ACP reductase (isoniazid/ethionamide target)",
    "embb": "Arabinosyltransferase (ethambutol target)",
    "embc": "Arabinosyltransferase (ethambutol target)",
    "gyra": "DNA gyrase subunit A (fluoroquinolone target)",
    "gyrb": "DNA gyrase subunit B (fluoroquinolone target)",
    "rrs": "16S rRNA (aminoglycoside target)",
    "eis": "Aminoglycoside acetyltransferase",
    "erm(41)": "Ribosomal RNA methyltransferase (inducible macrolide resistance, M. abscessus)",
    "erm41": "Ribosomal RNA methyltransferase (inducible macrolide resistance, M. abscessus)",
    "rrl": "23S rRNA (macrolide/linezolid target)",
    "atpe": "ATP synthase subunit c (bedaquiline target)",
    "mmpl5": "Efflux pump component (bedaquiline/clofazimine resistance)",
    "mmps5": "Efflux pump component (bedaquiline/clofazimine resistance)",
    "rv0678": "MmpS5-MmpL5 efflux repressor (bedaquiline/clofazimine resistance)",
    "mmpr5": "MmpS5-MmpL5 efflux repressor (bedaquiline/clofazimine resistance, M. abscessus nomenclature)",
    "pnca": "Pyrazinamidase (pyrazinamide activation)",
    "etha": "Monooxygenase (ethionamide activation)",
    "gid": "7-methylguanosine methyltransferase (low-level streptomycin resistance)",
    "tlya": "rRNA methyltransferase (capreomycin/viomycin target)",
    "folp1": "Dihydropteroate synthase (sulfonamide/dapsone target)",
    "dpre1": "Decaprenylphosphoryl-beta-D-ribose 2'-epimerase (arabinogalactan synthesis)",
    "mmpl3": "Trehalose monomycolate transporter",
    "whib7": "Transcriptional regulator (intrinsic multidrug resistance, prominent in M. abscessus)",
    "rpsl": "Ribosomal protein S12 (streptomycin target)",
    "ndh": "NADH dehydrogenase (clofazimine/bedaquiline cross-resistance)",
}

NCT_PATTERN = re.compile(r'\bNCT\d{8}\b')

MIC_PATTERN = re.compile(
    r'MIC[a-z0-9]*\s*(?:of|was|were|is|:|=|values?)?\s*'
    r'(?:[<>≤≥~]\s*)?'
    r'(\d+\.?\d*(?:\s*[-–to]+\s*\d+\.?\d*)?)\s*'
    r'(µg/mL|ug/mL|μg/mL|mg/L|ng/mL|µM|uM|nM|mM)',
    re.IGNORECASE,
)

MUTATION_PATTERN = re.compile(r'\b([A-Z]\d{1,4}[A-Z])\b')
MUTATION_FALSE_POSITIVES = {"H37Rv", "H37Ra", "K562"}

REVIEW_SELF_ID_PATTERNS = re.compile(
    r'\bthis review\b|\bwe review\b|\boverview of\b|\bin this (?:mini-?)?review\b|'
    r'\bsummariz(?:e|es|ed|ing)\b.{0,40}\b(?:literature|studies|advances)\b',
    re.IGNORECASE,
)

METHOD_KEYWORDS = [
    "broth microdilution", "REMA", "MABA", "MGIT", "agar dilution", "Etest",
    "resazurin microtiter", "microplate alamar blue", "disk diffusion",
    "whole genome sequencing", "site-directed mutagenesis", "spontaneous mutant selection",
]

PHASE_KEYWORDS = [
    ("phase iii", "Phase III clinical trial"), ("phase 3", "Phase III clinical trial"),
    ("phase iia", "Phase IIa clinical trial"), ("phase ii", "Phase II clinical trial"),
    ("phase 2", "Phase II clinical trial"), ("phase i", "Phase I clinical trial"),
    ("phase 1", "Phase I clinical trial"), ("fda-approved", "Marketed/approved"),
    ("who-approved", "Marketed/approved"), ("preclinical", "Preclinical"),
    ("in vitro", "Preclinical (in vitro data)"), ("in vivo", "Preclinical (in vivo data)"),
]

STRAIN_PATTERNS = [
    "H37Rv", "H37Ra", "ATCC 19977", "ATCC 25177", "CIP 104536",
    "M. abscessus subsp. abscessus", "M. abscessus subsp. massiliense", "M. abscessus subsp. bolletii",
]

MECHANISM_KEYWORD_PATTERN = re.compile(
    r'\b(?:mechanism|mediated by|confers?|conferring|target(?:s|ed|ing)?|'
    r'inhibit(?:s|ing|ion)?|binding|blocks?)\b',
    re.IGNORECASE,
)

# Splits on ". " only when followed by an uppercase letter (a real new sentence),
# NOT on abbreviation periods like "M. abscessus" (lowercase follows) or
# "e.g." / "i.e." — naive `[^.]*...\.` splitting breaks on those, which is
# a common failure mode in scientific text full of species abbreviations.
SENTENCE_SPLIT_PATTERN = re.compile(r'(?<=[a-z0-9)])\.\s+(?=[A-Z])')


@dataclass
class AutoExtractResult:
    compound_name: str = ""
    compound_class: str = ""
    bacteria: str = ""
    method: str = ""
    mic: str = ""
    phase_or_status: str = ""
    clinicaltrials_id: str = ""
    mechanism: str = ""
    gene: str = ""
    function: str = ""
    mutations: str = ""
    is_likely_review: bool = False
    notes: str = ""


def _find_compounds(text: str) -> List[str]:
    lower = text.lower()
    return [name for name in COMPOUND_DB if re.search(r'\b' + re.escape(name) + r'\b', lower)]


def _find_genes(text: str) -> List[str]:
    lower = text.lower()
    return [g for g in GENE_DB if re.search(r'\b' + re.escape(g) + r'\b', lower)]


def _find_method(text: str) -> List[str]:
    lower = text.lower()
    return [m for m in METHOD_KEYWORDS if m.lower() in lower]


def _find_phase(text: str) -> Optional[str]:
    lower = text.lower()
    for keyword, label in PHASE_KEYWORDS:
        if keyword in lower:
            return label
    return None


def _find_strain(text: str) -> List[str]:
    return [s for s in STRAIN_PATTERNS if s.lower() in text.lower()]


def auto_extract(abstract: str, species_hint: str = "") -> AutoExtractResult:
    if not abstract:
        return AutoExtractResult(
            bacteria=species_hint,
            notes="No abstract text available — nothing could be auto-extracted. Full-text read required.",
        )

    notes_parts = []

    compounds = _find_compounds(abstract)
    compound_name = "; ".join(c.title() for c in compounds)
    compound_class = "; ".join(sorted(set(COMPOUND_DB[c] for c in compounds)))
    if compounds:
        notes_parts.append(f"AUTO: compound(s) matched against known-compound list: {compound_name}.")
    else:
        notes_parts.append("AUTO: no compound matched the curated known-compound list — may be a genuinely novel/uncoded compound, or a name not yet in COMPOUND_DB. Read manually.")

    genes = _find_genes(abstract)
    gene_field = "; ".join(genes)
    function_field = "; ".join(sorted(set(GENE_DB[g] for g in genes)))
    if genes:
        notes_parts.append(f"AUTO: gene(s) matched against known-gene list: {gene_field}.")
    else:
        notes_parts.append("AUTO: no gene matched the curated known-gene list.")

    strains = _find_strain(abstract)
    bacteria = species_hint or "; ".join(strains) or ""
    if strains and species_hint:
        bacteria = f"{species_hint} ({'; '.join(strains)})"

    methods = _find_method(abstract)
    method_field = "; ".join(methods)

    mic_hits = [f"{val.strip()} {unit}" for val, unit in MIC_PATTERN.findall(abstract)]
    mic_field = "; ".join(mic_hits)
    if mic_hits:
        notes_parts.append(f"AUTO: possible MIC value(s): {mic_field} — verify unit/context, may not be this compound's own value.")

    phase = _find_phase(abstract) or ""

    nct_hits = NCT_PATTERN.findall(abstract)
    nct_field = "; ".join(nct_hits)
    if nct_hits:
        notes_parts.append(f"AUTO: ClinicalTrials.gov ID found directly in abstract: {nct_field}.")

    sentences = SENTENCE_SPLIT_PATTERN.split(abstract)
    mechanism = ""
    for sentence in sentences:
        if MECHANISM_KEYWORD_PATTERN.search(sentence):
            mechanism = sentence.strip()
            break
    if mechanism:
        notes_parts.append("AUTO: mechanism field is the first sentence matching mechanism-indicating keywords — may not be the most relevant sentence, verify.")

    raw_mutations = MUTATION_PATTERN.findall(abstract)
    mutation_hits = sorted(set(m for m in raw_mutations if m not in MUTATION_FALSE_POSITIVES))
    mutations_field = "; ".join(mutation_hits)
    if mutation_hits:
        notes_parts.append(f"AUTO: possible mutation token(s): {mutations_field} — regex pattern-match only, verify these are real substitutions.")

    is_review = bool(REVIEW_SELF_ID_PATTERNS.search(abstract))
    if is_review:
        notes_parts.append("AUTO: abstract text itself suggests this is a REVIEW, even if Publication Type/title didn't flag it.")

    return AutoExtractResult(
        compound_name=compound_name,
        compound_class=compound_class,
        bacteria=bacteria,
        method=method_field,
        mic=mic_field,
        phase_or_status=phase,
        clinicaltrials_id=nct_field,
        mechanism=mechanism,
        gene=gene_field,
        function=function_field,
        mutations=mutations_field,
        is_likely_review=is_review,
        notes=" | ".join(notes_parts),
    )
