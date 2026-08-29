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
| `settings_dialog.py` | the settings window: provider, key, API format |
| `settings_fields.py` | cards, labels, hints and buttons for the settings |

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

Drop and fold are different on purpose. A draft is text the model wrote before
calling a tool: it is a preamble, not an answer, and it is **dropped**, because
the saved conversation never contains it and the chat must not show what the
conversation lacks. A thinking block is **folded** — it stays in the feed as
one line the user can open again. The block shows how long it took only when
it was watched arriving: reasoning that came whole at the end of a
non-streaming request has no measurable duration, and printing `0.0 s` for a
minute of thought would be a lie.

## The empty state fills the panel

`WelcomeCard` is not a small card pinned to the top: with an empty feed it takes
the whole height and centres its own content, because a compact card left two
thirds of the panel as a void and read as a rendering fault rather than as a
starting point. The feed's trailing stretch is what fought it — while the
welcome is shown that stretch drops to zero and the card carries the stretch
instead; `_drop_welcome` hands it back. Both live in one pair of methods so the
two states cannot drift apart.

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

Fields are grouped into cards, each with a small hint underneath. The provider
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
