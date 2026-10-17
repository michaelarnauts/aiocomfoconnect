"""Tests for the package metadata in pyproject.toml."""

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Distribution name -> top-level module it provides, where they differ.
IMPORT_NAMES = {
    "protobuf": "google",
}


def _pyproject():
    with open(ROOT / "pyproject.toml", "rb") as file:
        return tomllib.load(file)


def _imported_top_level_modules():
    modules = set()
    for path in (ROOT / "aiocomfoconnect").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return modules


def test_runtime_dependencies_are_imported():
    """Every runtime dependency should be imported by the package."""
    dependencies = set(_pyproject()["tool"]["poetry"]["dependencies"]) - {"python"}
    imported = _imported_top_level_modules()

    unused = {dep for dep in dependencies if IMPORT_NAMES.get(dep, dep) not in imported}
    assert not unused, f"Runtime dependencies that are never imported: {sorted(unused)}"


def test_license_is_declared():
    """The license should be part of the package metadata."""
    assert _pyproject()["tool"]["poetry"].get("license") == "MIT"
