---
name: charts
description: Draw charts and tables right in the chat — a histogram of a field, values per category as bars or a pie, a line over time, a table of chosen features. Load this when the user asks to plot, chart, graph or tabulate data, or when a comparison reads better as a picture than as a sentence.
tools: [chart_layer, show_chart, show_table]
---

# Charts and tables in the chat

The person sees the chart or table in the feed; you get a short confirmation
with the numbers. After drawing, add one sentence that says what the chart
shows — the pattern, the leader, the outlier — not a description of the chart.

## Which tool

- **The numbers are in a layer:** `chart_layer`. It computes and draws in one
  step, so the values never travel through you. `value` without `group_by`
  draws a histogram of that field or expression; `group_by` draws one bar per
  category: `count` of features, or `sum`/`mean`/`min`/`max` of `value`.
  Expressions work: `value="$area / 1e6"` for km², `$length / 1000` for km.
- **You already have the numbers** (from query_layer, a calculation, the user):
  `show_chart` with `labels` and `series`.
- **Rows the person should read:** `show_table` with the fields, a filter and
  `order_by` — "the ten largest" is `order_by="pop2020 desc"`, `limit=10`. The
  person sees every row; you get the first three.

## Picking the form

- Compare categories → bars (the default). Long category names lay out as rows
  by themselves.
- Shares of a whole, at most seven parts → pie. More parts fold into "Other";
  for many categories prefer bars.
- Change over time or an ordered sequence → line, labels in order.
- Distribution of one numeric field → histogram (`chart_layer` without
  `group_by`).
- Relationship of two numeric fields → scatter, at most three series.

## Rules

- One measure per chart. Never put values of different units on one axis
  (population and area): draw two charts.
- Put the unit in `title` or `unit`: "Population 2020, people", "km²".
- Sort categories by value unless their order means something (months,
  classes): `chart_layer` already sorts by size.
- Do not repeat every value in your answer — the chart carries them.
