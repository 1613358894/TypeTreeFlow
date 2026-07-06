from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from typetreeflow.external.runner import CommandRunner
from typetreeflow.phylo.iqtree import IqtreeResult, execute_iqtree
from typetreeflow.phylo.mafft import MafftResult, execute_mafft
from typetreeflow.phylo.plan import build_phylo_plan, write_phylo_plan
from typetreeflow.phylo.trimal import TrimalResult, execute_trimal
from typetreeflow.workflow.paths import OutputPaths


@dataclass(frozen=True)
class PhyloWorkflowResult:
    plan_path: Path
    mafft_result: MafftResult | None
    trimal_result: TrimalResult | None
    iqtree_result: IqtreeResult | None
    treefile_path: Path
    status: str
    notes: str = ""


def prepare_phylogeny(
    paths: OutputPaths,
    runner: CommandRunner | None = None,
    dry_run: bool = True,
    force: bool = False,
    skip_tree: bool = False,
    enable_phylo: bool = False,
    query_required: bool = False,
    threads: int = 1,
    bootstrap: int = 1000,
    model: str = "MFP",
) -> PhyloWorkflowResult:
    plan = build_phylo_plan(
        paths,
        skip_tree=skip_tree,
        force=force,
        query_required=query_required,
    )
    plan_path = write_phylo_plan(plan, paths.phylo_plan_path)

    if skip_tree:
        return _result(
            plan_path,
            paths.iqtree_treefile_path,
            status="phylo_skipped",
            notes=plan.notes,
        )

    if dry_run:
        return _result(
            plan_path,
            paths.iqtree_treefile_path,
            status=plan.status,
            notes=plan.notes,
        )

    if not enable_phylo:
        return _result(
            plan_path,
            paths.iqtree_treefile_path,
            status="phylo_not_enabled",
            notes="Phylogeny execution requires --enable-phylo; no command was run.",
        )

    if plan.status != "phylo_planned":
        return _result(
            plan_path,
            paths.iqtree_treefile_path,
            status=plan.status,
            notes=plan.notes,
        )

    if runner is None:
        return _result(
            plan_path,
            paths.iqtree_treefile_path,
            status="phylo_runner_missing",
            notes="Phylogeny execution requires an injected command runner in this phase.",
        )

    mafft_result = execute_mafft(
        plan,
        runner,
        dry_run=False,
        force=force,
        threads=threads,
    )
    if not _step_ready(mafft_result.status, "mafft"):
        return _result(
            plan_path,
            paths.iqtree_treefile_path,
            mafft_result=mafft_result,
            status="phylo_mafft_failed",
            notes=mafft_result.notes,
        )

    trimal_result = execute_trimal(
        plan,
        runner,
        dry_run=False,
        force=force,
    )
    if not _step_ready(trimal_result.status, "trimal"):
        return _result(
            plan_path,
            paths.iqtree_treefile_path,
            mafft_result=mafft_result,
            trimal_result=trimal_result,
            status="phylo_trimal_failed",
            notes=trimal_result.notes,
        )

    iqtree_result = execute_iqtree(
        plan,
        runner,
        dry_run=False,
        force=force,
        threads=threads,
        bootstrap=bootstrap,
        model=model,
    )
    if not _step_ready(iqtree_result.status, "iqtree"):
        return _result(
            plan_path,
            paths.iqtree_treefile_path,
            mafft_result=mafft_result,
            trimal_result=trimal_result,
            iqtree_result=iqtree_result,
            status="phylo_iqtree_failed",
            notes=iqtree_result.notes,
        )

    return _result(
        plan_path,
        iqtree_result.treefile_path,
        mafft_result=mafft_result,
        trimal_result=trimal_result,
        iqtree_result=iqtree_result,
        status="phylo_tree_ready",
        notes=f"Phylogeny treefile is ready: {iqtree_result.treefile_path}",
    )


def _step_ready(status: str, tool: str) -> bool:
    return status in {f"{tool}_succeeded", f"{tool}_skipped_existing"}


def _result(
    plan_path: Path,
    treefile_path: Path,
    status: str,
    notes: str,
    mafft_result: MafftResult | None = None,
    trimal_result: TrimalResult | None = None,
    iqtree_result: IqtreeResult | None = None,
) -> PhyloWorkflowResult:
    return PhyloWorkflowResult(
        plan_path=plan_path,
        mafft_result=mafft_result,
        trimal_result=trimal_result,
        iqtree_result=iqtree_result,
        treefile_path=treefile_path,
        status=status,
        notes=notes,
    )
