# ui/ — presentation only

Nothing but rendering logic lives here. No data processing, no LLM calls.

## Rules

1. **No business logic.** UI files only draw components and emit PyQt signals.
   Decisions belong to `core/`.
2. **QGIS wrappers only.** Always `from qgis.PyQt.QtWidgets import ...`.
   Never `PyQt5` or `PyQt6` directly — the Qt version depends on the QGIS build.
3. **No Qt Designer.** Widgets and layouts are built in code; there are no
   `.ui` files.
4. **Colours come from `theme.py`, the brand's tokens.** Two sets, light and
   dark, with the exact hex values of `design/tokens.css` — cartographic blue
   on cool neutrals, from the design handoff (`tests/test_settings_ui.py`
   checks they match). The QGIS palette only
   decides which set applies, by its lightness, so the plugin follows the
   light and the dark theme. It is deliberately not limited to the QGIS
   colours (the user's call: the plugin must look good, and palette-derived
   colours looked dull — on macOS the palette highlight is a muted navy).
   No other module spells a colour: widgets ask `style` for a role (`panel`,
   `hairline`, `muted`, `accent`…). The header icons are drawn in `icons.py`
   with a pen from `style`, not taken from `QgsApplication.getThemeIcon`: the
   stock icons are colourful toolbar art and look like mismatched stickers in
   a compact header.
5. **Enum compatibility.** Qt5 and Qt6 hold enums differently. Paths like
   `Qt.DockWidgetArea.RightDockWidgetArea` do not exist on Qt5 — wrap them in
   `getattr` with a fallback, as done in `plugin.py`.

## What the interface is made of

| File | What |
| ---- | --- |
| `dock_widget.py`  | the shell: header, feed, composer; conversation menu; the orchestrator contract |
| `conversation.py` | a `QScrollArea` with one widget per message, autoscroll, action grouping |
| `messages.py`     | the user message, the agent reply, the service message |
| `activity.py`     | the group of tool calls: named header with the time, rows with coloured skill badges and result lines |
| `disclosure.py`   | the fold line: title, detail, chevron after them |
| `plan.py`         | the plan card with its buttons inside |
| `confirmations.py` | the modal questions: share data with a provider, run destructive steps |
| `durations.py`    | `3.4 s`, `2 min 5 s` — one formatter for the feed and the settings |
| `composer.py`     | the input box as in Claude Code: text and the send/stop button inside, the toolbar under it; Enter sends, Esc stops a run; `/` and `@` open the popup |
| `composer_parts.py` | the editor, `/skill` and `@layer` parsing, token highlighting, the toolbar (+, model) |
| `sessions_popup.py` | the conversations menu: pick, rename in place, delete after the dock confirms |
| `context_meter.py` | the ring under the composer and its popup: window, auto-compact, Compact, spent |
| `choice_popup.py` | the mode menu as in Claude Code: caption, rows with a note, check and number key |
| `attachments.py`  | the + file pickers, drag-and-drop paths, the picture chips waiting in the composer |
| `chart.py`        | a chart in the feed: bars, rows, lines, donut, histogram, scatter; painted, hover tips, copy image/CSV |
| `chart_scale.py`  | axis arithmetic: round ticks, compact numbers, which bar layout fits |
| `table_card.py`   | a table in the feed: painted rows, natural column widths, elided cells with tips, copy CSV |
| `question.py`     | the agent's question card: up to three answers to click and a fourth row to type one's own |
| `progress.py`     | the status line: the searching compass, "Working…", the elapsed time; the feed's last row, under the newest message |
| `compass.py`      | the brand mark: open-ring compass painted on a 24-unit grid; needle rotation per state (rest, search, done, error, ask, arrive), keyframed with per-segment easing |
| `controls.py`     | custom controls: `Segmented` keeps the combo-box API, `Chips`, `RoundedFrame` (every state-dependent box), icon tiles, badges, keycaps, `ElidedLabel`, menus |
| `connection_widgets.py` | provider tiles and the connection status card |
| `logos.py`        | provider logos from `ui/logos/*.svg`, tinted to the theme's text colour |
| `skill_popup.py`  | the list above the composer: prefix-then-substring ranking, keyboard steering, `local` badge |
| `connectors_settings.py` | the Connectors page: open-data sources by group, search, a switch each; a card click opens its page |
| `connector_detail.py` | one connector's page: example prompts for the chat box, description, layers, licence, servers |
| `personalisation_settings.py` | the Personalisation page: who you are, instructions, how you work, answers; stores `config/personal` on Save |
| `memory_settings.py` | the Memory section: the user's notes, add and remove, stored on Save |
| `skills_settings.py` | the Skills settings page: folder, example, discovered local skills and their problems |
| `theme.py`        | the brand's light and dark colour tokens (`design/tokens.css`); the only module that spells a colour |
| `style.py`        | colour roles read from `theme`, `fill()` and `ink()` through the palette, `scale_font()` |
| `icons.py`        | header, settings-nav, brand and layer icons: drawn with a palette pen, one stroke weight |
| `settings_dialog.py` | the settings window: state, dirty tracking, saving |
| `settings_probe.py` | the connection test: start, cancel, report, close only once stopped |
| `settings_layout.py` | the sidebar, the page stack and per-page scrolling |
| `settings_fields.py` | the row grammar: rows, switches, separators, inputs, buttons |
| `settings_advanced.py` | the Privacy and Advanced pages |
| `geocoder_settings.py` | the Geocoding page |

## Icons

Interface icons are Lucide outlines (ISC; the licence notice stays inside
every file in `ui/glyphs/`, as the licence requires) and provider logos are
Simple Icons (CC0) in `ui/logos/`. Both are plain black SVGs recoloured at
runtime by `svg_art.tinted` with `CompositionMode_SourceIn`, so one set
follows both themes. One family, one stroke (1.75 on the 24 grid). The
device ratio sizes the pixmap, never the drawing. A null icon falls back to
a text glyph in the header. Add an icon by adding its Lucide file with the
notice and a role in `icons.NAMES`; `tests/test_icons.py` checks the set.

The dock header carries no title — the dock's title bar already says AI
Agent — only the token count and the three icon buttons.

## Menus and suggestion cards

Every popup menu comes from `controls.menu`: frameless and translucent (so
the rounded corners are not drawn over a square system frame), a soft edge,
roomy rows and a quiet highlight. Menus open where there is room: the history
menu right-aligned under its button, the composer's + menu upwards. The
history menu lists past conversations only; starting a new one is the button
beside it.

Welcome suggestions are `Suggestion` frames with a wrapping label, not
buttons: button text never wraps, and a long example was cut off in a narrow
dock. Examples name no local place; the one city named is Paris, which every
user knows.

## The agent reply is markdown

`AssistantMessage` renders text through `QTextDocument.setMarkdown()`. The
model writes bold, lists and code — all of it must display, not show as
asterisks. The height follows the content, because there is a single scroll —
the feed's.

While an answer streams, `append` does **not** render. Re-parsing the whole
document per token is quadratic work on the main thread, and the tokens arrive
faster than an eye can read them. Deltas accumulate and a single-shot timer
repaints at `REPAINT_INTERVAL_MS`; `set_markdown` stops that timer and renders
the final text at once. The timer is parented to the widget, so a dropped
draft cannot fire a repaint into a deleted browser.

## Transients in the feed

Three things in the feed are alive only for the current turn: the activity
group, the streaming draft and the thinking block. `ConversationView` owns the
discipline so the orchestrator does not have to: **every** append goes through
`_append`, which drops the draft and folds the thinking block. The one path
that bypasses it — `add_activity_step` with a group already open — repeats
both calls explicitly.

A thinking block does not break the group: it is added **inside** the
activity group as a row of its own, so a whole think–act–think–act chain folds
into one list. The group opens with its first call or reasoning; `_close_activity`
rests it when a message arrives, folding it to the header — the feed stays
readable without hiding anything: one click reopens a turn.

Drop and fold are different on purpose. A draft is normally **finalised**, not
dropped: before the first tool of a turn reaches the feed, the loop's `preamble`
signal has already turned the draft into a kept assistant message and saved it
into the conversation — so the text stays and replay still matches the screen.
The view-level drop in `_append` is only a safety net for a draft that was never
finalised (an aborted stream). A thinking block is **folded** — it stays in the
feed as one line the user can open again. The block shows how long it took only when
it was watched arriving: reasoning that came whole at the end of a
non-streaming request has no measurable duration, and printing `0.0 s` for a
minute of thought would be a lie.

## The empty state fills the panel

`WelcomeCard` has **no wrapping frame**. A card pinned to the top left two
thirds of the panel as a void; stretching that same card to full height only
turned the void into a huge empty box — worse, because a border draws attention
to the emptiness it encloses. What works is the opposite: no container at all,
and the suggestions themselves are the blocks. The group is centred vertically
in the free space, so the balance is deliberate rather than leftover.

The feed's trailing stretch is what fought the centring — it exists to push
messages upwards. While the welcome is shown that stretch drops to zero and the
card carries it instead; `_drop_welcome` hands it back. Both halves live in one
pair of methods so the two states cannot drift apart.

## The feed is flat lines, frames mean a decision

The activity list follows TerraLab's: the header names the first two calls and
counts the rest, "Reading layer roads, Adding basemap +2", and once the turn
moves on shows how long it took; the whole line is clickable (`Disclosure`).
While the agent works the rows sit **open, without a frame**, one per call: a
badge with the skill's icon in that skill's hue on a pale wash of it (`HUES`
over the categorical chart palette; the skill is the `CallSummary.skill` the
registry sets), the wording muted with the call's own values bright, and under
it the tool's `summarize_result` line — what the call found. Reasoning gets a
badge of its own so it lines up. When the answer arrives the list folds to its
header. A group with one call has no header at all — it only repeated the row —
and its row stays shown. Row text keeps the inherited font: a scaled font set before the row
joins the feed is computed from the application font and came out smaller. Success carries no mark — only a failed or rejected call shows
one, and the header counts failures in the danger colour. The working line
below says "Working…" with the time; it does not repeat the current call, which
the open list already names.

Boxing every turn made the feed read as a wall of cards. A frame with a fill is
reserved for the one thing that asks the user to act: the plan card. If a new
element wants a frame, the question to ask is "does it hold buttons?" — if not,
it is a line or an open list.

## Action grouping

`ConversationView` itself folds consecutive tool calls into one
`ActivityGroup`. Any message of another kind closes the group. So the
orchestrator still calls `add_tool_message` per call and knows nothing about
grouping.

## The plan card

While the plan applies, each step shows its progress at the end of its line
(● running, ✓ done, ✕ failed, — skipped) and a failed step its reason under
it, in plain words (`core/agent/failures.explain_failure`); the model keeps the
exact English error. Apply-phase tool events go to the card, not to feed rows,
which only repeated its lines.

The Apply and Cancel buttons live inside `PlanCard`, not as a separate row at
the bottom of the panel. The card emits signals upwards; the dock re-emits them
under the same names as before. After applying or cancelling the buttons
disappear and the title shows the outcome — the conversation history stays
honest.

## One button for send and stop

While the agent works, the send button does not grey out — it becomes “stop”:
the glyph, the colour and the tooltip change. There is deliberately no separate
button — it would be visible always and inactive most of the time. Enter is
ignored while a run is active; Esc stops it (with the popup open, Esc only
closes the popup). On an empty box the button is grey; offline it hides, since
the welcome card already offers Open settings.

## The conversations menu

The Conversations button in the header builds its menu at click time instead of
keeping a list: it goes stale with every agent reply. The list comes from the
orchestrator through `set_session_source` — the provider returns
`(identifier, title)` pairs so that no `core/` types leak into `ui/`.

## The settings window

**A sidebar over a page stack, styled after Claude's own settings.** Five
entries with drawn icons — Connection, Privacy, Skills, Geocoding, Advanced —
ordered by how often each is touched. Sidebar and pages sit **full-bleed on the same window surface**,
split by one vertical hairline; the footer is cut off by a horizontal one.
A floating lifted pane was tried between the tab and this version and looked
worse than both — a box inside a box reads as a widget, not a page. The
selected entry is a `panel()` pill plus bold, so the selection survives the
light theme where the lift is zero. The sidebar opens with the plugin's
brand mark, never with the word Settings: the window is already titled so.

**One row grammar for every control.** A row is caption left (title plus a
muted hint under it, both wrapping), control right at a fixed
`CONTROL_WIDTH`, vertically centred. Uniform control width is what makes the
pages read as straight columns instead of ragged boxes. `add_rows`
interleaves hairline separators **between** rows, never after the last one;
`card_rows` wraps them in a card. Controls that size themselves (segmented
choices, chips) use `custom_row`.

**Booleans are drawn switches, not native checkboxes.** A stray blue
checkbox at the end of a wide row reads as debris; a track-and-knob toggle
reads as a setting. `Switch` subclasses `QCheckBox` — the whole checkbox API
(`setChecked`, `toggled`, `setEnabled`) keeps working — and only replaces
`paintEvent`: accent track when on, hairline track when off, `card()` when
disabled, knob from `highlightedText`. Same approach as the header icons:
palette-driven `QPainter`, no image assets.

**Copy is short.** Every hint is one short phrase; a page or section note is
one sentence. Wordy explanations read as generated filler (the user's word
was "нейрослоп") — cut them, or move detail to a tooltip. The geocoder is one
row with a segmented Off · Photon · Nominatim choice, its hint follows the
choice, and the server address row appears only for Nominatim.

**Hints are visible, one short line under each title.** They used to hide
behind "?" marks to avoid a wall of text; the user approved the redesign
(`design/mockups/index.html`) that shows them again, so every hint must stay a
single short sentence. A longer explanation goes to the row's tooltip
(`tooltip=` in `fields.row`), never under the title.

**The window follows the Claude Code desktop settings** (the user's
reference). The sidebar has small group captions (`GROUPS`) and no search — there are
too few settings to need one (the user's call);
pages carry no title of their own and open with bold `section` headings, each
with an optional muted sentence; rows sit flat on the page with hairlines
between them (`card_rows` builds no frame). Only the main providers get a
tile — Ollama, LM Studio, OpenAI, OpenRouter, Anthropic, Google Gemini — with
monochrome Simple Icons logos (CC0) in `ui/logos/`, tinted by `logos.py`;
every other service is a custom address.

**The custom controls keep the combo-box API.** `Segmented` (API format,
authorisation, geocoder) answers `currentText`, `findText`,
`setCurrentIndex` and the change signals, so loading and saving did not change.
The provider tiles only draw `preset_combo`, which stays hidden and remains the
single source of truth: a tile sets the combo, the combo selects the tile.

**Edits are tracked.** `_watch_changes` marks a page dirty from its controls'
signals (never while `_loading_endpoint` is set); the page gets a dot in the
sidebar and Save stays disabled until something changed. The connection probe
answers in the status card at the top of the Connection page, with latency and
what is known about the endpoint; the footer line is for validation errors.

**The accent is the system accent, not the selection highlight.**
`style.accent` reads the Qt 6.6+ `Accent` role and falls back to `highlight`.
On macOS the highlight is the muted text-selection fill (`#314f78` in the dark
appearance), which made every button and ring look dull. On a dark palette the
accent is softened towards white and text on it uses `style.on_accent` (the
dark base), as in the mockup. Dark surfaces get a slight cool tint
(`style.cool`); the settings sidebar (`style.sidebar`) sits a step above the
content (`style.content`) and runs the full height, with the footer only under
the pages. Verify the window inside a real QGIS too: offscreen renders a
smaller font and the standard palette, and both hid real layout faults.

**The roles follow the mockup's CSS.** The settings sidebar is `surface-2`
and runs the full height with the footer only under the pages; pages, cards
and inputs are `surface`; inputs and plain buttons take `border-strong`; the
selected sidebar entry is a `surface` fill with no border and hover is
`sunken`; the dock and feed backdrop is `bg`. Verify windows inside a real
QGIS too: offscreen renders a smaller font, which hid real layout faults.

**Never restyle a container from inside a child's event.** A style sheet on a
container cascades to every descendant. The composer once changed its frame's
style sheet in the editor's `focusOutEvent`; Qt swapped the editor's style
mid-event and QGIS segfaulted in event processing, intermittently and only in
a full test run. Container backgrounds go through `style.fill` (the palette),
focus and state looks are painted (`controls.RoundedFrame` for the composer,
provider tiles and popup rows; `Compass`, `PaintedDot`), and a style
sheet is set only when its text actually changed.

**Nothing that cannot shrink may sit in a grid.** A pill badge or an unelided
name in the provider tiles widened the whole page in Russian; tile captions are
wrapping text and names elide. The screen checks' overflow detector found it.

Pages scroll individually (`scrollable()`), with the viewport forced
transparent so the window surface shows through — a `QScrollArea` left to
its own devices paints its own grey. Test connection lives on the
Connection page — it tests exactly what that page edits and means nothing on
the others, and its answer stays in that page's status card. The validation
line, the saved/unsaved note and Cancel/Save sit in the footer under a full
hairline, visible from every page.

The provider
is picked from a list and fills in the address and the API format; the preset
list lives in `core/llm/providers.py`, because that is knowledge about
services, not about the interface. The preset does **not** fill in the model —
it only suggests one as a placeholder: model names change more often than
addresses, and writing a wrong one is worse than writing none.

The connection-check result is shown as a line inside the window, not as a
modal box: the check gets pressed several times in a row, and closing a dialog
above a dialog every time is torture. Errors are red, success is green, both
colours come from the palette.

The connection check lives in `core/llm/probe.py` — it does not belong in ui,
it is a model call. The dialog receives a “worked, text” pair and only draws it.

**Three depth levels, not one.** The settings dialog first looked flatly dark,
and the cause was computed, not guessed: under the typical dark QGIS palette
the window background is ≈49 grey, `card()` gave 39 — the card was **darker**
than its backdrop and sank — while the input at 35 differed from it by four
levels out of 255. Hence `panel()`: in the dark theme it lifts the base towards
white, in the light theme it returns it untouched. The result is 49 → 59 → 35:
the card stands out, the input is recessed. `card()` remains for the
conversation feed; its look is already approved.

**Card styling must be bound to an objectName.** `QLabel` inherits `QFrame`, so
a selector like `QFrame { border: ... }` leaks into the labels inside the card.
Curing that by stamping `border: none` on containers is wrong: that rule leaks
further, into the inputs, and their frame disappears — exactly what happened.
The right way is `QFrame#settingsCard { ... }` plus explicit styles for
`QLineEdit`/`QComboBox`. The invariant is guarded by
`tests/test_settings_ui.py`.

## The orchestrator contract

`core/orchestrator/contracts.py::DockWidgetContract` describes the minimal API.
Added a method to `AgentDockWidget`? Add it to the contract too, otherwise the
wiring silently diverges.

## The slash popup

Typing `/` as the first character opens a list of skills **above** the
composer; it filters while the first token is typed and hides at the first
space. The popup is a plain child of the dock body positioned over the feed,
deliberately not a Qt `Popup` window: a popup window takes keyboard focus, and
the whole point is that the user keeps typing into the editor while ↑↓ steer
the list. `PromptEdit` therefore emits `navigated`/`accepted`/`dismissed`
while `popup_open` is set and lets every other key through; Enter with no
match falls back to sending, so a lone `/` never traps the user. Choosing
inserts `/name ` with a trailing space and the caret at the end — the request
is typed straight after. Ranking is prefix matches first, then substring
matches, capped at `MAX_ROWS`; local skills carry a `local` badge in the
accent colour. The list itself comes from the orchestrator through
`set_skill_source`, like the conversations menu, so `ui/` knows nothing about
registries.

The same popup serves `@` layer mentions. A mention opens at an `@` that starts
the text or follows whitespace (so an e-mail address never does) and closes at
whitespace; choosing replaces only the mention, keeping the rest of the text,
and quotes names with spaces (`@"Main roads"`). Layers come from the
orchestrator through `set_layer_source`. Rows take the mouse too: hover moves
the keyboard selection, a click chooses. Tab only completes — with no match it
does nothing; Enter with no match still sends. The selected row is an
accent-tinted fill, because the card colour on the panel colour is barely
distinguishable in either theme.

## When a run stops

Stop and errors keep the half-streamed answer (`keep_draft`) instead of
dropping it. After an error the orchestrator puts the request back into an
empty composer (`restore`) so a retry is one key; after a stop it does not —
stopping is deliberate, and the request stays visible in the chat.

## The brand mark

`compass.py` is the one source of the mark: the plugin icon (`icon.svg`,
rendered to `icon.png`) repeats its geometry. One live compass per panel —
the status line's, swinging while the agent works; the welcome mark plays
`arrive` once and then rests. Other marks are still pixmaps (`compass.pixmap`).
The halo colour must be the colour under the mark, or the needle's cut in the
ring shows as a stripe.

