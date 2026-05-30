# Troubleshooting

Setup and runtime fixes for the **Quantifying AI Risk** O'Reilly Live Training Course.

Work top to bottom. Most issues are solved in the first section. If you are short on time during the live session, jump straight to [Section 2: Run in Colab](#2-run-in-colab) — it sidesteps every local environment problem.

---

## 1. Local setup

### Run the check first

From the repo root:

```bash
python setup_check.py
```

Exit code `0` means you are ready. Anything else prints exactly which check failed. The script **only verifies** — it never installs or changes anything. The fixes below are the actions it asks you to take.

### The one-line fix that solves most failures

```bash
pip install -r requirements.txt
```

Re-run `python setup_check.py` afterward to confirm.

### Python version too old

The course needs **Python 3.10 or newer**. The version check is the one failure `pip` cannot fix for you — you need the right interpreter before anything else works.

Check what you have:

```bash
python --version
```

If it is below 3.10:

- **Recommended:** create a fresh environment with a supported version.
  ```bash
  # using conda
  conda create -n airisk python=3.11
  conda activate airisk
  pip install -r requirements.txt
  ```
- **Or** install Python 3.11 from python.org, then make sure you launch it (`python3.11` on some systems).

If upgrading locally is going to eat your session time, use [Colab](#2-run-in-colab) instead and fix this later.

### A package says it is not installed

Install the one it names, or install everything at once:

```bash
pip install -r requirements.txt
```

If `pip` itself is missing or out of date:

```bash
python -m ensurepip --upgrade
python -m pip install --upgrade pip
```

### "Permission denied" during install

You are installing into a system Python. Two clean ways out:

```bash
# Option A — install just for your user
pip install --user -r requirements.txt
```

```bash
# Option B (better) — use a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

A virtual environment is the more durable fix and keeps the course packages from colliding with anything else on your machine.

### Jupyter starts but the notebook cannot find a kernel

This is the `ipykernel` check failing. Install it into the **same** environment you are running the notebooks from:

```bash
pip install ipykernel
python -m ipykernel install --user --name airisk --display-name "Quantifying AI Risk"
```

Then in Jupyter: **Kernel → Change Kernel →** "Quantifying AI Risk".

### Launching the notebooks

Once checks pass:

```bash
jupyter notebook notebooks/01_telemetry.ipynb
```

---

## 2. Run in Colab

If anything local is fighting you, this is the fastest path back into the session. Colab already has Python and every package the course needs.

1. Open the repo's **README** on GitHub.
2. Click the **Open in Colab** badge next to the notebook you need.
3. The notebook opens in your browser. Run cells top to bottom.

### Notes for Colab

- **Run the notebooks in order.** Hour 1 writes data that Hour 2 reads; Hour 2 writes posteriors that Hour 3 reads. Out of order, later notebooks will not find their inputs.
- **Files do not persist** after the session ends. That is fine for the course — you are generating the data live each time.
- If a notebook needs a file produced by an earlier one, just run the earlier notebook first in the same Colab session, or re-run from the top.
- If Colab says a package is missing (rare), add a cell at the top:
  ```python
  !pip install -r requirements.txt
  ```

---

## 3. Common notebook runtime errors

### `FileNotFoundError` pointing at the `data/` folder

The `data/` folder is **empty when you clone the repo**. The notebooks fill it as they run.

- Hour 2 cannot find the telemetry stream → run **Hour 1** first, all the way through.
- Hour 3 cannot find the posteriors → run **Hour 2** first, all the way through.

Run each notebook from the top. Skipping cells is the usual cause.

### `ModuleNotFoundError` inside a notebook (but `setup_check.py` passed)

Your notebook is running a **different** Python than the one you checked. Confirm the kernel:

```python
import sys
print(sys.executable)
```

If that path is not your course environment, switch kernels (**Kernel → Change Kernel**) or reinstall `ipykernel` into the right environment (see [Section 1](#jupyter-starts-but-the-notebook-cannot-find-a-kernel)).

### A cell hangs or the simulation feels stuck

The Hour 3 Monte Carlo runs 10,000 scenarios. On a modest machine it can take a little time. Give it a few seconds before assuming it is stuck. If you interrupted it midway, restart the kernel (**Kernel → Restart**) and run from the top.

### Plots do not show up

Make sure the plotting cell ran without error and, if needed, that the notebook has:

```python
%matplotlib inline
```

In Colab this is on by default.

### State got weird after running cells out of order

The cleanest reset: **Kernel → Restart & Run All**. Because each notebook regenerates its own data, a clean top-to-bottom run always reproduces the expected result.

---

## Still stuck during the live session?

Drop a note in the chat. I will help while we work through the Hour 1 theory — there is enough conceptual material before the first notebook that you have room to fix an environment problem without falling behind. If all else fails, switch to Colab and rejoin the flow.
