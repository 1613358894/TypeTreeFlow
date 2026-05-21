from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from typetreeflow.workflow.paths import OutputPaths

PHYLO_PLAN_FIELDS = [
    "input_fasta_path",
    "aligned_fasta_path",
    "trimmed_fasta_path",
    "iqtree_prefix",
    "treefile_path",
    "status",
    "notes",
]

MIN_PHYLO_SEQUENCES = 4


@dataclass(frozen=True)
class PhyloPlan:
    input_fasta_path: Path
    aligned_fasta_path: Path
    trimmed_fasta_path: Path
    iqtree_prefix: Path
    treefile_path: Path
    status: str
    notes: str = ""


def build_phylo_plan(
    paths: OutputPaths,
    skip_tree: bool = False,
    force: bool = False,
) -> PhyloPlan:
    input_fasta_path = paths.all_16s_fasta_path
    aligned_fasta_path = paths.aligned_16s_fasta_path
    trimmed_fasta_path = paths.trimmed_16s_fasta_path
    iqtree_prefix = paths.iqtree_prefix
    treefile_path = paths.iqtree_treefile_path

    status = "phylo_planned"
    notes = "Phylogeny plan written; MAFFT, trimAl, and IQ-TREE were not executed."

    if skip_tree:
        status = "phylo_skipped"
        notes = "Tree workflow was skipped by configuration."
    elif not input_fasta_path.exists():
        status = "phylo_skipped_no_input"
        notes = f"Combined 16S FASTA does not exist: {input_fasta_path}"
    else:
        sequence_count = count_fasta_sequences(input_fasta_path)
        if sequence_count < MIN_PHYLO_SEQUENCES:
            status = "phylo_skipped_too_few_sequences"
            notes = (
                f"At least {MIN_PHYLO_SEQUENCES} FASTA sequences are required for "
                "IQ-TREE ultrafast bootstrap; "
                f"found {sequence_count}."
            )
        elif treefile_path.exists() and not force:
            status = "phylo_skipped_existing_tree"
            notes = f"Existing IQ-TREE treefile found: {treefile_path}"

    return PhyloPlan(
        input_fasta_path=input_fasta_path,
        aligned_fasta_path=aligned_fasta_path,
        trimmed_fasta_path=trimmed_fasta_path,
        iqtree_prefix=iqtree_prefix,
        treefile_path=treefile_path,
        status=status,
        notes=notes,
    )


def count_fasta_sequences(path: str | Path) -> int:
    count = 0
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith(">"):
                count += 1
    return count


def write_phylo_plan(plan: PhyloPlan, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PHYLO_PLAN_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerow(
            {field: str(getattr(plan, field)) for field in PHYLO_PLAN_FIELDS}
        )
    return output_path
