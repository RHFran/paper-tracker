# Contributing

Thanks for helping make research digests more useful and trustworthy.

## Local development

Use Python 3.11+ on Windows, Linux, macOS, or WSL. Runtime code uses the standard
library; Windows also installs IANA timezone data from `tzdata`.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m compileall -q literature_digest
```

Work in a branch and keep changes focused. Include a regression test with a fix,
and update both quickstarts when changing user-visible behavior. Tests should be
offline by default: use synthetic metadata, mocked HTTP, mocked model responses,
and fake SMTP. Do not send email or incur provider charges in CI.

Live pipeline tests must configure a synthetic model and provide validated model
responses. `tests/model_fixture.py` supplies explicit doubles for tests focused on
other contracts; fail-closed model tests exercise the real analysis layer with
mocked provider HTTP. `preview` remains fully offline and model-free.

## Useful contributions

- Retrieval adapters with documented date semantics, pagination and error handling
- Better topic matching, deduplication, localization and accessible email layouts
- Evidence validation and rights-aware source-figure handling
- Scheduler, SMTP uncertainty and profile-isolation regression tests

Treat paper text, titles and provider responses as untrusted data. Escape HTML,
keep credentials out of reports and errors, and retain provenance for every
research claim. A matching evidence excerpt does not prove a paraphrase is correct.

## Pull requests

Describe the user-visible change, commands run and any untested integration.
Provide small, synthetic fixtures rather than publisher full text or private
reports. Never commit real addresses, API keys, SMTP passwords, state databases
or generated subscriber reports. Avoid adding runtime dependencies unless the
benefit justifies them.

Security-sensitive issues should follow [SECURITY.md](SECURITY.md), rather than a
public proof of concept containing credentials or personal data. Contributions
are provided under the repository's [MIT license](LICENSE).
