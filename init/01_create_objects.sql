-- Jupiteri andmeanalüüsi projekt: skeemid ja staging tabelid.
-- See fail jookseb PostgreSQL konteineri esmakordsel käivitamisel.

-- staging = toorandmed allikatest (API, CSV)
-- mart     = transformeeritud analüütika (tuleb hiljem SQL-iga)
-- quality  = andmekvaliteedi testide tulemused (vt init/07_quality_objects.sql)

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS quality;

-- Iga ingest-skript (kataloog, vaadatavus) kirjutab siia ühe rea.
-- run_id seob kõik sama käivituse read omavahel.
CREATE TABLE IF NOT EXISTS staging.pipeline_runs (
    run_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    source_name TEXT NOT NULL,
    status TEXT NOT NULL,
    row_count INTEGER,
    message TEXT
);

-- Videokataloog API-st. Pealkiri on väli `heading`.
-- Hiljem ühendatakse vaadatavusega võtmega title ≈ heading.
CREATE TABLE IF NOT EXISTS staging.catalog_raw (
    run_id UUID NOT NULL REFERENCES staging.pipeline_runs (run_id),
    catalog_id TEXT NOT NULL,
    schedule_start TEXT,
    heading TEXT NOT NULL,
    primary_category_name TEXT,
    primary_category_path TEXT,
    vertical_photo_url TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_url TEXT NOT NULL,
    PRIMARY KEY (run_id, catalog_id)
);

CREATE INDEX IF NOT EXISTS idx_catalog_raw_heading
    ON staging.catalog_raw (heading);

CREATE INDEX IF NOT EXISTS idx_catalog_raw_loaded_at
    ON staging.catalog_raw (loaded_at DESC);

-- Päevase cron jaoks: üks rida catalog_id kohta (ainult uued read + pealkirja muutuste logi).
-- Vanem catalog_raw jäetakse alles, kuid ingest kasutab staging.catalog.
CREATE TABLE IF NOT EXISTS staging.catalog (
    catalog_id TEXT PRIMARY KEY,
    schedule_start TEXT,
    heading TEXT NOT NULL,
    primary_category_name TEXT,
    primary_category_path TEXT,
    vertical_photo_url TEXT,
    source_url TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_catalog_heading
    ON staging.catalog (heading);

CREATE TABLE IF NOT EXISTS staging.catalog_title_changes (
    change_id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES staging.pipeline_runs (run_id),
    catalog_id TEXT NOT NULL REFERENCES staging.catalog (catalog_id),
    old_heading TEXT NOT NULL,
    new_heading TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_catalog_title_changes_catalog
    ON staging.catalog_title_changes (catalog_id);

-- Vaadatavus CSV-st. grain = daily või weekly (eraldi failitüübid).
-- title on ühendusvõti kataloogi ja (hiljem) meta CSV-ga.
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

-- Esiletõstmine (prominence) API-st. Üks rida = pealkiri ühel päeval.
-- Iga cron käivitus asendab sama feature_date read uutega.
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
