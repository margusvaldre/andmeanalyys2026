-- Andmekvaliteedi kontrollid: tabelid + käivitatav funktsioon `quality.run_checks`.
-- Eeldab skeeme `staging`, `mart` ja funktsiooni `mart.normalize_title` (vt init/05_mart_objects.sql).

CREATE TABLE IF NOT EXISTS quality.check_runs (
    check_run_id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    trigger_source TEXT,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'passed', 'failed'))
);

CREATE TABLE IF NOT EXISTS quality.rule_results (
    result_id BIGSERIAL PRIMARY KEY,
    check_run_id UUID NOT NULL REFERENCES quality.check_runs (check_run_id) ON DELETE CASCADE,
    rule_name TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('pass', 'warn', 'fail')),
    message TEXT NOT NULL,
    failing_count BIGINT NOT NULL DEFAULT 0,
    sample_detail TEXT,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rule_results_run
    ON quality.rule_results (check_run_id);

CREATE INDEX IF NOT EXISTS idx_rule_results_severity
    ON quality.rule_results (check_run_id, severity);

CREATE OR REPLACE VIEW quality.v_latest_rule_results AS
SELECT
    cr.started_at AS check_started_at,
    cr.trigger_source,
    cr.status AS run_status,
    rr.rule_name,
    rr.severity,
    rr.message,
    rr.failing_count,
    rr.sample_detail
FROM quality.rule_results AS rr
INNER JOIN quality.check_runs AS cr
    ON rr.check_run_id = cr.check_run_id
WHERE cr.check_run_id = (
    SELECT c.check_run_id
    FROM quality.check_runs AS c
    ORDER BY c.started_at DESC
    LIMIT 1
);

CREATE OR REPLACE FUNCTION quality.run_checks(p_trigger TEXT DEFAULT 'sql')
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_run UUID := gen_random_uuid();
    n BIGINT;
    s TEXT;
    sources BIGINT;
    dim_n BIGINT;
    v_match_pct NUMERIC;
    v_match_day DATE;
    v_pair_count BIGINT;
    v_pct_fail BIGINT;
    v_pct_warn BIGINT;
BEGIN
    INSERT INTO quality.check_runs (check_run_id, started_at, trigger_source, status)
    VALUES (v_run, now(), p_trigger, 'running');

    -- Kataloog: tühi pealkiri pärast normaliseerimist
    SELECT COUNT(*) INTO n
    FROM staging.catalog
    WHERE mart.normalize_title(heading) IS NULL;

    SELECT
        CASE
            WHEN n > 0 THEN (
                SELECT c.catalog_id
                FROM staging.catalog AS c
                WHERE mart.normalize_title(c.heading) IS NULL
                LIMIT 1
            )
        END
    INTO s;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'catalog_heading_blank',
        CASE WHEN n = 0 THEN 'pass' ELSE 'fail' END,
        'Kataloog: pealkiri ei tohi olla tühi (ainult tühikud loetakse tühjaks).',
        n,
        s
    );

    -- Vaadatavus: tühi pealkiri
    SELECT COUNT(*) INTO n
    FROM staging.viewers_raw
    WHERE mart.normalize_title(title) IS NULL;

    SELECT
        CASE
            WHEN n > 0 THEN (
                SELECT v.source_file
                FROM staging.viewers_raw AS v
                WHERE mart.normalize_title(v.title) IS NULL
                LIMIT 1
            )
        END
    INTO s;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'viewers_title_blank',
        CASE WHEN n = 0 THEN 'pass' ELSE 'fail' END,
        'Vaadatavus: pealkiri ei tohi olla tühi.',
        n,
        s
    );

    -- Vaadatavus: negatiivsed mõõdikud
    SELECT COUNT(*) INTO n
    FROM staging.viewers_raw
    WHERE total < 0
       OR live < 0
       OR od < 0
       OR web < 0
       OR app < 0;

    SELECT
        CASE
            WHEN n > 0 THEN (
                SELECT v.title
                FROM staging.viewers_raw AS v
                WHERE v.total < 0
                   OR v.live < 0
                   OR v.od < 0
                   OR v.web < 0
                   OR v.app < 0
                LIMIT 1
            )
        END
    INTO s;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'viewers_negative_measures',
        CASE WHEN n = 0 THEN 'pass' ELSE 'fail' END,
        'Vaadatavus: vaatamiste arvud ei tohi olla negatiivsed.',
        n,
        s
    );

    -- Vaadatavus: kuupäev peab jääma deklareeritud perioodi sisse
    SELECT COUNT(*) INTO n
    FROM staging.viewers_raw
    WHERE view_date < period_start
       OR view_date > period_end;

    SELECT
        CASE
            WHEN n > 0 THEN (
                SELECT
                    format(
                        'view_date=%s period=%s..%s file=%s',
                        v.view_date,
                        v.period_start,
                        v.period_end,
                        v.source_file
                    )
                FROM staging.viewers_raw AS v
                WHERE v.view_date < v.period_start
                   OR v.view_date > v.period_end
                LIMIT 1
            )
        END
    INTO s;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'viewers_view_date_outside_period',
        CASE WHEN n = 0 THEN 'pass' ELSE 'fail' END,
        'Vaadatavus: view_date peab olema period_start ja period_end vahel.',
        n,
        s
    );

    -- Esiletõstmine: tühi pealkiri
    SELECT COUNT(*) INTO n
    FROM staging.featured_daily
    WHERE mart.normalize_title(title) IS NULL;

    SELECT
        CASE
            WHEN n > 0 THEN (
                SELECT f.title
                FROM staging.featured_daily AS f
                WHERE mart.normalize_title(f.title) IS NULL
                LIMIT 1
            )
        END
    INTO s;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'featured_title_blank',
        CASE WHEN n = 0 THEN 'pass' ELSE 'fail' END,
        'Esiletõstmine: pealkiri ei tohi olla tühi.',
        n,
        s
    );

    -- Esiletõstmine: negatiivne skoor
    SELECT COUNT(*) INTO n
    FROM staging.featured_daily
    WHERE prominence_score_total < 0;

    SELECT
        CASE
            WHEN n > 0 THEN (
                SELECT f.title
                FROM staging.featured_daily AS f
                WHERE f.prominence_score_total < 0
                LIMIT 1
            )
        END
    INTO s;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'featured_negative_prominence',
        CASE WHEN n = 0 THEN 'pass' ELSE 'fail' END,
        'Esiletõstmine: prominence_score_total ei tohi olla negatiivne.',
        n,
        s
    );

    -- Mart: dim_content ei tohi olla tühi, kui vähemalt üks allikas sisaldab ridu
    SELECT
        (SELECT COUNT(*) FROM staging.catalog)
        + (SELECT COUNT(*) FROM staging.viewers_raw)
        + (SELECT COUNT(*) FROM staging.featured_daily)
    INTO sources;

    SELECT COUNT(*) INTO dim_n FROM mart.dim_content;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'mart_dim_nonempty_when_staging_has_rows',
        CASE
            WHEN sources = 0 THEN 'pass'
            WHEN dim_n = 0 AND sources > 0 THEN 'fail'
            ELSE 'pass'
        END,
        'Mart: kui staging sisaldab ridu, peab pärast transformi mart.dim_content sisaldama vähemalt ühte rida.',
        CASE WHEN sources > 0 AND dim_n = 0 THEN sources ELSE 0 END,
        CASE WHEN sources > 0 AND dim_n = 0 THEN 'Käivita transform (run_pipeline.py transform).' END
    );

    -- Match rate protsendid vahemikus 0..100 (kui read olemas)
    SELECT COUNT(*) INTO n
    FROM mart.title_match_daily
    WHERE featured_count > 0
      AND (
          catalog_match_pct IS NOT NULL
          AND (catalog_match_pct < 0 OR catalog_match_pct > 100)
          OR viewers_match_pct IS NOT NULL
          AND (viewers_match_pct < 0 OR viewers_match_pct > 100)
      );

    SELECT
        CASE
            WHEN n > 0 THEN (
                SELECT m.activity_date::TEXT
                FROM mart.title_match_daily AS m
                WHERE m.featured_count > 0
                  AND (
                      m.catalog_match_pct IS NOT NULL
                      AND (m.catalog_match_pct < 0 OR m.catalog_match_pct > 100)
                      OR m.viewers_match_pct IS NOT NULL
                      AND (m.viewers_match_pct < 0 OR m.viewers_match_pct > 100)
                  )
                LIMIT 1
            )
        END
    INTO s;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'title_match_pct_in_range',
        CASE WHEN n = 0 THEN 'pass' ELSE 'fail' END,
        'mart.title_match_daily: kattuvusprotsendid peavad jääma vahemikku 0..100.',
        n,
        s
    );

    -- Hiljutised ebaõnnestunud toru käivitused (hoiatus)
    SELECT COUNT(*) INTO n
    FROM staging.pipeline_runs
    WHERE status = 'failed'
      AND started_at >= now() - INTERVAL '7 days';

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'pipeline_failures_last_7_days',
        CASE WHEN n = 0 THEN 'pass' ELSE 'warn' END,
        'Viimase 7 päeva jooksul on staging.pipeline_runs kirjeid status=failed.',
        n,
        NULL
    );

    -- Meta CSV: tühi pealkiri
    SELECT COUNT(*) INTO n
    FROM staging.content_metadata
    WHERE mart.normalize_title(title) IS NULL;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'metadata_title_blank',
        CASE WHEN n = 0 THEN 'pass' ELSE 'fail' END,
        'Meta CSV: pealkiri ei tohi olla tühi.',
        n,
        NULL
    );

    -- Meta CSV: tundmatu päritolukood (hoiatus)
    SELECT COUNT(*) INTO n
    FROM staging.content_metadata AS m
    LEFT JOIN mart.ref_origin_labels AS ol
        ON m.origin_code = ol.origin_code
    WHERE ol.origin_code IS NULL;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'metadata_unknown_origin_code',
        CASE WHEN n = 0 THEN 'pass' ELSE 'warn' END,
        'Meta CSV: origin_code puudub viitetabelis mart.ref_origin_labels.',
        n,
        NULL
    );

    -- Meta CSV: tundmatu sisutüüp (hoiatus)
    SELECT COUNT(*) INTO n
    FROM staging.content_metadata AS m
    LEFT JOIN mart.ref_content_type_labels AS tl
        ON mart.normalize_content_type_code(m.content_type_code) = tl.content_type_code
    WHERE tl.content_type_code IS NULL;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'metadata_unknown_content_type',
        CASE WHEN n = 0 THEN 'pass' ELSE 'warn' END,
        'Meta CSV: content_type_code puudub viitetabelis mart.ref_content_type_labels.',
        n,
        NULL
    );

    -- Kataloogi pealkirjad meta CSV-ga (hoiatus, kui meta on olemas aga kattuvus madal)
    SELECT
        CASE
            WHEN (SELECT COUNT(*) FROM staging.content_metadata) = 0 THEN NULL
            WHEN (SELECT COUNT(*) FROM staging.catalog) = 0 THEN NULL
            ELSE ROUND(
                100.0 * (
                    SELECT COUNT(*)
                    FROM staging.catalog AS c
                    INNER JOIN staging.content_metadata AS m
                        ON mart.normalize_title(c.heading) = mart.normalize_title(m.title)
                ) / NULLIF((SELECT COUNT(*) FROM staging.catalog), 0),
                2
            )
        END
    INTO s;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'metadata_catalog_match_pct_low',
        CASE
            WHEN s IS NULL THEN 'pass'
            WHEN s::NUMERIC >= 50 THEN 'pass'
            ELSE 'warn'
        END,
        'Meta CSV: vähem kui 50% kataloogi pealkirjadest leidub meta failis (hoiatus).',
        CASE WHEN s IS NOT NULL AND s::NUMERIC < 50 THEN 1 ELSE 0 END,
        s
    );

    -- Esiletõstmine ↔ vaadatavus: viimase päeva viewers_match_pct (äriküsimus 2).
    SELECT m.activity_date, m.viewers_match_pct, m.featured_count
    INTO v_match_day, v_match_pct, n
    FROM mart.title_match_daily AS m
    WHERE m.viewers_match_count > 0
       OR m.viewers_match_pct > 0
    ORDER BY m.activity_date DESC
    LIMIT 1;

    IF v_match_day IS NULL THEN
        SELECT m.activity_date, m.viewers_match_pct, m.featured_count
        INTO v_match_day, v_match_pct, n
        FROM mart.title_match_daily AS m
        ORDER BY m.activity_date DESC
        LIMIT 1;
    END IF;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'title_match_viewers_match_pct_latest',
        CASE
            WHEN v_match_day IS NULL THEN 'pass'
            WHEN v_match_pct < 50 THEN 'fail'
            WHEN v_match_pct < 70 THEN 'warn'
            ELSE 'pass'
        END,
        'Viimase päeva (viewers andmetega) viewers_match_pct: WARN < 70%, FAIL < 50%.',
        CASE
            WHEN v_match_day IS NULL THEN 0
            WHEN v_match_pct < 70 THEN 1
            ELSE 0
        END,
        CASE
            WHEN v_match_day IS NULL THEN NULL
            ELSE format(
                '%s viewers_match_pct=%s featured_count=%s',
                v_match_day,
                v_match_pct,
                n
            )
        END
    );

    -- Korrelatsioon: viimase daily perioodi pair_count.
    SELECT c.period_start::TEXT, c.pair_count::BIGINT
    INTO s, v_pair_count
    FROM mart.v_superset_featured_correlation AS c
    WHERE c.grain = 'daily'
      AND c.pair_count > 0
    ORDER BY c.period_start DESC
    LIMIT 1;

    IF s IS NULL THEN
        SELECT c.period_start::TEXT, c.pair_count::BIGINT
        INTO s, v_pair_count
        FROM mart.v_superset_featured_correlation AS c
        WHERE c.grain = 'daily'
        ORDER BY c.period_start DESC
        LIMIT 1;
    END IF;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'correlation_pair_count_latest_daily',
        CASE
            WHEN s IS NULL THEN 'pass'
            WHEN v_pair_count < 20 THEN 'fail'
            WHEN v_pair_count < 50 THEN 'warn'
            ELSE 'pass'
        END,
        'Viimase päeva korrelatsioon: WARN kui pair_count < 50, FAIL kui < 20.',
        CASE
            WHEN s IS NULL THEN 0
            WHEN v_pair_count < 50 THEN 1
            ELSE 0
        END,
        CASE
            WHEN s IS NULL THEN NULL
            ELSE format('period_start=%s pair_count=%s', s, v_pair_count)
        END
    );

    -- Struktuuri virn: SUM(pct) peab olema ~100% iga rea kohta.
    SELECT COUNT(*) INTO v_pct_fail
    FROM (
        SELECT 1
        FROM mart.content_structure_period_pct AS p
        GROUP BY
            p.grain,
            p.period_start,
            p.period_end,
            p.structure_type,
            p.dimension
        HAVING ROUND(SUM(p.pct)::NUMERIC, 2) < 99
            OR ROUND(SUM(p.pct)::NUMERIC, 2) > 101
    ) AS bad_fail;

    SELECT COUNT(*) INTO v_pct_warn
    FROM (
        SELECT 1
        FROM mart.content_structure_period_pct AS p
        GROUP BY
            p.grain,
            p.period_start,
            p.period_end,
            p.structure_type,
            p.dimension
        HAVING ROUND(SUM(p.pct)::NUMERIC, 2) < 99.5
            OR ROUND(SUM(p.pct)::NUMERIC, 2) > 100.5
    ) AS bad_warn;

    SELECT
        format(
            'grain=%s %s..%s %s/%s pct_sum=%s',
            x.grain,
            x.period_start,
            x.period_end,
            x.structure_type,
            x.dimension,
            x.pct_sum
        )
    INTO s
    FROM (
        SELECT
            p.grain,
            p.period_start,
            p.period_end,
            p.structure_type,
            p.dimension,
            ROUND(SUM(p.pct)::NUMERIC, 2) AS pct_sum
        FROM mart.content_structure_period_pct AS p
        GROUP BY
            p.grain,
            p.period_start,
            p.period_end,
            p.structure_type,
            p.dimension
        HAVING ROUND(SUM(p.pct)::NUMERIC, 2) < 99.5
            OR ROUND(SUM(p.pct)::NUMERIC, 2) > 100.5
        ORDER BY ABS(ROUND(SUM(p.pct)::NUMERIC, 2) - 100) DESC
        LIMIT 1
    ) AS x;

    INSERT INTO quality.rule_results (
        check_run_id, rule_name, severity, message, failing_count, sample_detail
    )
    VALUES (
        v_run,
        'structure_pct_sum_near_100',
        CASE
            WHEN (SELECT COUNT(*) FROM mart.content_structure_period_pct) = 0 THEN 'pass'
            WHEN v_pct_fail > 0 THEN 'fail'
            WHEN v_pct_warn > 0 THEN 'warn'
            ELSE 'pass'
        END,
        'Struktuuri virn: SUM(pct) WARN väljaspool 99.5–100.5, FAIL väljaspool 99–101.',
        CASE
            WHEN v_pct_fail > 0 THEN v_pct_fail
            WHEN v_pct_warn > 0 THEN v_pct_warn
            ELSE 0
        END,
        s
    );

    UPDATE quality.check_runs
    SET
        finished_at = now(),
        status = CASE
            WHEN EXISTS (
                SELECT 1
                FROM quality.rule_results
                WHERE check_run_id = v_run
                  AND severity = 'fail'
            )
            THEN 'failed'
            ELSE 'passed'
        END
    WHERE check_run_id = v_run;

    RETURN v_run;
END;
$$;
