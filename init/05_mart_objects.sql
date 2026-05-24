-- Mart kiht: analüütika tabelid (täidetakse scripts/01_transform.sql abil).

-- Ühtne pealkirja normaliseerimine ühenduste jaoks (trim + üleliigsed tühikud).
CREATE OR REPLACE FUNCTION mart.normalize_title(raw_title TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT NULLIF(regexp_replace(trim(raw_title), '\s+', ' ', 'g'), '');
$$;

-- Üks rida iga unikaalse pealkirja kohta (kataloog + esiletõstmine + vaadatavus).
CREATE TABLE IF NOT EXISTS mart.dim_content (
    title_normalized TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    catalog_id TEXT,
    primary_category_name TEXT,
    primary_category_path TEXT,
    in_catalog BOOLEAN NOT NULL DEFAULT false,
    in_featured BOOLEAN NOT NULL DEFAULT false,
    in_viewers_daily BOOLEAN NOT NULL DEFAULT false,
    transformed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Päevane fakt: esiletõstmine + vaadatavus + kataloogi kategooria (kui leidub).
CREATE TABLE IF NOT EXISTS mart.fact_content_daily (
    activity_date DATE NOT NULL,
    title_normalized TEXT NOT NULL,
    title TEXT NOT NULL,
    catalog_id TEXT,
    primary_category_name TEXT,
    primary_category_path TEXT,
    content_type TEXT,
    prominence_score_total NUMERIC(12, 4),
    views_total INTEGER,
    views_live INTEGER,
    views_od INTEGER,
    views_web INTEGER,
    views_app INTEGER,
    in_catalog BOOLEAN NOT NULL DEFAULT false,
    in_featured BOOLEAN NOT NULL DEFAULT false,
    in_viewers BOOLEAN NOT NULL DEFAULT false,
    transformed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (activity_date, title_normalized)
);

CREATE INDEX IF NOT EXISTS idx_fact_content_daily_date
    ON mart.fact_content_daily (activity_date);

CREATE INDEX IF NOT EXISTS idx_fact_content_daily_category
    ON mart.fact_content_daily (primary_category_name);

-- Struktuuri võrdlus: mitu pealkirja allikas × kategooria/tüüp kohta.
CREATE TABLE IF NOT EXISTS mart.content_by_source (
    activity_date DATE NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('catalog', 'featured', 'viewed')),
    primary_category_name TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT '',
    title_count INTEGER NOT NULL,
    transformed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (activity_date, source, primary_category_name, content_type)
);

-- Ühenduste kvaliteet päeva kohta (match rate).
CREATE TABLE IF NOT EXISTS mart.title_match_daily (
    activity_date DATE PRIMARY KEY,
    featured_count INTEGER NOT NULL,
    catalog_match_count INTEGER NOT NULL,
    viewers_match_count INTEGER NOT NULL,
    both_metrics_count INTEGER NOT NULL,
    catalog_match_pct NUMERIC(5, 2),
    viewers_match_pct NUMERIC(5, 2),
    transformed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
