# Jupiteri andmeanalüüsi projekt

## Kiirkäivitus (kataloog API → PostgreSQL)

1. Loo keskkonnamuutujad:

```powershell
cd C:\Users\Kasutaja\andmeanalyys2026
copy .env.example .env
```

2. Käivita teenused (andmebaas + pipeline + scheduler + Superset):

```powershell
docker compose up -d --build
```

Scheduler käivitab iga päev kell **06:00** (Europe/Tallinn) käsu `run-all` (kataloog, vaadatavus, esiletõstmine, **meta CSV**, transform, andmekvaliteedi kontrollid). Vaadatavuse CSV peab enne olema kaustas `data/viewers/`.

Logid:

```powershell
docker compose logs -f scheduler
Get-Content logs\pipeline.log -Tail 50
```

Arenduses saad toru stardil käivitada (lisa `.env` faili `RUN_ON_STARTUP=true` ja taaskäivita scheduler).

Superset: **http://localhost:8089** (vaikimisi port `.env.example` failis; kasutaja `admin`). Juhend: [`docs/superset.md`](docs/superset.md).

Kui vana andmebaas segab, lähtesta:

```powershell
docker compose down -v
docker compose up -d --build
```

3. Lae andmed (kataloog + vaadatavus + esiletõstmine + meta CSV):

```powershell
docker compose exec pipeline python scripts/run_pipeline.py ingest-all
```

Või eraldi:

```powershell
docker compose exec pipeline python scripts/run_pipeline.py ingest-catalog
docker compose exec pipeline python scripts/run_pipeline.py ingest-viewers
docker compose exec pipeline python scripts/run_pipeline.py ingest-featured
docker compose exec pipeline python scripts/run_pipeline.py ingest-metadata
docker compose exec pipeline python scripts/run_pipeline.py transform
```

Meta CSV asub failis `data/metadata/jupiter_metadata.csv` (veerud: `updated`, `title`, `origin`, `type`).

Andmekvaliteedi kontrollid (kirjutavad `quality.check_runs` ja `quality.rule_results`; eeldavad `init/07_quality_objects.sql`):

```powershell
docker compose exec pipeline python scripts/run_pipeline.py quality
```

Täielik toru (sissevõtt + transform + kvaliteet):

```powershell
docker compose exec pipeline python scripts/run_pipeline.py run-all
```

Kui andmebaas loodi enne uuemaid tabeleid, käivita üks kord:

```powershell
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/02_viewers_staging.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/03_catalog_incremental.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/04_featured_staging.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/05_mart_objects.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/06_superset_views.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/07_quality_objects.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/08_metadata_staging.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/09_superset_display.sql
```

`03_catalog_incremental.sql` loob `staging.catalog` (üks rida `catalog_id` kohta) ja täidab selle vajadusel vanast `catalog_raw`-st.

4. Kontrolli tulemust:

```powershell
docker compose exec db psql -U praktikum -d praktikum -c "SELECT COUNT(*) FROM staging.catalog;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT * FROM staging.catalog_title_changes ORDER BY detected_at DESC LIMIT 5;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT grain, COUNT(*) FROM staging.viewers_raw GROUP BY grain;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT feature_date, COUNT(*) FROM staging.featured_daily GROUP BY feature_date;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT title, prominence_score_total FROM staging.featured_daily ORDER BY prominence_score_total DESC LIMIT 10;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT run_id, source_name, status, row_count FROM staging.pipeline_runs ORDER BY started_at DESC LIMIT 5;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT activity_date, featured_count, catalog_match_pct, viewers_match_pct FROM mart.title_match_daily;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT source, SUM(title_count) FROM mart.content_by_source GROUP BY source;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT title, prominence_score_total, views_total FROM mart.v_featured_viewership ORDER BY views_total DESC LIMIT 10;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT title, origin_country, meta_content_type FROM mart.dim_content WHERE in_metadata LIMIT 10;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT structure_type, dimension, category_label, pct FROM mart.content_structure_pct WHERE dimension='origin_country' ORDER BY structure_type, pct DESC LIMIT 15;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT * FROM quality.v_latest_rule_results;"
```

## Projektifailid

| Fail | Roll |
|------|------|
| `compose.yml` | PostgreSQL + pipeline + scheduler + Superset |
| `docs/superset.md` | Näidikulaua käivitus ja graafikud |
| `Dockerfile.superset` | Superset konteiner |
| `superset/dashboard_export/` | Imporditav starter-dashboard |
| `scheduler/crontab` | Päevane cron (06:00) |
| `Dockerfile.scheduler` | Cron konteiner |
| `logs/pipeline.log` | Scheduleri väljund (gitignore) |
| `init/01_create_objects.sql` | skeemid ja põhitabelid |
| `init/03_catalog_incremental.sql` | `staging.catalog` + pealkirja muutuste logi |
| `scripts/catalog_api.py` | API lugemine (kasutab ingest_catalog_api) |
| `scripts/ingest_catalog_api.py` | API → `staging.catalog` (ainult uued + muutuste tuvastus) |
| `scripts/ingest_viewers_csv.py` | CSV → `staging.viewers_raw` |
| `scripts/prominence_api.py` | Esiletõstmise skooride arvutus API-st |
| `scripts/ingest_featured_api.py` | API → `staging.featured_daily` |
| `scripts/ingest_metadata_csv.py` | Meta CSV → `staging.content_metadata` |
| `data/metadata/jupiter_metadata.csv` | Pealkiri → päritolumaa ja sisutüüp |
| `data/prominence/*.csv` | Positsioonimaatriks ja lehe koefitsiendid |
| `init/05_mart_objects.sql` | Mart tabelid ja `normalize_title` funktsioon |
| `scripts/01_transform.sql` | Staging → mart transformatsioon |
| `init/07_quality_objects.sql` | `quality` skeemi tabelid + `quality.run_checks()` |
| `init/08_metadata_staging.sql` | `staging.content_metadata`, viitetabelid, `mart.content_structure_pct` |
| `scripts/02_quality_checks.sql` | Käsitsi: `SELECT quality.run_checks(...)` (vt faili sisu) |
| `scripts/run_pipeline.py` | `ingest-*`, `transform`, `quality`, `run-all` |
| `docs/arhitektuur.md` | Äriküsimus ja andmevoog |

