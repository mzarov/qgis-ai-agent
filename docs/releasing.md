# Releasing

A release is one button in GitHub. The workflow `.github/workflows/release.yml`
tests the code, builds the zip, uploads it to
[plugins.qgis.org](https://plugins.qgis.org/plugins/ai_agent/), and only then
tags the commit and publishes a GitHub release with the zip attached.

## One-time setup

1. On plugins.qgis.org open **AI Agent → Tokens**
   (`https://plugins.qgis.org/plugins/ai_agent/tokens/`) and create a token.
2. In the GitHub repository open **Settings → Secrets and variables → Actions**
   and add it as the secret `QGIS_PLUGIN_TOKEN`.

The token is only ever read from that secret; it never appears in the code or
the logs.

## Each release

1. Raise `version=` in `ai_agent/metadata.txt` and `version` in
   `pyproject.toml`, and add an entry on top of `changelog=` — the version on
   its own indented line, then `- ` bullets. Keep every changelog line
   indented: an unindented line makes the metadata unreadable for the plugin
   repository.
2. Merge that to `main`.
3. **Actions → release → Run workflow** on `main`.

The run fails, before anything is published, when the tests fail, when the tag
for that version already exists, or when the changelog has no entry for it.
If plugins.qgis.org rejects the upload, nothing is tagged — fix the problem and
run it again. `python3 tools/release_notes.py` prints the notes the release will
use.

A new version appears on plugins.qgis.org after its automatic checks and, for
accounts without the approver role, a manual approval by the repository
volunteers.
