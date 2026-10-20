---
name: plugins
description: Use other QGIS plugins — find one for a task among the installed ones or in the official QGIS plugin repository, install it with the user's consent, run its Processing algorithms or start its menu commands. Load this when no built-in skill covers the task (isochrones and routing, segmentation, web maps, special formats, national services) or the user names a plugin.
tools: [list_plugins, describe_plugin, run_plugin_command, find_plugin, install_plugin]
---

# Other plugins

Many tasks the built-in skills cannot do are already solved by a plugin:
isochrones and routing, AI segmentation of imagery, exporting a web map,
special file formats, national data services. Look before saying something is
impossible.

## Order

1. `list_plugins` — the installed, active ones; filter with a word for the
   task (`segmentation`, `web map`, `isochrones`).
2. Nothing fits → `find_plugin` in the official repository. Pick by fit first,
   then by downloads; prefer a plugin that is not experimental. Tell the user
   in one line what it is and why, then queue `install_plugin` with its key —
   the user confirms the installation. A result marked `installed` but not
   `active` is switched on by the same call. A fitting plugin already found
   in this conversation is enough: do not search again.
3. `describe_plugin` — what that plugin offers. A plugin queued for install
   exists only once applied: when the next step needs it, call `apply_now`.
4. Prefer its **Processing algorithms**: they run through the processing skill
   (`describe_processing`, then `run_processing`) — parameters are checked, the
   step joins the plan and the result comes back to you. Load the processing
   skill for them.
5. Use `run_plugin_command` only when the plugin has no algorithm for the task.
   It clicks the plugin's menu command for the user, after a confirmation,
   because another plugin's code can do anything. Most commands open the
   plugin's own window: say so, tell the user what to choose there, and do
   not claim a result you cannot see.

## Never

- Never start a command that the user did not ask for or that the task does
  not need — not "to see what it does".
- Never install a plugin the task does not need, and never two for the same
  job. A plugin that needs an account or an API key (a routing service) says
  so in its description: tell the user before installing it.
- Never guess a command path: copy it from `describe_plugin`.
