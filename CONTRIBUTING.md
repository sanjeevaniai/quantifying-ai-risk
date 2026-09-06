# Contributing

Corrections are welcome, particularly where the implementation is wrong.

```bash
pip install -r requirements.txt
pytest
```

If you change the engine, the contracts or the scenario file, run the three
notebooks in order as well. CI does both on Python 3.10, 3.11 and 3.12.

A few conventions:

- Declared values belong in `contracts/*.json` or `risk_scenario.yaml`, not in
  `src/qair`. If a number needs to be in both, the contract is the source and the
  code reads it.
- When an assumption changes, update the contract or the scenario file rather
  than only the code that uses it.
- Notebooks are committed without outputs. CI checks this.
- `tests/test_reproducibility.py` holds the values the pipeline should reproduce
  from the committed fixture. If a change moves one legitimately, update it there
  and say why in the pull request.

A failing test is a good bug report on its own.
