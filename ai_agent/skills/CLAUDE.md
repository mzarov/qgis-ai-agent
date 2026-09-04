# skills/ — domain knowledge

A skill is a domain package: `<domain>/SKILL.md` with frontmatter and a body of
rules. This is what used to live as numbered clauses in the system prompt.

The format deliberately follows the open Agent Skills convention: required
`name` and `description` in the frontmatter, a Markdown body, progressive
loading. Our `tools` field is a local extension binding the skill to its tool
classes.

## Format

```markdown
---
name: processing
description: One sentence — when to load this skill. The model chooses by it.
tools: [search_processing, describe_processing, run_processing]
---

# Domain heading

The rules the model must know while working in this domain.
```

The frontmatter is parsed by hand on stdlib (`base.py`) — PyYAML is not a
dependency and will not become one. `key: value` pairs and inline lists
`[a, b, c]` are supported.

## Rules

1. **The language is English.** The `SKILL.md` body goes into the system
   prompt. English here is more than a convention: example user phrasings are
   written in English too, otherwise the skill teaches the model one language
   instead of all of them. Which language to *answer* in is decided not by the
   skill but by `language_policy` in `core/agent/prompts.py`.
2. **`description` is the selection trigger.** Write it as the answer to “when
   should I load this”, not as the domain's title. It sits in the prompt
   permanently, so one dense line, not a paragraph.
3. **`tools` must match the registry.** The names in the list are exactly the
   tools with `skill = "<domain>"` in `qgis_tools/registry.py`, in the same
   order. A mismatch is caught by review checks.
4. **Never duplicate what the code already guarantees.** If the tool itself
   coerces an enum label to its index or fills the default output, a rule about
   it does not belong in `SKILL.md`. It only burns tokens and drifts from the
   code at the first edit. That was the main disease of the old prompt.
   The reverse also holds: when the model systematically ignores a `SKILL.md`
   rule — move the check into `BaseTool.prepare`; code is more reliable than an
   instruction.
5. **Write what the model cannot guess:** step order, measurement units,
   pitfalls like metres on a geographic CRS, links to other domains.
6. **The body loads on demand,** so length is cheaper here than in the prompt
   core. But no padding: anything that does not change the model's decision is
   excess.

## Adding a domain

1. `qgis_tools/<domain>/` — tool classes with `skill = "<domain>"`
2. `skills/<domain>/SKILL.md` — frontmatter and rules
3. one line in `qgis_tools/registry.py`

The loop, the orchestrator and the prompt core stay untouched. If you had to
edit them — the abstraction leaked; find out why.

## Local skills

Users can add skills without touching the plugin: `<QGIS profile>/ai_agent_skills/<name>/SKILL.md`,
the same format as the built-in ones. The registry stays pure — it never
imports `qgis` — so the local root is set from outside by
`core/local_skills.py` (`SKILL_REGISTRY.set_local_root`) and rescanned before
every prompt and every popup, which is a directory listing, nothing more.

Rules the loader enforces instead of trusting: `name` is mandatory and
lowercase (`[a-z0-9][a-z0-9_-]*`), `description` is mandatory, a name taken by
a built-in skill is refused (the built-in wins — a local file must not be able
to rewrite `inspect`), a name used twice locally is refused. Refused entries
are reported as problems on the Skills settings page, never loaded silently.

A local skill cannot add Python: its `tools` list may only name tools that
already exist, unknown names are dropped and reported. Loading a local skill
also loads the domains of the tools it names (`skills_to_load`), so a skill
that says `tools: [download_osm]` brings the OSM rules with it — otherwise the
model would have the tool without the knowledge of how it is used here.
