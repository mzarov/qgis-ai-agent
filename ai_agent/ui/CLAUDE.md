# ui/ — presentation only

Nothing but rendering logic lives here. No data processing, no LLM calls.

## Rules

1. **No business logic.** UI files only draw components and emit PyQt signals.
   Decisions belong to `core/`.
2. **QGIS wrappers only.** Always `from qgis.PyQt.QtWidgets import ...`.
   Never `PyQt5` or `PyQt6` directly — the Qt version depends on the QGIS build.
3. **No Qt Designer.** Widgets and layouts are built in code; there are no
   `.ui` files.
4. **Colours come from the QGIS theme.** The palette is read through `QPalette`
   in `style.py`. Hard-coded colours are forbidden: the plugin must follow both
   the light and the dark theme. The header icons are drawn in `icons.py` with a
   pen from that same palette rather than taken from
   `QgsApplication.getThemeIcon`: the stock icons are colourful and were drawn
   for a toolbar, so in a compact header they look like three mismatched
   stickers — and they ignore the theme. Outside our own panel the QGIS theme
   is still respected.
5. **Enum compatibility.** Qt5 and Qt6 hold enums differently. Paths like
   `Qt.DockWidgetArea.RightDockWidgetArea` do not exist on Qt5 — wrap them in
   `getattr` with a fallback, as done in `plugin.py`.

## What the interface is made of

| File | What |
| ---- | --- |
| `dock_widget.py`  | the shell: header, feed, composer; conversation menu; the orchestrator contract |
| `conversation.py` | a `QScrollArea` with one widget per message, autoscroll, action grouping |
| `messages.py`     | the user message, the agent reply, the service message |
| `activity.py`     | the collapsible group of tool calls |
| `plan.py`         | the plan card with its buttons inside |
| `composer.py`     | the input box: Enter sends, Shift+Enter breaks the line; the send button turns into “stop” |
| `style.py`        | palette colours; `panel()` — the raised level for dialogs |
| `icons.py`        | header icons: drawn with a palette pen, one stroke weight |
| `settings_dialog.py` | the settings window: state, saving, the connection probe |
| `settings_layout.py` | the sidebar, the page stack and per-page scrolling |
| `settings_fields.py` | the row grammar: rows, switches, separators, inputs, buttons |
| `settings_advanced.py` | the Privacy and Advanced pages |
| `geocoder_settings.py` | the Geocoding page |

## Header icons

The three icons — a clock for conversations, a bin for clearing, a gear for
settings — are drawn with `QPainter` on a 16×16 canvas with a single pen of
width 1.45 in the `style.muted` colour. Hence the consistency: one stroke
weight, one colour, one optical density. The whole set is outline-only; no
shape carries a fill.

The gear teeth are computed with trigonometry rather than written out as
coordinates, so they are also verified with arithmetic: every vertex inside the
canvas, the hub inside the ring, and the distance between vertices above three
pixels at icon size 15 — otherwise the teeth merge into a blob.

The pixmap is created with the screen's `devicePixelRatio`, otherwise the icons
blur on retina. The ratio is sanity-checked: outside 1…4 it falls back to one.

**The screen multiplier participates only in the pixmap size, never in the
transform.** A `QPainter` on a pixmap with a set `devicePixelRatio` already
works in logical coordinates — Qt applies the multiplier itself. Multiplying by
it again in `painter.scale` draws twice as large and crops to the top-left
corner; invisible on a normal screen, obvious on retina. Hence
`scale_for(size) = size / CANVAS` with no ratio at all, and an invariant test:
the canvas must map onto the icon exactly.

If painting fails for any reason, the button shows a text glyph — the same
fallback that existed with theme icons. Geometry is guarded by
`tests/test_icons.py`: every point must lie inside the canvas, the set carries
one pen weight, and the brush returns to `NoBrush` after the filled slider,
otherwise the next shape gets flooded.

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
activity group as a frameless row, so a whole think–act–think–act chain folds
into one box. The group opens itself while reasoning streams and `_close_activity`
rests it when a message arrives — the feed stays compact without hiding anything:
one click reopens the turn.

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

The design language follows Claude Code's own feed: transient rows — the
activity group and the thinking block inside it — are **plain muted text with a
chevron**, no background and no border. Boxing every turn made the feed read as
a wall of cards; the frames carried no meaning. A frame is reserved for the one
thing that asks the user to act: the plan card keeps its hairline border (and
nothing else — its fill is transparent too). If a new element wants a frame,
the question to ask is "does it hold buttons?" — if not, it is a line, not a
box.

## Action grouping

`ConversationView` itself folds consecutive tool calls into one
`ActivityGroup`. Any message of another kind closes the group. So the
orchestrator still calls `add_tool_message` per call and knows nothing about
grouping.

## The plan card

The Apply and Cancel buttons live inside `PlanCard`, not as a separate row at
the bottom of the panel. The card emits signals upwards; the dock re-emits them
under the same names as before. After applying or cancelling the buttons
disappear and the title shows the outcome — the conversation history stays
honest.

## One button for send and stop

While the agent works, the send button does not grey out — it becomes “stop”:
the glyph, the colour and the tooltip change. There is deliberately no separate
button — it would be visible always and inactive most of the time. Enter is
ignored while a run is active.

## The conversations menu

The Conversations button in the header builds its menu at click time instead of
keeping a list: it goes stale with every agent reply. The list comes from the
orchestrator through `set_session_source` — the provider returns
`(identifier, title)` pairs so that no `core/` types leak into `ui/`.

## The settings window

**A sidebar over a page stack, styled after Claude's own settings.** Four
entries — Connection, Privacy, Geocoding, Advanced — ordered by how often each
is touched. Sidebar and pages sit **full-bleed on the same window surface**,
split by one vertical hairline; the footer is cut off by a horizontal one.
A floating lifted pane was tried between the tab and this version and looked
worse than both — a box inside a box reads as a widget, not a page. The
selected entry is a `panel()` pill plus bold, so the selection survives the
light theme where the lift is zero. The sidebar carries **no heading**: the
window is already titled Settings, and repeating the word inside it was
noise.

**One row grammar for every control.** A row is caption left (title plus a
muted hint under it, both wrapping), control right at a fixed
`CONTROL_WIDTH`, vertically centred. Uniform control width is what makes the
pages read as straight columns instead of ragged boxes. `add_rows`
interleaves hairline separators **between** rows, never after the last one.
Each page starts with one bold `group()` header; a page never repeats its
sidebar entry as a heading.

**Booleans are drawn switches, not native checkboxes.** A stray blue
checkbox at the end of a wide row reads as debris; a track-and-knob toggle
reads as a setting. `Switch` subclasses `QCheckBox` — the whole checkbox API
(`setChecked`, `toggled`, `setEnabled`) keeps working — and only replaces
`paintEvent`: accent track when on, hairline track when off, `card()` when
disabled, knob from `highlightedText`. Same approach as the header icons:
palette-driven `QPainter`, no image assets.

Descriptions live behind a small "?" mark after the title, shown on hover —
a page of stacked explanatory paragraphs read as a wall of text (the user's
call, and they were right). The safety-critical explanation of the sensitive
switch is not lost to the tooltip: the per-endpoint consent dialog spells out
the same boundary before the first request is ever sent. The geocoder's hint
changes with the chosen provider, so its row keeps a reference to the mark
and rewrites the tooltip. Inside the caption the title label owns the
stretch — a word-wrapping `QLabel` next to an `addStretch` gets squeezed to
its minimum and wraps with half the row empty; giving the label the stretch
makes wrapping happen only when the window is genuinely narrow, and lines
the "?" marks up in one column before the controls.

Pages scroll individually (`scrollable()`), with the viewport forced
transparent so the window surface shows through — a `QScrollArea` left to
its own devices paints its own grey. Test connection lives on the
Connection page — it tests exactly what that page edits and means nothing on
the others. The status line and Save/Close stay in the footer under a full
hairline, so the probe's answer is visible from any page and survives page
switches.

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
