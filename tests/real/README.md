# Real-API tests

These tests hit Onshape's live API using credentials from the environment.
They are **skipped by default** when `ONSHAPE_ACCESS_KEY` is not set, so the
regular `pytest` run (which targets the 471 mock-based tests) is unaffected.

Run them explicitly:

```bash
pytest tests/real/ -v
```

They reuse the smoke-test document `c287a50857bf10a5be2320c5` and delete any
features they create when done. See `scratchpad/smoke-test.md` in the parent
project for evidence of the response shapes these tests assert on.
