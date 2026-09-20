#!/usr/bin/env python3
"""Check that the environment can run the notebooks.

    python setup_check.py

Exit code 0 means ready. It does not train a model or run a simulation.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

REQUIRED_PYTHON = (3, 10)

PACKAGES = {
    "numpy": "numpy",
    "scipy": "scipy",
    "sklearn": "scikit-learn",
    "matplotlib": "matplotlib",
    "yaml": "PyYAML",
    "jsonschema": "jsonschema",
    "ipykernel": "ipykernel",
}

COMMITTED_INPUTS = (
    "risk_scenario.yaml",
    "measures.py",
    "data/control_evidence.json",
    "data/reference_distribution.json",
)


def line(ok: bool, message: str, fix: str = "") -> bool:
    print(f"  [{'OK' if ok else 'FAIL'}]   {message}")
    if not ok and fix:
        print(f"          {fix}")
    return ok


def check_python() -> bool:
    actual = sys.version_info[:2]
    return line(
        actual >= REQUIRED_PYTHON,
        f"Python {actual[0]}.{actual[1]} (need >= {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]})",
        "Install a newer Python.",
    )


def check_packages() -> bool:
    results = []
    for import_name, pip_name in PACKAGES.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            results.append(line(False, f"{pip_name} is not installed",
                                f"pip install {pip_name}"))
            continue
        try:
            results.append(line(True, f"{pip_name} {version(pip_name)}"))
        except PackageNotFoundError:
            results.append(line(True, f"{pip_name}"))
    return all(results)


def check_repository(root: Path) -> bool:
    results = [line((root / rel).exists(), rel, "Missing tracked file; re-clone.")
               for rel in COMMITTED_INPUTS]
    contracts = sorted(p.stem for p in (root / "contracts").glob("*.json"))
    results.append(line(bool(contracts), f"contracts/: {len(contracts)} measures "
                                         f"({', '.join(contracts)})"))
    schemas = list((root / "schemas").glob("*.schema.json"))
    results.append(line(bool(schemas), f"schemas/: {len(schemas)} schemas"))
    return all(results)


def check_library(root: Path) -> bool:
    for path in (str(root), str(root / "src")):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        from qair.contracts import load_contracts
        from qair.risk import load_scenario
    except Exception as exc:  # noqa: BLE001
        return line(False, f"qair import failed: {exc}", "Run from the repository root.")
    try:
        contracts = load_contracts(root / "contracts")
        scenario = load_scenario(root / "risk_scenario.yaml")
        scenario.check_covers(contracts)
    except Exception as exc:  # noqa: BLE001
        return line(False, f"contracts or scenario failed to load: {exc}")

    ok = line(True, f"loaded {len(contracts)} contracts and the risk scenario")
    ok &= line(True, f"dependence matrix validates ({len(scenario.dependence_order)}x"
                     f"{len(scenario.dependence_order)})")
    ok &= line(scenario.mode in ("illustrative", "calibrated"),
               f"risk_scenario.yaml mode: {scenario.mode}")
    return ok


def check_notebook_filter(root: Path) -> None:
    """Report whether this clone strips notebook outputs on commit.

    Advisory only: it never changes the exit code. The nbstripout filter is
    defined in .git/config, which cannot be committed, so a fresh clone and a CI
    checkout both start without it. CI's own gate is the backstop.
    """
    if not (root / ".git").exists():
        return
    try:
        found = subprocess.run(["git", "config", "--get", "filter.nbstripout.clean"],
                               cwd=root, capture_output=True, text=True).returncode == 0
    except OSError:
        return

    print("\nNotebooks:")
    if found:
        print("  [OK]   notebook outputs are stripped on commit")
    else:
        print("  [NOTE] this clone does not strip notebook outputs on commit")
        print("          nbstripout --install --attributes .gitattributes")


def main() -> int:
    root = Path(__file__).resolve().parent
    print("Quantifying AI Risk — environment check\n")

    print("Python:")
    python_ok = check_python()
    print("\nPackages:")
    packages_ok = check_packages()
    print("\nRepository:")
    repo_ok = check_repository(root)
    print("\nLibrary:")
    library_ok = check_library(root) if packages_ok and repo_ok else line(
        False, "skipped, fix the failures above first")

    check_notebook_filter(root)

    all_ok = python_ok and packages_ok and repo_ok and library_ok
    if all_ok:
        print("\nReady. Open notebooks/01_telemetry.ipynb.")
    else:
        print("\nSome checks failed. Try: pip install -r requirements.txt")
        print("See TROUBLESHOOTING.md.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
