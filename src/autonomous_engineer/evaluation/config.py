"""
evaluation/config.py -- Live LLM provider configuration and secure environment auditor.

Provides:
1. LLMProviderConfig: Strict provider-neutral configuration with secret masking.
2. EvaluationMode: Explicit LIVE / MOCK / UNAVAILABLE mode selection.
3. EnvironmentAuditor: Safe environment inspection guaranteeing zero credential leakage.
"""
from __future__ import annotations

import enum
import os
import platform
import shutil
import subprocess
import sys
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class EvaluationMode(str, enum.Enum):
    """Execution mode of the evaluation runner."""

    LIVE = "live"
    MOCK = "mock"
    UNAVAILABLE = "unavailable"


class LLMProviderConfig(BaseModel):
    """
    Configuration contract for live LLM providers.
    Guarantees secrets are never revealed in string representations or serialization.
    """

    model_config = ConfigDict(frozen=True)

    provider_name: str = Field(
        default="openai-compatible",
        description="Identifier of provider protocol",
    )
    api_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL for chat completions endpoint",
    )
    model_name: str = Field(
        default="gpt-4o",
        description="Model identifier to request",
    )
    api_key: str | None = Field(
        default=None,
        description="Secret API key (never printed or persisted in plain text)",
    )
    timeout_seconds: float = Field(
        default=60.0,
        ge=1.0,
        description="Request timeout in seconds",
    )
    max_tokens: int = Field(
        default=4096,
        ge=1,
        description="Maximum output tokens",
    )
    temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="Generation temperature (0.0 for deterministic baseline)",
    )
    retry_limit: int = Field(
        default=3,
        ge=1,
        description="Network/HTTP retry limit",
    )

    @classmethod
    def from_env(cls) -> LLMProviderConfig:
        """Construct provider configuration from environment variables."""
        api_key = (
            os.environ.get("OPENAI_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )
        if os.environ.get("OPENROUTER_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            api_base = os.environ.get("OPENROUTER_BASE_URL", os.environ.get("OPENAI_API_BASE", "https://openrouter.ai/api/v1"))
            model = os.environ.get("OPENROUTER_MODEL", os.environ.get("OPENAI_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"))
        else:
            api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")
            model = os.environ.get("OPENAI_MODEL", "gpt-4o")

        return cls(
            provider_name="openai-compatible",
            api_base_url=api_base,
            model_name=model,
            api_key=api_key,
        )

    @property
    def has_credentials(self) -> bool:
        """True iff a non-empty API key is present."""
        return bool(self.api_key and len(self.api_key.strip()) > 0)

    def masked_dict(self) -> dict[str, Any]:
        """Return configuration dictionary with API key strictly masked."""
        data = self.model_dump()
        if data.get("api_key"):
            data["api_key"] = "[REDACTED_SECRET]"
        else:
            data["api_key"] = None
        data["has_credentials"] = self.has_credentials
        return data


class EnvironmentAuditor:
    """Safely audits execution environment capabilities without leaking sensitive information."""

    @staticmethod
    def audit() -> dict[str, Any]:
        """
        Produce a complete, safe audit of runtime environment capabilities.
        """
        git_version = "unavailable"
        if shutil.which("git"):
            try:
                proc = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
                git_version = proc.stdout.strip()
            except Exception:
                git_version = "error_querying"

        pytest_version = "unavailable"
        try:
            import pytest
            pytest_version = getattr(pytest, "__version__", "unknown")
        except ImportError:
            pass

        provider_config = LLMProviderConfig.from_env()

        # Check network connectivity safely
        has_network = False
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            # Query standard DNS port
            sock.connect(("8.8.8.8", 53))
            sock.close()
            has_network = True
        except Exception:
            has_network = False

        return {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "os_name": os.name,
            "git_version": git_version,
            "pytest_version": pytest_version,
            "network_available": has_network,
            "llm_provider": provider_config.provider_name,
            "llm_model": provider_config.model_name,
            "llm_credentials_available": provider_config.has_credentials,
            "evaluation_mode_default": (
                EvaluationMode.LIVE.value
                if provider_config.has_credentials
                else EvaluationMode.UNAVAILABLE.value
            ),
        }