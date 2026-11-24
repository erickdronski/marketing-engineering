# Verify a change

Use Python 3.9 or later and run these commands from a clean clone:

```sh
python -m unittest discover -s tests -t .
python -m mktgkit demo
python -m mktgkit init practice --example
python -m mktgkit warehouse build -w practice
python -m mktgkit check -w practice
```

The example intentionally contains dated research and a stale spend export. Its check should report warnings and zero errors. Run the same workflow from a wheel in a fresh virtual environment when changing package data. Run Ruff for lint and formatting. The CI workflow checks multiple Python versions, Windows and macOS.

The synthetic source data and decision history have regenerators in `tools/`. Regenerate into a new directory first and compare reviewed changes before replacing a fixture. Changes to source notes can invalidate signed claims. Keep the demo and documentation examples consistent with the reviewed fixture.

For an issue, include the version, operating system, a minimal synthetic input, the command and the observed result. Remove private client names, contact details, tokens and transcripts before posting.
