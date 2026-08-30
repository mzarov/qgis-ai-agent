## Outcome

Describe the user-visible result and why it belongs in the plugin.

## Safety and data boundary

- [ ] Read tools do not mutate QGIS.
- [ ] Writes are visible in the plan before execution.
- [ ] External files, destructive operations and `run_python` have explicit risk handling.
- [ ] Any new data sent to a model or service is disclosed and tested.
- [ ] No credential, project data or generated archive was committed.

## Verification

- [ ] `python3 -m unittest discover -s tests -t .`
- [ ] `ruff check . && ruff format --check .`
- [ ] `python3 tools/build_plugin.py`
- [ ] Relevant live-QGIS checks from `docs/smoke_checklist.md`

Add screenshots or a short recording for visible UI changes.
