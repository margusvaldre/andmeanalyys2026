-- Superseti vaated (käivita PÄRAST init/08_metadata_staging.sql — failinimi 10 > 08).
-- Esimene DB käivitus: tühi content_structure_pct on OK; meta vaated täienevad pärast transformi.

-- Abivaated (tühi DB lubatud).
CREATE OR REPLACE VIEW mart.v_latest_featured_day AS
SELECT MAX(feature_date) AS latest_feature_date
FROM staging.featured_daily;

CREATE OR REPLACE VIEW mart.v_content_latest_day AS
SELECT f.*
FROM mart.fact_content_daily AS f
INNER JOIN mart.v_latest_featured_day AS d
    ON f.activity_date = d.latest_feature_date;

-- Superseti import (enne run-all); transform kirjutab üle.
CREATE OR REPLACE VIEW mart.v_featured_viewership AS
SELECT
    activity_date,
    title_normalized,
    title,
    primary_category_name,
    content_type,
    prominence_score_total,
    views_total,
    views_web,
    views_app
FROM mart.v_content_latest_day
WHERE FALSE;

CREATE OR REPLACE VIEW mart.v_featured_viewership_period AS
SELECT
    'daily'::TEXT AS grain,
    activity_date AS period_start,
    activity_date AS period_end,
    activity_date,
    title_normalized,
    title,
    primary_category_name,
    prominence_score_total,
    views_total,
    (views_total IS NULL) AS viewers_missing,
    false AS in_catalog
FROM mart.v_content_latest_day
WHERE FALSE;

-- Struktuur: vaheversioon enne esimest transformi (ainult content_by_source).
CREATE OR REPLACE VIEW mart.v_superset_structure_pct AS
WITH base AS (
    SELECT
        activity_date,
        CASE source
            WHEN 'catalog' THEN 'Kataloogi struktuur'
            WHEN 'featured' THEN 'Esitatud sisu struktuur'
            WHEN 'viewed' THEN 'Vaadatud sisu struktuur'
        END AS structure_label,
        source,
        CASE
            WHEN source = 'catalog' AND primary_category_name <> ''
                THEN primary_category_name
            WHEN source = 'viewed' AND content_type <> ''
                THEN content_type
            WHEN source = 'featured'
                THEN 'Esiletõstmine (meta puudub)'
            ELSE 'Määramata'
        END AS segment,
        title_count::NUMERIC AS measure_value
    FROM mart.content_by_source
),
totals AS (
    SELECT
        activity_date,
        structure_label,
        SUM(measure_value) AS structure_total
    FROM base
    GROUP BY activity_date, structure_label
)
SELECT
    'daily'::TEXT AS grain,
    b.activity_date AS period_start,
    b.activity_date AS period_end,
    b.activity_date,
    b.structure_label,
    b.source,
    b.segment,
    b.measure_value,
    ROUND(100.0 * b.measure_value / NULLIF(t.structure_total, 0), 2) AS pct
FROM base AS b
INNER JOIN totals AS t
    ON b.activity_date = t.activity_date
   AND b.structure_label = t.structure_label;

DROP VIEW IF EXISTS mart.v_superset_origin_pct;
DROP VIEW IF EXISTS mart.v_superset_content_type_pct;
DROP VIEW IF EXISTS mart.v_superset_featured_top;
DROP VIEW IF EXISTS mart.v_superset_featured_correlation;

CREATE VIEW mart.v_superset_origin_pct AS
SELECT
    'daily'::TEXT AS grain,
    activity_date AS period_start,
    TO_CHAR(activity_date, 'YYYY-MM-DD') AS period_start_key,
    activity_date AS period_end,
    TO_CHAR(activity_date, 'YYYY-MM-DD') AS period_end_key,
    activity_date,
    CASE structure_type
        WHEN 'catalog' THEN 'Kataloogi struktuur'
        WHEN 'presented' THEN 'Esitatud sisu struktuur'
        WHEN 'viewed' THEN 'Vaadatud sisu struktuur'
    END AS structure_label,
    CASE structure_type
        WHEN 'catalog' THEN 1
        WHEN 'presented' THEN 2
        WHEN 'viewed' THEN 3
    END AS structure_sort,
    structure_type,
    category_label AS segment,
    CASE category_code
        WHEN 'EST' THEN 1
        WHEN 'EU' THEN 2
        WHEN 'UK' THEN 3
        WHEN 'REST' THEN 4
        WHEN 'NORDICS' THEN 5
        WHEN 'COPRO' THEN 6
        WHEN 'USACAN' THEN 7
        ELSE 99
    END AS segment_sort,
    measure_value,
    pct
FROM mart.content_structure_pct
WHERE dimension = 'origin_country';

CREATE VIEW mart.v_superset_content_type_pct AS
SELECT
    'daily'::TEXT AS grain,
    activity_date AS period_start,
    TO_CHAR(activity_date, 'YYYY-MM-DD') AS period_start_key,
    activity_date AS period_end,
    TO_CHAR(activity_date, 'YYYY-MM-DD') AS period_end_key,
    activity_date,
    CASE structure_type
        WHEN 'catalog' THEN 'Kataloogi struktuur'
        WHEN 'presented' THEN 'Esitatud sisu struktuur'
        WHEN 'viewed' THEN 'Vaadatud sisu struktuur'
    END AS structure_label,
    CASE structure_type
        WHEN 'catalog' THEN 1
        WHEN 'presented' THEN 2
        WHEN 'viewed' THEN 3
    END AS structure_sort,
    structure_type,
    category_label AS segment,
    CASE category_code
        WHEN 'FILM' THEN 1
        WHEN 'CULTURE' THEN 2
        WHEN 'LIFE' THEN 3
        WHEN 'INFO' THEN 4
        WHEN 'MUSIC' THEN 5
        WHEN 'ENTER' THEN 6
        WHEN 'SERIES' THEN 7
        WHEN 'SPORT' THEN 8
        WHEN 'INFOTAINMENT' THEN 9
        WHEN 'NEWS' THEN 10
        WHEN 'ANIMA' THEN 11
        WHEN 'EDU' THEN 12
        ELSE 99
    END AS segment_sort,
    measure_value,
    pct
FROM mart.content_structure_pct
WHERE dimension = 'content_type';

CREATE OR REPLACE VIEW mart.v_superset_featured_top AS
SELECT
    'daily'::TEXT AS grain,
    v.activity_date AS period_start,
    TO_CHAR(v.activity_date, 'YYYY-MM-DD') AS period_start_key,
    v.activity_date AS period_end,
    TO_CHAR(v.activity_date, 'YYYY-MM-DD') AS period_end_key,
    v.activity_date,
    v.title,
    v.prominence_score_total,
    v.views_total,
    NULL::TEXT AS views_note,
    f.in_catalog,
    v.primary_category_name
FROM mart.v_featured_viewership AS v
INNER JOIN mart.v_content_latest_day AS f
    ON v.title_normalized = f.title_normalized
WHERE FALSE
ORDER BY v.prominence_score_total DESC
LIMIT 50;

CREATE OR REPLACE VIEW mart.v_superset_featured_correlation AS
SELECT
    'daily'::TEXT AS grain,
    activity_date AS period_start,
    TO_CHAR(activity_date, 'YYYY-MM-DD') AS period_start_key,
    activity_date AS period_end,
    TO_CHAR(activity_date, 'YYYY-MM-DD') AS period_end_key,
    activity_date,
    0::BIGINT AS pair_count,
    NULL::DOUBLE PRECISION AS corr_prominence_views
FROM mart.v_content_latest_day
WHERE FALSE;
