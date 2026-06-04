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

Scheduler käivitab iga päev kell **06:00** (Europe/Tallinn) käsu `run-all` (API, vaadatavus, esiletõstmine, **meta CSV**, transform, quality, **check** — **ilma arhiivide taastamiseta**). WARN logitakse, kuid toru jätkub; FAIL peatab. Vaadatavuse CSV peab enne olema kaustas `data/viewers/`. Iga edukas kataloogi ja esiletõstmise ingest **kirjutab** päeva varukoopia CSV kaustadesse `data/catalog_daily/` ja `data/featured/`; uus andmebaas laeb need üks kord käsuga `ingest-archives`.

Logid:

```powershell
docker compose logs -f scheduler
Get-Content logs\pipeline.log -Tail 50
```

Arenduses saad toru stardil käivitada (lisa `.env` faili `RUN_ON_STARTUP=true` ja taaskäivita scheduler).

Superset: **http://localhost:8089** (vaikimisi port `.env.example` failis; kasutaja `admin`). Juhend: [`docs/superset.md`](docs/superset.md).

Kui vana andmebaas segab, lähtesta (kustutab kõik andmed):

```powershell
docker compose down -v
docker compose up -d --build
```

Oota, kuni `docker compose ps` näitab `db`, `scheduler` ja `superset` olekus **healthy** (esimene Superseti build võib võtta mitu minutit). `superset-import` peab lõppema edukalt (vaata `docker compose logs superset-import`).

**Täiesti uus andmebaas** saab skeemi automaatselt failidest `init/01` … `init/10` (esimene `docker compose up`; Superseti vaated on `10`, et käivitada pärast `08`).

**Puhas paigaldus — kontrollnimekiri**

```powershell
copy .env.example .env
docker compose down -v
docker compose up -d --build
docker compose ps
docker compose exec pipeline python scripts/run_pipeline.py ingest-archives
docker compose exec pipeline python scripts/run_pipeline.py run-all
```

Oodatav `run-all` lõpp: `mart.dim_content` tuhandeid ridu, `v_featured_viewership` sadu ridu, quality ja check (võib olla WARN, nt päevade kattumine). Seejärel Superset: http://localhost:8089 → dashboard **Jupiteri analüüs**.

**Olemasolev andmebaas** (nt kloonitud repo enne meta CSV-d) — käivita käsitsi kõik täiendavad skriptid (vt allpool jaotist „Vana andmebaas”).

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

Kontrolli, et andmevoog on terviklik (pärast `run-all`):

```powershell
docker compose exec pipeline python scripts/run_pipeline.py check
```

`check` on read-only: kontrollib faile, staging/mart ridu ja Superseti vaateid (sh **TOP vaate globaalne limiit** — kas `v_superset_featured_top` LIMIT 500 võib moonutada perioodi TOP 20). Kui on ainult hoiatusi (nt erinev featured/viewers päev või weekly ilma arhiivita), exit 0; `--strict` loeb WARN-id veaks.

### Vana andmebaas — käsitsi skeemi täiendamine

Kui andmebaas loodi **enne** uuemaid `init/*.sql` faile, PostgreSQL **ei käivita** neid uuesti automaatselt. Käivita üks kord (järjekord oluline):

```powershell
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/02_viewers_staging.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/03_catalog_incremental.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/04_featured_staging.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/05_mart_objects.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/07_quality_objects.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/08_metadata_staging.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/10_superset_views.sql
```

Kontrolli, et meta tabel on olemas:

```powershell
docker compose exec db psql -U praktikum -d praktikum -c "\dt staging.content_metadata"
```

Peaks näitama tabelit `staging.content_metadata`. Seejärel:

```powershell
docker compose exec pipeline python scripts/run_pipeline.py run-all
```

`03_catalog_incremental.sql` loob `staging.catalog` (üks rida `catalog_id` kohta) ja täidab selle vajadusel vanast `catalog_raw`-st.

### Levinud vead

| Viga | Põhjus | Lahendus |
|------|--------|----------|
| `relation "staging.content_metadata" does not exist` | Puudub `init/08_metadata_staging.sql` (vana DB maht) | Käivita `08` ja `10` (vt ülal); seejärel `run-all` |
| `function quality.run_checks does not exist` | Puudub `init/07_quality_objects.sql` | Käivita `07` |
| `relation "staging.catalog" does not exist` | Puudub `init/03_catalog_incremental.sql` | Käivita `02`–`08` ja `10` või `docker compose down -v` ja uus `up` |
| `db` konteiner exit 3 esimesel `up` | Vana init järjekord (`06` enne `08`) | `docker compose down -v` ja uus `up` (vajab `10_superset_views.sql`) |
| Superset „Columns missing in dataset” | Vale dashboardi `chartId` või vana Superseti maht | `docker compose run --rm --no-deps superset-import` |
| Tühi „Esiletõstmine ja vaadatavus” | Filtrid puuduvad või erinev featured vs viewers päev | Loo dashboardi filtrid (`docs/superset.md`); lae viewers CSV; `transform` |

4. Kontrolli tulemust:

```powershell
docker compose exec db psql -U praktikum -d praktikum -c "SELECT COUNT(*) FROM staging.catalog;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT * FROM staging.catalog_title_changes ORDER BY detected_at DESC LIMIT 5;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT grain, COUNT(*) FROM staging.viewers_raw GROUP BY grain;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT feature_date, COUNT(*) FROM staging.featured_daily GROUP BY feature_date;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT title, prominence_score_total, feature_date FROM staging.featured_daily ORDER BY prominence_score_total DESC LIMIT 10;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT run_id, source_name, status, row_count FROM staging.pipeline_runs ORDER BY started_at DESC LIMIT 5;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT activity_date, featured_count, catalog_match_pct, viewers_match_pct FROM mart.title_match_daily;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT source, SUM(title_count) FROM mart.content_by_source GROUP BY source;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT title, prominence_score_total, views_total FROM mart.v_superset_featured_viewership WHERE grain='daily' AND period_start_key='2026-05-29' ORDER BY prominence_score_total DESC LIMIT 10;"
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
| `superset/dashboard_export_source.zip` | **Install:** Superset UI export → `prepare_dashboard_export.py` |
| `superset/dashboard_export/` | Genereeritud YAML (import; üle kirjutatakse iga `superset-import` korral ZIP-ist) |
| `superset/dashboard_export_backup_20260519/` | **Varasem** käsitsi YAML starter (tagasipöördumine; import ilma `prepare`) |
| `superset/dashboard_export_20260603T213354.zip` | Sama install ZIP kuupäevaga nimega (valikuline arhiiv) |
| `scheduler/crontab` | Päevane cron (06:00) |
| `Dockerfile.scheduler` | Cron konteiner |
| `logs/pipeline.log` | Scheduleri väljund (gitignore) |
| `init/01_create_objects.sql` | skeemid ja põhitabelid |
| `init/03_catalog_incremental.sql` | `staging.catalog` + pealkirja muutuste logi |
| `scripts/catalog_api.py` | API lugemine (kasutab ingest_catalog_api) |
| `scripts/ingest_catalog_api.py` | API → `staging.catalog` + `staging.catalog_daily` + CSV arhiiv |
| `scripts/ingest_daily_archives.py` | Varukoopia CSV → staging (`ingest-archives`; ükshaaval, mitte run-all) |
| `scripts/daily_archive.py` | Arhiivi eksport/import loogika |
| `scripts/ingest_viewers_csv.py` | CSV → `staging.viewers_raw` |
| `scripts/prominence_api.py` | Esiletõstmise skooride arvutus API-st |
| `scripts/ingest_featured_api.py` | API → `staging.featured_daily` + CSV arhiiv |
| `scripts/ingest_metadata_csv.py` | Meta CSV → `staging.content_metadata` |
| `data/metadata/jupiter_metadata.csv` | Pealkiri → päritolumaa ja sisutüüp |
| `data/prominence/*.csv` | Positsioonimaatriks ja lehe koefitsiendid |
| `init/05_mart_objects.sql` | Mart tabelid ja `normalize_title` funktsioon |
| `scripts/01_transform.sql` | Staging → mart transformatsioon |
| `init/07_quality_objects.sql` | `quality` skeemi tabelid + `quality.run_checks()` |
| `init/08_metadata_staging.sql` | `staging.content_metadata`, `staging.catalog_daily`, viitetabelid, `mart.content_structure_period_pct` |
| `scripts/02_quality_checks.sql` | Käsitsi: `SELECT quality.run_checks(...)` (vt faili sisu) |
| `scripts/pipeline_check.py` | Read-only toru kontroll (`run_pipeline.py check`) |
| `scripts/run_pipeline.py` | `ingest-*`, `transform`, `quality`, `check`, `run-all` (lõpus check) |
| `docs/arhitektuur.md` | Äriküsimus ja andmevoog |

