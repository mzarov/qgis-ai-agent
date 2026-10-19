-- Usage statistics storage. The deploy workflow applies this file on every
-- run, so every statement must be idempotent.

-- One row per install and day; a resend for the same day replaces the row.
-- install_hash is the SHA-256 hex of the install UUID: the UUID itself is
-- never stored, and neither is an IP address or a time finer than the day.
CREATE TABLE IF NOT EXISTS pings (
  install_hash TEXT NOT NULL,
  day TEXT NOT NULL,
  plugin TEXT NOT NULL,
  qgis TEXT NOT NULL,
  os TEXT NOT NULL,
  locale TEXT NOT NULL,
  provider TEXT NOT NULL,
  dialect TEXT NOT NULL,
  runs INTEGER NOT NULL,
  applies INTEGER NOT NULL,
  tools TEXT NOT NULL DEFAULT '{}',
  skills TEXT NOT NULL DEFAULT '{}',
  failures TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (install_hash, day)
);

-- Every aggregate reads a window of days; install_hash makes the index
-- covering for the distinct-install counts.
CREATE INDEX IF NOT EXISTS pings_day ON pings (day, install_hash);

-- The last computed /v1/stats document, so the aggregates are rebuilt at most
-- once an hour however many people open the dashboard.
CREATE TABLE IF NOT EXISTS stats_snapshot (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  generated TEXT NOT NULL,
  body TEXT NOT NULL
);

-- Fields added in ping v2, a table of its own because ADD COLUMN fails when this file runs again.
CREATE TABLE IF NOT EXISTS ping_extras (
  install_hash TEXT NOT NULL,
  day TEXT NOT NULL,
  configured INTEGER NOT NULL,
  tool_errors TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (install_hash, day)
);
