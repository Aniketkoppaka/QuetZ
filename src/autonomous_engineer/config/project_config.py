"""
config/project_config.py -- Declarative Project-Level Configuration (.quetz.yaml).

Enables repositories to define deterministic per-repo behavior:
- Target test command override
- Minimum confidence thresholds
- Custom banned imports and protected paths
- Sandbox runtime preferences (docker vs. local)
- Mutation testing enablement
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ProjectExecutionConfig(BaseModel):
    """Execution preferences specified in .quetz.yaml."""

    model_config = ConfigDict(frozen=True)

    test_command: str | None = None
    sandbox: str = "local"  # "docker" or "local"
    docker_image: str = "quetz-sandbox:latest"
    timeout_seconds: int = 120
    min_confidence: float = 0.85
    enable_mutation_testing: bool = False
    max_repair_iterations: int = 3


class QuetzProjectConfig(BaseModel):
    """Root configuration model for .quetz.yaml or .quetz.json."""

    model_config = ConfigDict(frozen=True)

    version: int = 1
    policy: str = "strict-fail-closed"
    execution: ProjectExecutionConfig = Field(default_factory=ProjectExecutionConfig)
    banned_imports: tuple[str, ...] = Field(default=())
    protected_paths: tuple[str, ...] = Field(default=())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QuetzProjectConfig:
        exec_data = data.get("execution", {})
        if isinstance(exec_data, dict):
            execution = ProjectExecutionConfig(**exec_data)
        else:
            execution = ProjectExecutionConfig()

        banned = tuple(data.get("banned_imports", []))
        protected = tuple(data.get("protected_paths", []))

        return cls(
            version=data.get("version", 1),
            policy=data.get("policy", "strict-fail-closed"),
            execution=execution,
            banned_imports=banned,
            protected_paths=protected,
        )

    @classmethod
    def load_from_workspace(cls, workspace_path: Path) -> QuetzProjectConfig | None:
        """Look for .quetz.yaml, .quetz.yml, or .quetz.json in root."""
        candidates = [
            workspace_path / ".quetz.yaml",
            workspace_path / ".quetz.yml",
            workspace_path / ".quetz.json",
        ]
        for c in candidates:
            if c.is_file():
                content = c.read_text(encoding="utf-8")
                try:
                    import yaml  # type: ignore
                    data = yaml.safe_load(content) or {}
                except ImportError:
                    import json
                    try:
                        data = json.loads(content)
                    except Exception:
                        data = {}
                return cls.from_dict(data)
        return None