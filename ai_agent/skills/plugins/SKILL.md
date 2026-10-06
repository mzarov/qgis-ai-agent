---
name: plugins
description: Use the other QGIS plugins the user has installed — find which plugin can do a task (segmentation, web maps, special formats, services), run its Processing algorithms or start its menu commands. Load this when no built-in skill covers the task or the user names a plugin.
tools: [list_plugins, describe_plugin, run_plugin_command]
---

# Other installed plugins

Many tasks the built-in skills cannot do are already solved by a plugin the
user installed: AI segmentation of imagery, exporting a web map, special file
formats, national data services. Look before saying something is impossible.

## Order

1. `list_plugins` — filter with a word for the task (`segmentation`,
   `web map`, `elevation`). Only active plugins are listed; you cannot install
   or enable one — tell the user which plugin to install from the QGIS plugin
   repository when nothing fits.
2. `describe_plugin` — what that plugin offers.
3. Prefer its **Processing algorithms**: they run through the processing skill
   (`describe_processing`, then `run_processing`) — parameters are checked, the
   step joins the plan and the result comes back to you. Load the processing
   skill for them.
4. Use `run_plugin_command` only when the plugin has no algorithm for the task.
   It clicks the plugin's menu command for the user, after a confirmation,
   because another plugin's code can do anything. Most commands open the
   plugin's own window: say so, tell the user what to choose there, and do
   not claim a result you cannot see.

## Never

- Never start a command that the user did not ask for or that the task does
  not need — not "to see what it does".
- Never guess a command path: copy it from `describe_plugin`.
