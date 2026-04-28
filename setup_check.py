#!/usr/bin/env python3
"""
setup_check.py

Verifies the local environment is ready for the
"Quantifying AI Risk" O'Reilly Live Training Course.

Run from the repo root:

    python setup_check.py

Exit code 0 means you are ready. Anything else means at least one check
failed and the script will tell you which one.
"""

import sys
import importlib
from importlib.metadata import version, PackageNotFoundError


REQUIRED_PYTHON = (3, 10)

REQUIRED_PACKAGES = [
    "numpy",
    "pandas",
    "scipy",
    "matplotlib",
    "seaborn",
    "sklearn",      # scikit-learn imports as sklearn
    "jupyter",
    "tqdm",
]

# Some packages have a different import name than their pip name.
PIP_NAMES = {
    "sklearn": "scikit-learn",
}


def _check_python_version() -> bool:
    actual = sys.version_info[:2]
    ok = actual >= REQUIRED_PYTHON
    required_str = f"{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}"
    actual_str = f"{actual[0]}.{actual[1]}"
    if ok:
        print(f"  [OK]   Python {actual_str} (need >= {required_str})")
    else:
        print(f"  [FAIL] Python {actual_str} (need >= {required_str})")
        print(f"         Upgrade Python before continuing.")
    return ok


def _check_package(name: str) -> bool:
    pip_name = PIP_NAMES.get(name, name)
    try:
        importlib.import_module(name)
    except ImportError:
        print(f"  [FAIL] {pip_name} is not installed")
        print(f"         Run: pip install {pip_name}")
        return False

    try:
        installed_version = version(pip_name)
        print(f"  [OK]   {pip_name} {installed_version}")
    except PackageNotFoundError:
        # Imported fine but version unknown — still acceptable
        print(f"  [OK]   {pip_name} (version unknown)")
    return True


def _check_jupyter_kernel() -> bool:
    """Verify ipykernel is installed so Jupyter can actually run notebooks."""
    try:
        importlib.import_module("ipykernel")
        print(f"  [OK]   ipykernel is available")
        return True
    except ImportError:
        print(f"  [FAIL] ipykernel is not installed")
        print(f"         Run: pip install ipykernel")
        return False


def main() -> int:
    print("=" * 60)
    print("  Quantifying AI Risk — environment check")
    print("=" * 60)
    print()

    print("Python version:")
    python_ok = _check_python_version()
    print()

    print("Required packages:")
    package_results = [_check_package(name) for name in REQUIRED_PACKAGES]
    print()

    print("Jupyter runtime:")
    kernel_ok = _check_jupyter_kernel()
    print()

    all_ok = python_ok and all(package_results) and kernel_ok

    print("=" * 60)
    if all_ok:
        print("  All checks passed. You are ready for Hour 1.")
        print()
        print("  Next step:")
        print("      jupyter notebook notebooks/01_telemetry.ipynb")
        print("=" * 60)
        return 0
    else:
        print("  Some checks failed. Fix the issues listed above")
        print("  and re-run this script before the course starts.")
        print()
        print("  Quickest fix in most cases:")
        print("      pip install -r requirements.txt")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())