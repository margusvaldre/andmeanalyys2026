-- Transformatsioon: staging -> mart
-- Käivita pärast ingest-all:
--   docker compose exec pipeline python scripts/run_pipeline.py transform

CREATE TABLE IF NOT EXISTS mart.content_structure_period_pct (
    grain TEXT NOT NULL CHECK (grain IN ('daily', 'weekly')),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    activity_date DATE NOT NULL,
    structure_type TEXT NOT NULL CHECK (structure_type IN ('catalog', 'presented', 'viewed')),
    dimension TEXT NOT NULL CHECK (dimension IN ('origin_country', 'content_type')),
    category_code TEXT NOT NULL,
    category_label TEXT NOT NULL,
    measure_value NUMERIC NOT NULL,
    pct NUMERIC(5, 2) NOT NULL,
    transformed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (grain, period_start, period_end, structure_type, dimension, category_code)
);

TRUNCATE TABLE
    mart.content_structure_period_pct,
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
    d.meta_content_type AS content_type,
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
    '' AS content_type,
    COUNT(*)::INTEGER AS title_count,
    now() AS transformed_at
FROM (
    SELECT DISTINCT ON (period_start, period_end, title)
        view_date,
        title
    FROM staging.viewers_raw
    WHERE grain = 'daily'
    ORDER BY period_start, period_end, title, loaded_at DESC
) AS latest_viewers
GROUP BY view_date;

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

-- Struktuuri protsendid meta CSV põhjal (päev + nädal).
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

INSERT INTO mart.ref_origin_labels (origin_code, origin_label) VALUES
    ('UNKNOWN', 'Määramata (meta puudub)')
ON CONFLICT (origin_code) DO NOTHING;

INSERT INTO mart.ref_content_type_labels (content_type_code, content_type_label) VALUES
    ('UNKNOWN', 'Määramata (meta puudub)')
ON CONFLICT (content_type_code) DO NOTHING;

WITH meta AS (
    SELECT
        mart.normalize_title(title) AS title_normalized,
        origin_code,
        mart.normalize_content_type_code(content_type_code) AS content_type_code
    FROM staging.content_metadata
    WHERE mart.normalize_title(title) IS NOT NULL
),
catalog_daily_norm AS (
    SELECT DISTINCT ON (snapshot_date, mart.normalize_title(heading))
        snapshot_date,
        mart.normalize_title(heading) AS title_normalized
    FROM staging.catalog_daily
    WHERE mart.normalize_title(heading) IS NOT NULL
    ORDER BY snapshot_date, mart.normalize_title(heading), catalog_id
),
viewers_daily_latest AS (
    SELECT DISTINCT ON (period_start, period_end, title)
        view_date,
        title,
        mart.normalize_title(title) AS title_normalized,
        total
    FROM staging.viewers_raw
    WHERE grain = 'daily'
    ORDER BY period_start, period_end, title, loaded_at DESC
),
viewers_weekly_latest AS (
    SELECT DISTINCT ON (period_start, period_end, title)
        period_start,
        period_end,
        title,
        mart.normalize_title(title) AS title_normalized,
        total
    FROM staging.viewers_raw
    WHERE grain = 'weekly'
    ORDER BY period_start, period_end, title, loaded_at DESC
),
periods AS (
    SELECT
        'daily'::TEXT AS grain,
        d.activity_date AS period_start,
        d.activity_date AS period_end,
        d.activity_date
    FROM (
        SELECT snapshot_date AS activity_date FROM staging.catalog_daily
        UNION
        SELECT feature_date AS activity_date FROM staging.featured_daily
        UNION
        SELECT view_date AS activity_date FROM viewers_daily_latest
    ) AS d
    UNION ALL
    SELECT
        'weekly'::TEXT AS grain,
        w.period_start,
        w.period_end,
        w.period_end AS activity_date
    FROM (SELECT DISTINCT period_start, period_end FROM viewers_weekly_latest) AS w
),
structure_counts AS (
    -- Kataloog: pealkirjade arv (meta puudub -> UNKNOWN).
    SELECT
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        'catalog'::TEXT AS structure_type,
        'origin_country'::TEXT AS dimension,
        COALESCE(m.origin_code, 'UNKNOWN') AS category_code,
        COALESCE(ol.origin_label, 'Määramata (meta puudub)') AS category_label,
        COUNT(*)::NUMERIC AS measure_value
    FROM periods AS p
    INNER JOIN catalog_daily_norm AS c
        ON (
            (p.grain = 'daily' AND c.snapshot_date = p.period_start)
            OR (p.grain = 'weekly' AND c.snapshot_date BETWEEN p.period_start AND p.period_end)
        )
    LEFT JOIN meta AS m
        ON c.title_normalized = m.title_normalized
    LEFT JOIN mart.ref_origin_labels AS ol
        ON COALESCE(m.origin_code, 'UNKNOWN') = ol.origin_code
    GROUP BY
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        COALESCE(m.origin_code, 'UNKNOWN'),
        COALESCE(ol.origin_label, 'Määramata (meta puudub)')

    UNION ALL

    SELECT
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        'catalog',
        'content_type',
        COALESCE(m.content_type_code, 'UNKNOWN'),
        COALESCE(tl.content_type_label, 'Määramata (meta puudub)'),
        COUNT(*)::NUMERIC
    FROM periods AS p
    INNER JOIN catalog_daily_norm AS c
        ON (
            (p.grain = 'daily' AND c.snapshot_date = p.period_start)
            OR (p.grain = 'weekly' AND c.snapshot_date BETWEEN p.period_start AND p.period_end)
        )
    LEFT JOIN meta AS m
        ON c.title_normalized = m.title_normalized
    LEFT JOIN mart.ref_content_type_labels AS tl
        ON COALESCE(m.content_type_code, 'UNKNOWN') = tl.content_type_code
    GROUP BY
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        COALESCE(m.content_type_code, 'UNKNOWN'),
        COALESCE(tl.content_type_label, 'Määramata (meta puudub)')

    UNION ALL

    -- Esitatud: päev / nädal summa (meta puudub -> UNKNOWN).
    SELECT
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        'presented',
        'origin_country',
        COALESCE(m.origin_code, 'UNKNOWN'),
        COALESCE(ol.origin_label, 'Määramata (meta puudub)'),
        SUM(f.prominence_score_total)::NUMERIC
    FROM periods AS p
    INNER JOIN staging.featured_daily AS f
        ON (
            (p.grain = 'daily' AND f.feature_date = p.period_start)
            OR (p.grain = 'weekly' AND f.feature_date BETWEEN p.period_start AND p.period_end)
        )
    LEFT JOIN meta AS m
        ON mart.normalize_title(f.title) = m.title_normalized
    LEFT JOIN mart.ref_origin_labels AS ol
        ON COALESCE(m.origin_code, 'UNKNOWN') = ol.origin_code
    WHERE f.prominence_score_total IS NOT NULL
    GROUP BY
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        COALESCE(m.origin_code, 'UNKNOWN'),
        COALESCE(ol.origin_label, 'Määramata (meta puudub)')

    UNION ALL

    SELECT
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        'presented',
        'content_type',
        COALESCE(m.content_type_code, 'UNKNOWN'),
        COALESCE(tl.content_type_label, 'Määramata (meta puudub)'),
        SUM(f.prominence_score_total)::NUMERIC
    FROM periods AS p
    INNER JOIN staging.featured_daily AS f
        ON (
            (p.grain = 'daily' AND f.feature_date = p.period_start)
            OR (p.grain = 'weekly' AND f.feature_date BETWEEN p.period_start AND p.period_end)
        )
    LEFT JOIN meta AS m
        ON mart.normalize_title(f.title) = m.title_normalized
    LEFT JOIN mart.ref_content_type_labels AS tl
        ON COALESCE(m.content_type_code, 'UNKNOWN') = tl.content_type_code
    WHERE f.prominence_score_total IS NOT NULL
    GROUP BY
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        COALESCE(m.content_type_code, 'UNKNOWN'),
        COALESCE(tl.content_type_label, 'Määramata (meta puudub)')

    UNION ALL

    -- Vaadatud: päeval daily CSV, nädalal weekly CSV (meta puudub -> UNKNOWN).
    SELECT
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        'viewed',
        'origin_country',
        COALESCE(m.origin_code, 'UNKNOWN'),
        COALESCE(ol.origin_label, 'Määramata (meta puudub)'),
        SUM(v.total)::NUMERIC
    FROM periods AS p
    INNER JOIN (
        SELECT
            'daily'::TEXT AS grain,
            view_date AS period_start,
            view_date AS period_end,
            title_normalized,
            total
        FROM viewers_daily_latest
        UNION ALL
        SELECT
            'weekly'::TEXT AS grain,
            period_start,
            period_end,
            title_normalized,
            total
        FROM viewers_weekly_latest
    ) AS v
        ON p.grain = v.grain
       AND p.period_start = v.period_start
       AND p.period_end = v.period_end
    LEFT JOIN meta AS m
        ON v.title_normalized = m.title_normalized
    LEFT JOIN mart.ref_origin_labels AS ol
        ON COALESCE(m.origin_code, 'UNKNOWN') = ol.origin_code
    GROUP BY
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        COALESCE(m.origin_code, 'UNKNOWN'),
        COALESCE(ol.origin_label, 'Määramata (meta puudub)')

    UNION ALL

    SELECT
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        'viewed',
        'content_type',
        COALESCE(m.content_type_code, 'UNKNOWN'),
        COALESCE(tl.content_type_label, 'Määramata (meta puudub)'),
        SUM(v.total)::NUMERIC
    FROM periods AS p
    INNER JOIN (
        SELECT
            'daily'::TEXT AS grain,
            view_date AS period_start,
            view_date AS period_end,
            title_normalized,
            total
        FROM viewers_daily_latest
        UNION ALL
        SELECT
            'weekly'::TEXT AS grain,
            period_start,
            period_end,
            title_normalized,
            total
        FROM viewers_weekly_latest
    ) AS v
        ON p.grain = v.grain
       AND p.period_start = v.period_start
       AND p.period_end = v.period_end
    LEFT JOIN meta AS m
        ON v.title_normalized = m.title_normalized
    LEFT JOIN mart.ref_content_type_labels AS tl
        ON COALESCE(m.content_type_code, 'UNKNOWN') = tl.content_type_code
    GROUP BY
        p.grain,
        p.period_start,
        p.period_end,
        p.activity_date,
        COALESCE(m.content_type_code, 'UNKNOWN'),
        COALESCE(tl.content_type_label, 'Määramata (meta puudub)')
),
structure_totals AS (
    SELECT
        grain,
        period_start,
        period_end,
        activity_date,
        structure_type,
        dimension,
        SUM(measure_value) AS structure_total
    FROM structure_counts
    GROUP BY grain, period_start, period_end, activity_date, structure_type, dimension
)
INSERT INTO mart.content_structure_period_pct (
    grain,
    period_start,
    period_end,
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
    sc.grain,
    sc.period_start,
    sc.period_end,
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
    ON sc.grain = st.grain
   AND sc.period_start = st.period_start
   AND sc.period_end = st.period_end
   AND sc.activity_date = st.activity_date
   AND sc.structure_type = st.structure_type
   AND sc.dimension = st.dimension;

-- Tagasiühilduvus: hoia ka vana päevatabel ainult viimase päeva jaoks.
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
    p.activity_date,
    p.structure_type,
    p.dimension,
    p.category_code,
    p.category_label,
    p.measure_value,
    p.pct,
    p.transformed_at
FROM mart.content_structure_period_pct AS p
INNER JOIN (
    SELECT MAX(period_start) AS latest_day
    FROM mart.content_structure_period_pct
    WHERE grain = 'daily'
) AS d
    ON p.grain = 'daily'
   AND p.period_start = d.latest_day;

-- Vaated Superseti jaoks.

CREATE OR REPLACE VIEW mart.v_content_daily AS
SELECT *
FROM mart.fact_content_daily;

-- Viimane esiletõstmise päev.
CREATE OR REPLACE VIEW mart.v_latest_featured_day AS
SELECT MAX(feature_date) AS latest_feature_date
FROM staging.featured_daily;

CREATE OR REPLACE VIEW mart.v_content_latest_day AS
SELECT f.*
FROM mart.fact_content_daily AS f
INNER JOIN mart.v_latest_featured_day AS d
    ON f.activity_date = d.latest_feature_date;

-- Viimase esiletõstmise päev (ilma fallbackita).
CREATE OR REPLACE VIEW mart.v_featured_viewership AS
SELECT
    f.activity_date,
    f.title_normalized,
    f.title,
    f.primary_category_name,
    f.content_type,
    f.prominence_score_total,
    f.views_total,
    f.views_web,
    f.views_app
FROM mart.v_content_latest_day AS f
WHERE f.in_featured
  AND f.prominence_score_total IS NOT NULL;

-- Perioodipõhine vaade TOP-i ja korrelatsiooni jaoks.
CREATE OR REPLACE VIEW mart.v_featured_viewership_period AS
WITH featured_daily AS (
    SELECT
        'daily'::TEXT AS grain,
        f.feature_date AS period_start,
        f.feature_date AS period_end,
        f.feature_date AS activity_date,
        mart.normalize_title(f.title) AS title_normalized,
        f.title,
        SUM(f.prominence_score_total)::NUMERIC(12,4) AS prominence_score_total
    FROM staging.featured_daily AS f
    WHERE mart.normalize_title(f.title) IS NOT NULL
      AND f.prominence_score_total IS NOT NULL
    GROUP BY f.feature_date, mart.normalize_title(f.title), f.title
),
featured_weekly AS (
    SELECT
        'weekly'::TEXT AS grain,
        w.period_start,
        w.period_end,
        w.period_end AS activity_date,
        mart.normalize_title(f.title) AS title_normalized,
        MAX(f.title) AS title,
        SUM(f.prominence_score_total)::NUMERIC(12,4) AS prominence_score_total
    FROM (SELECT DISTINCT period_start, period_end FROM staging.viewers_raw WHERE grain = 'weekly') AS w
    INNER JOIN staging.featured_daily AS f
        ON f.feature_date BETWEEN w.period_start AND w.period_end
    WHERE mart.normalize_title(f.title) IS NOT NULL
      AND f.prominence_score_total IS NOT NULL
    GROUP BY w.period_start, w.period_end, mart.normalize_title(f.title)
),
viewers_daily AS (
    SELECT DISTINCT ON (period_start, period_end, title)
        'daily'::TEXT AS grain,
        view_date AS period_start,
        view_date AS period_end,
        view_date AS activity_date,
        mart.normalize_title(title) AS title_normalized,
        total::INTEGER AS views_total
    FROM staging.viewers_raw
    WHERE grain = 'daily'
      AND mart.normalize_title(title) IS NOT NULL
    ORDER BY period_start, period_end, title, loaded_at DESC
),
viewers_weekly AS (
    SELECT DISTINCT ON (period_start, period_end, title)
        'weekly'::TEXT AS grain,
        period_start,
        period_end,
        period_end AS activity_date,
        mart.normalize_title(title) AS title_normalized,
        total::INTEGER AS views_total
    FROM staging.viewers_raw
    WHERE grain = 'weekly'
      AND mart.normalize_title(title) IS NOT NULL
    ORDER BY period_start, period_end, title, loaded_at DESC
),
catalog_presence_daily AS (
    SELECT DISTINCT
        'daily'::TEXT AS grain,
        snapshot_date AS period_start,
        snapshot_date AS period_end,
        snapshot_date AS activity_date,
        mart.normalize_title(heading) AS title_normalized
    FROM staging.catalog_daily
    WHERE mart.normalize_title(heading) IS NOT NULL
),
catalog_presence_weekly AS (
    SELECT DISTINCT
        'weekly'::TEXT AS grain,
        w.period_start,
        w.period_end,
        w.period_end AS activity_date,
        mart.normalize_title(c.heading) AS title_normalized
    FROM (SELECT DISTINCT period_start, period_end FROM staging.viewers_raw WHERE grain = 'weekly') AS w
    INNER JOIN staging.catalog_daily AS c
        ON c.snapshot_date BETWEEN w.period_start AND w.period_end
    WHERE mart.normalize_title(c.heading) IS NOT NULL
)
SELECT
    f.grain,
    f.period_start,
    f.period_end,
    f.activity_date,
    f.title_normalized,
    f.title,
    COALESCE(
        NULLIF(TRIM(d.meta_content_type), ''),
        NULLIF(TRIM(d.primary_category_name), ''),
        'Määramata (meta puudub)'
    ) AS primary_category_name,
    f.prominence_score_total,
    v.views_total,
    (v.views_total IS NULL) AS viewers_missing,
    (cp.title_normalized IS NOT NULL) AS in_catalog
FROM (
    SELECT * FROM featured_daily
    UNION ALL
    SELECT * FROM featured_weekly
) AS f
LEFT JOIN (
    SELECT * FROM viewers_daily
    UNION ALL
    SELECT * FROM viewers_weekly
) AS v
    ON f.grain = v.grain
   AND f.period_start = v.period_start
   AND f.period_end = v.period_end
   AND f.title_normalized = v.title_normalized
LEFT JOIN (
    SELECT * FROM catalog_presence_daily
    UNION ALL
    SELECT * FROM catalog_presence_weekly
) AS cp
    ON f.grain = cp.grain
   AND f.period_start = cp.period_start
   AND f.period_end = cp.period_end
   AND f.title_normalized = cp.title_normalized
LEFT JOIN mart.dim_content AS d
    ON f.title_normalized = d.title_normalized;

-- Superseti vaated (vt init/10_superset_views.sql).
-- Kui meta CSV on laetud, kasuta content_structure_pct; muidu vana vaheversioon.
CREATE OR REPLACE VIEW mart.v_superset_structure_pct AS
SELECT
    grain,
    period_start,
    period_end,
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
FROM mart.content_structure_period_pct
WHERE dimension = 'content_type'
  AND EXISTS (SELECT 1 FROM mart.content_structure_period_pct LIMIT 1)

UNION ALL

SELECT
    b.grain,
    b.period_start,
    b.period_end,
    b.activity_date,
    b.structure_label,
    b.source,
    b.segment,
    b.measure_value,
    b.pct
FROM (
    WITH base AS (
        SELECT
            'daily'::TEXT AS grain,
            activity_date AS period_start,
            activity_date AS period_end,
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
            grain,
            period_start,
            period_end,
            activity_date,
            structure_label,
            SUM(measure_value) AS structure_total
        FROM base
        GROUP BY grain, period_start, period_end, activity_date, structure_label
    )
    SELECT
        b.grain,
        b.period_start,
        b.period_end,
        b.activity_date,
        b.structure_label,
        b.source,
        b.segment,
        b.measure_value,
        ROUND(100.0 * b.measure_value / NULLIF(t.structure_total, 0), 2) AS pct
    FROM base AS b
    INNER JOIN totals AS t
        ON b.grain = t.grain
       AND b.period_start = t.period_start
       AND b.period_end = t.period_end
       AND b.activity_date = t.activity_date
       AND b.structure_label = t.structure_label
) AS b
WHERE NOT EXISTS (SELECT 1 FROM mart.content_structure_period_pct LIMIT 1);

DROP VIEW IF EXISTS mart.v_superset_origin_pct;
DROP VIEW IF EXISTS mart.v_superset_content_type_pct;
DROP VIEW IF EXISTS mart.v_superset_featured_viewership;
DROP VIEW IF EXISTS mart.v_superset_featured_top;
DROP VIEW IF EXISTS mart.v_superset_featured_correlation;

CREATE VIEW mart.v_superset_origin_pct AS
SELECT
    grain,
    period_start,
    TO_CHAR(period_start, 'YYYY-MM-DD') AS period_start_key,
    period_end,
    TO_CHAR(period_end, 'YYYY-MM-DD') AS period_end_key,
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
        WHEN 'UNKNOWN' THEN 98
        ELSE 99
    END AS segment_sort,
    measure_value,
    pct
FROM mart.content_structure_period_pct
WHERE dimension = 'origin_country';

CREATE VIEW mart.v_superset_content_type_pct AS
SELECT
    grain,
    period_start,
    TO_CHAR(period_start, 'YYYY-MM-DD') AS period_start_key,
    period_end,
    TO_CHAR(period_end, 'YYYY-MM-DD') AS period_end_key,
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
        WHEN 'UNKNOWN' THEN 98
        ELSE 99
    END AS segment_sort,
    measure_value,
    pct
FROM mart.content_structure_period_pct
WHERE dimension = 'content_type';

CREATE OR REPLACE VIEW mart.v_superset_featured_top AS
SELECT
    v.grain,
    v.period_start,
    TO_CHAR(v.period_start, 'YYYY-MM-DD') AS period_start_key,
    v.period_end,
    TO_CHAR(v.period_end, 'YYYY-MM-DD') AS period_end_key,
    v.activity_date,
    v.title,
    v.prominence_score_total,
    v.views_total,
    v.in_catalog,
    v.primary_category_name
FROM mart.v_featured_viewership_period AS v;

CREATE OR REPLACE VIEW mart.v_superset_featured_viewership AS
SELECT
    v.grain,
    v.period_start,
    TO_CHAR(v.period_start, 'YYYY-MM-DD') AS period_start_key,
    v.period_end,
    TO_CHAR(v.period_end, 'YYYY-MM-DD') AS period_end_key,
    v.activity_date,
    v.title,
    v.prominence_score_total,
    v.views_total,
    CASE WHEN v.views_total IS NULL THEN 'N/A' ELSE NULL END AS views_note,
    v.in_catalog,
    v.primary_category_name
FROM mart.v_featured_viewership_period AS v;

CREATE OR REPLACE VIEW mart.v_superset_featured_correlation AS
SELECT
    grain,
    period_start,
    TO_CHAR(period_start, 'YYYY-MM-DD') AS period_start_key,
    period_end,
    TO_CHAR(period_end, 'YYYY-MM-DD') AS period_end_key,
    activity_date,
    COUNT(*) FILTER (
        WHERE prominence_score_total IS NOT NULL
          AND views_total IS NOT NULL
    ) AS pair_count,
    corr(prominence_score_total::DOUBLE PRECISION, views_total::DOUBLE PRECISION) AS corr_prominence_views
FROM mart.v_featured_viewership_period
GROUP BY grain, period_start, period_end, activity_date;
