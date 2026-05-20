-- Vaated Superseti näidikulauale (käivita olemasolevas DB-s või uue paigaldusega).
-- Eeldab init/08_metadata_staging.sql ja transformi (mart.content_structure_pct).

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

-- Päritolumaa / sisutüüp: eestikeelsed sildid (vt init/09_superset_display.sql).
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

-- Viimase esiletõstmise päeva TOP (tabel graafikule).
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
