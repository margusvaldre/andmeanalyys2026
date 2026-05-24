-- Sisu metaandmed CSV-st (data/metadata/jupiter_metadata.csv).
-- Ühendusvõti: title ≈ kataloogi heading ja teiste allikate title.

CREATE TABLE IF NOT EXISTS staging.content_metadata (
    title TEXT PRIMARY KEY,
    updated_at DATE NOT NULL,
    origin_code TEXT NOT NULL,
    content_type_code TEXT NOT NULL,
    source_file TEXT NOT NULL,
    run_id UUID NOT NULL REFERENCES staging.pipeline_runs (run_id),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_content_metadata_origin
    ON staging.content_metadata (origin_code);

CREATE INDEX IF NOT EXISTS idx_content_metadata_type
    ON staging.content_metadata (content_type_code);

-- Viitekoodid → eestikeelsed sildid (mart.dim_content ja Superseti vaated v_superset_*_pct).
CREATE TABLE IF NOT EXISTS mart.ref_origin_labels (
    origin_code TEXT PRIMARY KEY,
    origin_label TEXT NOT NULL
);

INSERT INTO mart.ref_origin_labels (origin_code, origin_label) VALUES
    ('EST', 'Eesti'),
    ('EU', 'Euroopa Liit'),
    ('UK', 'Ühendkuningriik'),
    ('USACAN', 'USA ja Kanada'),
    ('NORDICS', 'Põhjamaad'),
    ('COPRO', 'Kaastootmine'),
    ('REST', 'Ülejäänud maailm')
ON CONFLICT (origin_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS mart.ref_content_type_labels (
    content_type_code TEXT PRIMARY KEY,
    content_type_label TEXT NOT NULL
);

INSERT INTO mart.ref_content_type_labels (content_type_code, content_type_label) VALUES
    ('FILM', 'Filmid ja näidendid'),
    ('CULTURE', 'Kultuur'),
    ('LIFE', 'Elu'),
    ('INFO', 'Info'),
    ('MUSIC', 'Muusika'),
    ('ENTER', 'Meelelahutus'),
    ('SERIES', 'Sarjad'),
    ('SPORT', 'Sport'),
    ('INFOTAINMENT', 'Infotainment'),
    ('NEWS', 'Uudised'),
    ('ANIMA', 'Anima'),
    ('EDU', 'Haridus')
ON CONFLICT (content_type_code) DO NOTHING;

-- Normaliseeri tüübikood (CSV sisaldab mõnikord kirjavea CULTRURE).
CREATE OR REPLACE FUNCTION mart.normalize_content_type_code(raw_code TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE upper(trim(COALESCE(raw_code, '')))
        WHEN 'CULTRURE' THEN 'CULTURE'
        WHEN '' THEN NULL
        ELSE upper(trim(raw_code))
    END;
$$;

-- Laienda dim_content meta väljadega (olemasolev DB).
ALTER TABLE mart.dim_content
    ADD COLUMN IF NOT EXISTS origin_code TEXT,
    ADD COLUMN IF NOT EXISTS origin_country TEXT,
    ADD COLUMN IF NOT EXISTS meta_content_type TEXT,
    ADD COLUMN IF NOT EXISTS meta_updated_at DATE,
    ADD COLUMN IF NOT EXISTS in_metadata BOOLEAN NOT NULL DEFAULT false;

-- Struktuuri % küsimuse 1 diagrammide jaoks.
CREATE TABLE IF NOT EXISTS mart.content_structure_pct (
    activity_date DATE NOT NULL,
    structure_type TEXT NOT NULL
        CHECK (structure_type IN ('catalog', 'presented', 'viewed')),
    dimension TEXT NOT NULL
        CHECK (dimension IN ('origin_country', 'content_type')),
    category_code TEXT NOT NULL,
    category_label TEXT NOT NULL,
    measure_value NUMERIC NOT NULL,
    pct NUMERIC(5, 2) NOT NULL,
    transformed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (activity_date, structure_type, dimension, category_code)
);

CREATE INDEX IF NOT EXISTS idx_content_structure_pct_lookup
    ON mart.content_structure_pct (activity_date, dimension, structure_type);
