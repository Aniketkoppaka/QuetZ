"""
retrieval/import_resolver.py -- Conservative local Python import resolver.

Statically maps ImportStatement objects to repo-relative file paths using the
RepositoryMap.
Zero code execution, zero sys.path modification, zero runtime reflection.
"""
from __future__ import annotations

from pathlib import Path

from autonomous_engineer.domain.models import ImportStatement, RepositoryMap


class LocalImportResolver:
    """Statically resolves import statements to repository-relative files."""

    def __init__(self, repo_map: RepositoryMap) -> None:
        self._repo_map = repo_map
        # Build lookup tables for rapid matching
        self._module_name_to_path: dict[str, str] = {}
        self._relative_paths: set[str] = set()

        for mod in repo_map.python_modules:
            self._module_name_to_path[mod.module_name] = mod.file_path
            self._relative_paths.add(mod.file_path)

    def resolve_import(
        self,
        source_file_path: str,
        import_stmt: ImportStatement,
    ) -> str | None:
        """
        Attempt to resolve an ImportStatement to a repo-relative file path.

        Args:
            source_file_path: Repo-relative path of the file containing the import.
            import_stmt: The ImportStatement to resolve.

        Returns:
            Repo-relative path (e.g. 'src/pkg/utils.py') if resolved, or None.
        """
        source_p = Path(source_file_path)
        source_dir = source_p.parent

        # 1. Relative imports (from . import x, from ..sub import y)
        if import_stmt.level > 0:
            target_dir = source_dir
            for _ in range(import_stmt.level - 1):
                target_dir = target_dir.parent

            mod_suffix = import_stmt.module.replace(".", "/") if import_stmt.module else ""
            candidate_base = (target_dir / mod_suffix).as_posix() if mod_suffix else target_dir.as_posix()

            # Check candidate.py
            cand_py = f"{candidate_base}.py"
            if cand_py in self._relative_paths:
                return cand_py

            # Check candidate/__init__.py
            cand_init = f"{candidate_base}/__init__.py" if candidate_base else "__init__.py"
            if cand_init in self._relative_paths:
                return cand_init

            # Also check if imported name is a submodule (e.g. from . import utils -> utils.py)
            for name in import_stmt.names:
                cand_sub = f"{candidate_base}/{name}.py" if candidate_base else f"{name}.py"
                if cand_sub in self._relative_paths:
                    return cand_sub

            return None

        # 2. Absolute imports (level == 0)
        if not import_stmt.module:
            return None

        module_dotted = import_stmt.module

        # Direct match in module_name_to_path
        if module_dotted in self._module_name_to_path:
            return self._module_name_to_path[module_dotted]

        # Match by path suffix (e.g. 'pkg.models' matching 'src/pkg/models.py')
        as_path_suffix = module_dotted.replace(".", "/") + ".py"
        for path in self._relative_paths:
            if path.endswith(as_path_suffix):
                return path

        # Match package __init__.py suffix
        as_init_suffix = module_dotted.replace(".", "/") + "/__init__.py"
        for path in self._relative_paths:
            if path.endswith(as_init_suffix):
                return path

        return None