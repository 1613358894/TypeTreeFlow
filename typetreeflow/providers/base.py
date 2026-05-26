from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol


class ProviderStatus(str, Enum):
    UNAVAILABLE = "unavailable"
    PLANNING_ONLY = "planning_only"
    METADATA_ONLY = "metadata_only"
    DOWNLOAD_ENABLED = "download_enabled"


@dataclass(frozen=True)
class ProviderCapability:
    status: ProviderStatus
    supports_network: bool = False
    requires_credentials: bool = False
    requires_terms_review: bool = True
    private_cache_allowed: bool = False
    allowed_modes: tuple[str, ...] = ("planning",)
    redistributable_fixtures_only: bool = True

    def allows_network_by_default(self) -> bool:
        return False


@dataclass(frozen=True)
class ProviderContext:
    outdir: Path
    network_enabled: bool = False
    mode: str = "planning"
    notes: tuple[str, ...] = field(default_factory=tuple)


class ProviderAdapter(Protocol):
    provider_key: str
    display_name: str
    capability: ProviderCapability

    def plan_notes(self, context: ProviderContext) -> list[str]:
        """Return review-only guidance for provider planning rows."""
        ...
