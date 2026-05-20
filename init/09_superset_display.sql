-- Superseti struktuurigraafikud: eestikeelsed sildid (vt mart.ref_*_labels, docs/images/*.png paigutus).
-- Käivita olemasolevas DB-s pärast transformi:
--   docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/09_superset_display.sql

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
