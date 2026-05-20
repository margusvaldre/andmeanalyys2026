-- Transformatsioon: staging -> mart
-- Käivita pärast ingest-all:
--   docker compose exec pipeline python scripts/run_pipeline.py transform

TRUNCATE TABLE
    mart.content_structure_pct,
    mart.title_match_daily,
    mart.content_by_source,
    mart.fact_content_daily,
    mart.dim_content;

-- Viimane vaadatavuse päevane laadimine iga (periood, pealkiri) kohta.
WITH viewers_daily AS (
    SELECT DISTINCT ON (period_start, period_end, title)
        period_start,
        period_end,
        view_date,
        content_type,
        title,
        total,
        live,
        od,
        web,
        app
    FROM staging.viewers_raw
    WHERE grain = 'daily'
    ORDER BY period_start, period_end, title, loaded_at DESC
),

catalog_norm AS (
    SELECT DISTINCT ON (mart.normalize_title(heading))
        catalog_id,
        heading,
        mart.normalize_title(heading) AS title_normalized,
        primary_category_name,
        primary_category_path
    FROM staging.catalog
    WHERE mart.normalize_title(heading) IS NOT NULL
    ORDER BY mart.normalize_title(heading), catalog_id
),

featured_norm AS (
    SELECT
        feature_date,
        title,
        mart.normalize_title(title) AS title_normalized,
        prominence_score_total,
        poster_url
    FROM staging.featured_daily
    WHERE mart.normalize_title(title) IS NOT NULL
),

meta_norm AS (
    SELECT
        title,
        mart.normalize_title(title) AS title_normalized,
        updated_at,
        origin_code,
        mart.normalize_content_type_code(content_type_code) AS content_type_code
    FROM staging.content_metadata
    WHERE mart.normalize_title(title) IS NOT NULL
),

viewers_norm AS (
    SELECT
        view_date,
        title,
        mart.normalize_title(title) AS title_normalized,
        content_type,
        total,
        live,
        od,
        web,
        app
    FROM viewers_daily
    WHERE mart.normalize_title(title) IS NOT NULL
),

-- Kõik pealkirjad, mis esinevad vähemalt ühes allikas.
all_titles AS (
    SELECT title_normalized, heading AS title, catalog_id, primary_category_name, primary_category_path
    FROM catalog_norm
    UNION
    SELECT title_normalized, title, NULL::TEXT, NULL::TEXT, NULL::TEXT
    FROM featured_norm
    UNION
    SELECT title_normalized, title, NULL::TEXT, NULL::TEXT, NULL::TEXT
    FROM viewers_norm
    UNION
    SELECT title_normalized, title, NULL::TEXT, NULL::TEXT, NULL::TEXT
    FROM meta_norm
),

dim_ranked AS (
    SELECT
        title_normalized,
        title,
        catalog_id,
        primary_category_name,
        primary_category_path,
        ROW_NUMBER() OVER (
            PARTITION BY title_normalized
            ORDER BY
                CASE WHEN catalog_id IS NOT NULL THEN 0 ELSE 1 END,
                title
        ) AS rn
    FROM all_titles
)

INSERT INTO mart.dim_content (
    title_normalized,
    title,
    catalog_id,
    primary_category_name,
    primary_category_path,
    origin_code,
    origin_country,
    meta_content_type,
    meta_updated_at,
    in_catalog,
    in_featured,
    in_viewers_daily,
    in_metadata,
    transformed_at
)
SELECT
    d.title_normalized,
    d.title,
    c.catalog_id,
    c.primary_category_name,
    c.primary_category_path,
    m.origin_code,
    ol.origin_label,
    tl.content_type_label,
    m.updated_at,
    c.title_normalized IS NOT NULL AS in_catalog,
    f.title_normalized IS NOT NULL AS in_featured,
    v.title_normalized IS NOT NULL AS in_viewers_daily,
    m.title_normalized IS NOT NULL AS in_metadata,
    now() AS transformed_at
FROM dim_ranked AS d
LEFT JOIN catalog_norm AS c
    ON d.title_normalized = c.title_normalized
LEFT JOIN (SELECT DISTINCT title_normalized FROM featured_norm) AS f
    ON d.title_normalized = f.title_normalized
LEFT JOIN (SELECT DISTINCT title_normalized FROM viewers_norm) AS v
    ON d.title_normalized = v.title_normalized
LEFT JOIN meta_norm AS m
    ON d.title_normalized = m.title_normalized
LEFT JOIN mart.ref_origin_labels AS ol
    ON m.origin_code = ol.origin_code
LEFT JOIN mart.ref_content_type_labels AS tl
    ON m.content_type_code = tl.content_type_code
WHERE d.rn = 1;

-- Päevane spinaal: esiletõstmise päevad + vaadatavuse päevad.
WITH viewers_daily AS (
    SELECT DISTINCT ON (period_start, period_end, title)
        view_date,
        content_type,
        title,
        total,
        live,
        od,
        web,
        app
    FROM staging.viewers_raw
    WHERE grain = 'daily'
    ORDER BY period_start, period_end, title, loaded_at DESC
),

featured_norm AS (
    SELECT
        feature_date,
        title,
        mart.normalize_title(title) AS title_normalized,
        prominence_score_total
    FROM staging.featured_daily
    WHERE mart.normalize_title(title) IS NOT NULL
),

viewers_norm AS (
    SELECT
        view_date,
        title,
        mart.normalize_title(title) AS title_normalized,
        content_type,
        total,
        live,
        od,
        web,
        app
    FROM viewers_daily
    WHERE mart.normalize_title(title) IS NOT NULL
),

catalog_norm AS (
    SELECT DISTINCT ON (mart.normalize_title(heading))
        catalog_id,
        heading,
        mart.normalize_title(heading) AS title_normalized,
        primary_category_name,
        primary_category_path
    FROM staging.catalog
    WHERE mart.normalize_title(heading) IS NOT NULL
    ORDER BY mart.normalize_title(heading), catalog_id
),

daily_spine AS (
    SELECT feature_date AS activity_date, title_normalized
    FROM featured_norm
    UNION
    SELECT view_date AS activity_date, title_normalized
    FROM viewers_norm
)

INSERT INTO mart.fact_content_daily (
    activity_date,
    title_normalized,
    title,
    catalog_id,
    primary_category_name,
    primary_category_path,
    content_type,
    prominence_score_total,
    views_total,
    views_live,
    views_od,
    views_web,
    views_app,
    in_catalog,
    in_featured,
    in_viewers,
    transformed_at
)
SELECT
    s.activity_date,
    s.title_normalized,
    COALESCE(c.heading, f.title, v.title, d.title) AS title,
    c.catalog_id,
    c.primary_category_name,
    c.primary_category_path,
    v.content_type,
    f.prominence_score_total,
    v.total AS views_total,
    v.live AS views_live,
    v.od AS views_od,
    v.web AS views_web,
    v.app AS views_app,
    c.title_normalized IS NOT NULL AS in_catalog,
    f.title_normalized IS NOT NULL AS in_featured,
    v.title_normalized IS NOT NULL AS in_viewers,
    now() AS transformed_at
FROM daily_spine AS s
LEFT JOIN featured_norm AS f
    ON s.activity_date = f.feature_date
   AND s.title_normalized = f.title_normalized
LEFT JOIN viewers_norm AS v
    ON s.activity_date = v.view_date
   AND s.title_normalized = v.title_normalized
LEFT JOIN catalog_norm AS c
    ON s.title_normalized = c.title_normalized
LEFT JOIN mart.dim_content AS d
    ON s.title_normalized = d.title_normalized;

-- Struktuur: kataloog (praegune seis), esiletõstmine ja vaadatavus päeva lõikes.
INSERT INTO mart.content_by_source (
    activity_date,
    source,
    primary_category_name,
    content_type,
    title_count,
    transformed_at
)
SELECT
    CURRENT_DATE AS activity_date,
    'catalog' AS source,
    COALESCE(primary_category_name, '') AS primary_category_name,
    '' AS content_type,
    COUNT(*)::INTEGER AS title_count,
    now() AS transformed_at
FROM staging.catalog
GROUP BY COALESCE(primary_category_name, '')

UNION ALL

SELECT
    feature_date AS activity_date,
    'featured' AS source,
    '' AS primary_category_name,
    '' AS content_type,
    COUNT(*)::INTEGER AS title_count,
    now() AS transformed_at
FROM staging.featured_daily
GROUP BY feature_date

UNION ALL

SELECT
    view_date AS activity_date,
    'viewed' AS source,
    '' AS primary_category_name,
    COALESCE(content_type, '') AS content_type,
    COUNT(*)::INTEGER AS title_count,
    now() AS transformed_at
FROM (
    SELECT DISTINCT ON (period_start, period_end, title)
        view_date,
        content_type,
        title
    FROM staging.viewers_raw
    WHERE grain = 'daily'
    ORDER BY period_start, period_end, title, loaded_at DESC
) AS latest_viewers
GROUP BY view_date, COALESCE(content_type, '');

-- Match rate päeva kohta (esiletõstmise read).
INSERT INTO mart.title_match_daily (
    activity_date,
    featured_count,
    catalog_match_count,
    viewers_match_count,
    both_metrics_count,
    catalog_match_pct,
    viewers_match_pct,
    transformed_at
)
SELECT
    activity_date,
    COUNT(*) FILTER (WHERE in_featured) AS featured_count,
    COUNT(*) FILTER (WHERE in_featured AND in_catalog) AS catalog_match_count,
    COUNT(*) FILTER (WHERE in_featured AND in_viewers) AS viewers_match_count,
    COUNT(*) FILTER (
        WHERE in_featured
          AND prominence_score_total IS NOT NULL
          AND views_total IS NOT NULL
    ) AS both_metrics_count,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE in_featured AND in_catalog)
        / NULLIF(COUNT(*) FILTER (WHERE in_featured), 0),
        2
    ) AS catalog_match_pct,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE in_featured AND in_viewers)
        / NULLIF(COUNT(*) FILTER (WHERE in_featured), 0),
        2
    ) AS viewers_match_pct,
    now() AS transformed_at
FROM mart.fact_content_daily
WHERE in_featured
GROUP BY activity_date;

-- Struktuuri protsendid meta CSV põhjal (küsimus 1 diagrammid).
WITH latest_day AS (
    SELECT COALESCE(MAX(feature_date), CURRENT_DATE) AS activity_date
    FROM staging.featured_daily
),

meta AS (
    SELECT
        mart.normalize_title(title) AS title_normalized,
        origin_code,
        mart.normalize_content_type_code(content_type_code) AS content_type_code
    FROM staging.content_metadata
    WHERE mart.normalize_title(title) IS NOT NULL
),

viewers_latest AS (
    SELECT DISTINCT ON (period_start, period_end, title)
        view_date,
        title,
        total
    FROM staging.viewers_raw
    WHERE grain = 'daily'
    ORDER BY period_start, period_end, title, loaded_at DESC
),

structure_counts AS (
    -- Kataloog: pealkirjade arv
    SELECT
        ld.activity_date,
        'catalog'::TEXT AS structure_type,
        'origin_country'::TEXT AS dimension,
        m.origin_code AS category_code,
        COALESCE(ol.origin_label, m.origin_code) AS category_label,
        COUNT(*)::NUMERIC AS measure_value
    FROM staging.catalog AS c
    INNER JOIN meta AS m
        ON mart.normalize_title(c.heading) = m.title_normalized
    CROSS JOIN latest_day AS ld
    LEFT JOIN mart.ref_origin_labels AS ol
        ON m.origin_code = ol.origin_code
    GROUP BY ld.activity_date, m.origin_code, ol.origin_label

    UNION ALL

    SELECT
        ld.activity_date,
        'catalog',
        'content_type',
        m.content_type_code,
        COALESCE(tl.content_type_label, m.content_type_code),
        COUNT(*)::NUMERIC
    FROM staging.catalog AS c
    INNER JOIN meta AS m
        ON mart.normalize_title(c.heading) = m.title_normalized
    CROSS JOIN latest_day AS ld
    LEFT JOIN mart.ref_content_type_labels AS tl
        ON m.content_type_code = tl.content_type_code
    GROUP BY ld.activity_date, m.content_type_code, tl.content_type_label

    UNION ALL

    -- Esitatud: esiletõstmise pealkirjad viimase päeva kohta
    SELECT
        ld.activity_date,
        'presented',
        'origin_country',
        m.origin_code,
        COALESCE(ol.origin_label, m.origin_code),
        COUNT(*)::NUMERIC
    FROM staging.featured_daily AS f
    INNER JOIN meta AS m
        ON mart.normalize_title(f.title) = m.title_normalized
    CROSS JOIN latest_day AS ld
    LEFT JOIN mart.ref_origin_labels AS ol
        ON m.origin_code = ol.origin_code
    WHERE f.feature_date = ld.activity_date
    GROUP BY ld.activity_date, m.origin_code, ol.origin_label

    UNION ALL

    SELECT
        ld.activity_date,
        'presented',
        'content_type',
        m.content_type_code,
        COALESCE(tl.content_type_label, m.content_type_code),
        COUNT(*)::NUMERIC
    FROM staging.featured_daily AS f
    INNER JOIN meta AS m
        ON mart.normalize_title(f.title) = m.title_normalized
    CROSS JOIN latest_day AS ld
    LEFT JOIN mart.ref_content_type_labels AS tl
        ON m.content_type_code = tl.content_type_code
    WHERE f.feature_date = ld.activity_date
    GROUP BY ld.activity_date, m.content_type_code, tl.content_type_label

    UNION ALL

    -- Vaadatud: vaatamiste summa viimase päeva kohta
    SELECT
        ld.activity_date,
        'viewed',
        'origin_country',
        m.origin_code,
        COALESCE(ol.origin_label, m.origin_code),
        SUM(v.total)::NUMERIC
    FROM viewers_latest AS v
    INNER JOIN meta AS m
        ON mart.normalize_title(v.title) = m.title_normalized
    CROSS JOIN latest_day AS ld
    LEFT JOIN mart.ref_origin_labels AS ol
        ON m.origin_code = ol.origin_code
    WHERE v.view_date = ld.activity_date
    GROUP BY ld.activity_date, m.origin_code, ol.origin_label

    UNION ALL

    SELECT
        ld.activity_date,
        'viewed',
        'content_type',
        m.content_type_code,
        COALESCE(tl.content_type_label, m.content_type_code),
        SUM(v.total)::NUMERIC
    FROM viewers_latest AS v
    INNER JOIN meta AS m
        ON mart.normalize_title(v.title) = m.title_normalized
    CROSS JOIN latest_day AS ld
    LEFT JOIN mart.ref_content_type_labels AS tl
        ON m.content_type_code = tl.content_type_code
    WHERE v.view_date = ld.activity_date
    GROUP BY ld.activity_date, m.content_type_code, tl.content_type_label
),

structure_totals AS (
    SELECT
        activity_date,
        structure_type,
        dimension,
        SUM(measure_value) AS structure_total
    FROM structure_counts
    GROUP BY activity_date, structure_type, dimension
)

INSERT INTO mart.content_structure_pct (
    activity_date,
    structure_type,
    dimension,
    category_code,
    category_label,
    measure_value,
    pct,
    transformed_at
)
SELECT
    sc.activity_date,
    sc.structure_type,
    sc.dimension,
    sc.category_code,
    sc.category_label,
    sc.measure_value,
    ROUND(100.0 * sc.measure_value / NULLIF(st.structure_total, 0), 2) AS pct,
    now() AS transformed_at
FROM structure_counts AS sc
INNER JOIN structure_totals AS st
    ON sc.activity_date = st.activity_date
   AND sc.structure_type = st.structure_type
   AND sc.dimension = st.dimension;

-- Vaated Superseti jaoks.

CREATE OR REPLACE VIEW mart.v_content_daily AS
SELECT *
FROM mart.fact_content_daily;

-- Ainult read, kus on nii esiletõstmine kui vaadatavus (korrelatsioon).
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
FROM mart.fact_content_daily
WHERE in_featured
  AND in_viewers
  AND prominence_score_total IS NOT NULL
  AND views_total IS NOT NULL;

-- Viimane esiletõstmise päev.
CREATE OR REPLACE VIEW mart.v_latest_featured_day AS
SELECT MAX(feature_date) AS latest_feature_date
FROM staging.featured_daily;

CREATE OR REPLACE VIEW mart.v_content_latest_day AS
SELECT f.*
FROM mart.fact_content_daily AS f
INNER JOIN mart.v_latest_featured_day AS d
    ON f.activity_date = d.latest_feature_date;

-- Superseti vaated (vt init/06_superset_views.sql).
-- Kui meta CSV on laetud, kasuta content_structure_pct; muidu vana vaheversioon.
CREATE OR REPLACE VIEW mart.v_superset_structure_pct AS
SELECT
    activity_date,
    CASE structure_type
        WHEN 'catalog' THEN '1. Kataloogi struktuur'
        WHEN 'presented' THEN '2. Esitatud sisu struktuur'
        WHEN 'viewed' THEN '3. Vaadatud sisu struktuur'
    END AS structure_label,
    structure_type AS source,
    category_label AS segment,
    measure_value,
    pct
FROM mart.content_structure_pct
WHERE dimension = 'content_type'
  AND EXISTS (SELECT 1 FROM mart.content_structure_pct LIMIT 1)

UNION ALL

SELECT
    b.activity_date,
    b.structure_label,
    b.source,
    b.segment,
    b.measure_value,
    b.pct
FROM (
    WITH base AS (
        SELECT
            activity_date,
            CASE source
                WHEN 'catalog' THEN '1. Kataloogi struktuur'
                WHEN 'featured' THEN '2. Esitatud sisu struktuur'
                WHEN 'viewed' THEN '3. Vaadatud sisu struktuur'
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
        b.activity_date,
        b.structure_label,
        b.source,
        b.segment,
        b.measure_value,
        ROUND(100.0 * b.measure_value / NULLIF(t.structure_total, 0), 2) AS pct
    FROM base AS b
    INNER JOIN totals AS t
        ON b.activity_date = t.activity_date
       AND b.structure_label = t.structure_label
) AS b
WHERE NOT EXISTS (SELECT 1 FROM mart.content_structure_pct LIMIT 1);

DROP VIEW IF EXISTS mart.v_superset_origin_pct;
DROP VIEW IF EXISTS mart.v_superset_content_type_pct;

CREATE VIEW mart.v_superset_origin_pct AS
SELECT
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
    title,
    prominence_score_total,
    views_total,
    in_catalog,
    primary_category_name
FROM mart.v_content_latest_day
WHERE in_featured
ORDER BY prominence_score_total DESC
LIMIT 50;
