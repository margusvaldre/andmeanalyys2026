-- Päevase cron jaoks: üks rida kataloogi kohta, mitte täis snapshot iga käivitusega.
-- Käivita olemasolevas DB-s üks kord:
--   docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/03_catalog_incremental.sql

-- Praegune kataloogi seis (ühendus vaadatavusega: heading ≈ title).
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

-- Logi, kui sama catalog_id puhul muutub pealkiri (heading).
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

-- Valikuline: täida catalog vanast catalog_raw viimasest laadimisest (ühekordne).
INSERT INTO staging.catalog (
    catalog_id,
    schedule_start,
    heading,
    primary_category_name,
    primary_category_path,
    vertical_photo_url,
    source_url,
    first_seen_at,
    last_seen_at
)
SELECT DISTINCT ON (catalog_id)
    catalog_id,
    schedule_start,
    heading,
    primary_category_name,
    primary_category_path,
    vertical_photo_url,
    source_url,
    loaded_at,
    loaded_at
FROM staging.catalog_raw
ORDER BY catalog_id, loaded_at DESC
ON CONFLICT (catalog_id) DO NOTHING;
