-- Esiletõstmise päevane snapshot (käivita olemasolevas DB-s, kui tabel puudub).

CREATE TABLE IF NOT EXISTS staging.featured_daily (
    feature_date DATE NOT NULL,
    title TEXT NOT NULL,
    prominence_score_total NUMERIC(12, 4) NOT NULL,
    poster_url TEXT,
    run_id UUID NOT NULL REFERENCES staging.pipeline_runs (run_id),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (feature_date, title)
);

CREATE INDEX IF NOT EXISTS idx_featured_daily_title
    ON staging.featured_daily (title);

CREATE INDEX IF NOT EXISTS idx_featured_daily_loaded_at
    ON staging.featured_daily (loaded_at DESC);
