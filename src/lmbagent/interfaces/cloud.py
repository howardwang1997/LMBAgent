"""Abstract interface for cloud deployment (Phase 3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CloudInterface(ABC):
    """Abstract interface for deploying the agent to cloud/AgentScope."""

    @abstractmethod
    async def deploy(self, config: dict[str, Any]) -> str:
        """Deploy the agent with given configuration.

        Returns:
            Deployment endpoint URL or ID.
        """
        ...

    @abstractmethod
    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle an incoming analysis request.

        Args:
            request: Dict with keys like 'file_url', 'analysis_type', 'output_format'.

        Returns:
            Dict with analysis results and output file URLs.
        """
        ...
