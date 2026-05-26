from __future__ import annotations

from typetreeflow.providers.base import ProviderCapability, ProviderContext, ProviderStatus


class AtccGenomePortalAdapter:
    provider_key = "atcc_genome_portal"
    display_name = "ATCC Genome Portal"
    capability = ProviderCapability(
        status=ProviderStatus.PLANNING_ONLY,
        supports_network=False,
        requires_credentials=False,
        requires_terms_review=True,
        private_cache_allowed=False,
        allowed_modes=("planning",),
        redistributable_fixtures_only=True,
    )

    def plan_notes(self, context: ProviderContext) -> list[str]:
        del context
        return [
            "adapter_status=planning_only",
            "atcc_downloader_gate=not_passed",
            "gate_failure=no documented ATCC legal approval or provider-permitted technical access route",
            "blocked_actions=login,download,scraping,browser_automation,terms_acceptance,purchase_flow,credential_storage",
            "handoff=user obtains permitted local FASTA outside TypeTreeFlow, records terms/license evidence, then uses external_genomes.tsv and --register-external-genomes",
        ]
