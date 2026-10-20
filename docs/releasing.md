# Releasing

A release is one manual run of `.github/workflows/release.yml`. It tests the
code, builds the ZIP, uploads it to
[plugins.qgis.org](https://plugins.qgis.org/plugins/ai_agent/), and only then
tags the commit and publishes a GitHub release with the ZIP attached.

## One-time setup

1. On plugins.qgis.org open **AI Agent → Tokens**
   (`https://plugins.qgis.org/plugins/ai_agent/tokens/`) and create a token.
2. In GitHub open **Settings → Secrets and variables → Actions** and save it
   as the secret `QGIS_PLUGIN_TOKEN`.

## Each release

1. Raise `version=` in `ai_agent/metadata.txt` and `version` in
   `pyproject.toml`. Add an entry at the top of `changelog=`: the version on its
   own line, then up to five short `- ` bullets. Indent every changelog line;
   an unindented line breaks the metadata.
2. Merge to `main`.
3. Run **Actions → release → Run workflow** on `main`.

Before building, the run installs the ZIP in QGIS 4.0 (`qgisMinimumVersion`)
and current stable QGIS containers and runs the real-QGIS workflows and
end-to-end scenarios (see the [smoke checklist](smoke_checklist.md)). Tick
**live_model_check** to also run the live-model scenarios; that spends the
provider's tokens.

The run stops before publishing if a test, ruff or mypy fails, the version's
tag already exists or the changelog has no entry for it. Only the final job,
which tags the release, can write to the repository. If plugins.qgis.org rejects the
upload, nothing is tagged. `python3 tools/release_notes.py` prints the release
notes.

A new version appears on plugins.qgis.org after its automatic checks and, for
accounts without the approver role, a manual approval.
