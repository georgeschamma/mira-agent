from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mira_agent.config import Settings
from mira_agent.integrations.exa import ResearchClient
from mira_agent.repositories.rls_client import RlsClient
from mira_agent.schemas.auth import CurrentUser


@dataclass(frozen=True, slots=True)
class MiraContext:
    client: RlsClient
    user: CurrentUser
    settings: Settings
    research_client: ResearchClient
    model: Any
