-- Vaadatavuse staging (käivita olemasolevas DB-s, kui 01_create_objects.sql on juba käinud).
-- Kasuta seda faili, kui andmebaas loodi enne viewers_raw tabeli lisamist.

CREATE TABLE IF NOT EXISTS staging.viewers_raw (
    run_id UUID NOT NULL REFERENCES staging.pipeline_runs (run_id),
    grain TEXT NOT NULL CHECK (grain IN ('daily', 'weekly')),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    view_date DATE NOT NULL,
    content_type TEXT,
    title TEXT NOT NULL,
    total INTEGER NOT NULL,
    live INTEGER NOT NULL,
    od INTEGER NOT NULL,
    web INTEGER NOT NULL,
    app INTEGER NOT NULL,
    source_file TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, grain, period_start, period_end, title)
);

CREATE INDEX IF NOT EXISTS idx_viewers_raw_title
    ON staging.viewers_raw (title);

CREATE INDEX IF NOT EXISTS idx_viewers_raw_grain_period
    ON staging.viewers_raw (grain, period_start, period_end);
