# Superset — Jupiteri näidikulaud

Apache Superset ühendub sama PostgreSQL-iga (`mart` skeem) ja kuvab kataloogi, esiletõstmise ja vaadatavuse mõõdikuid.

## Käivitus

```powershell
cd C:\Users\Kasutaja\andmeanalyys2026
copy .env.example .env
docker compose up -d --build
```

Esimene kord võtab Superseti ehitamine mitu minutit. Kontrolli importi:

```powershell
docker compose logs superset-import
```

Oodatav: zip loomine, dashboard import, `sync_datasets.py` ridade logi (veergude sünk). `superset-import` peab lõppema edukalt — muidu `superset` ei käivitu.

Ava brauseris: **http://localhost:8089** (või `.env` → `SUPERSET_PORT_HOST`)

- Kasutaja: `admin` (või `.env` → `SUPERSET_ADMIN_USER`)
- Parool: `jupiter26` (või `.env` → `SUPERSET_ADMIN_PASSWORD`)

Kui port 8088 on hõivatud, muuda `.env` failis `SUPERSET_PORT_HOST=8089`.

## Enne dashboardi

Veendu, et mart andmed on olemas:

```powershell
docker compose exec pipeline python scripts/run_pipeline.py run-all
```

`run-all` käivitab: päevased arhiivid (`data/featured/`, `data/catalog_daily/`), seejärel kataloog, viewers, featured API, meta CSV, transform ja `quality.run_checks`.

**Uus andmebaas** (esimene `docker compose up`): skeem tuleb `init/01` … `init/10`; `10_superset_views.sql` käib automaatselt. Kui DB loodi enne uuemaid init-faile:

```powershell
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/08_metadata_staging.sql
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/10_superset_views.sql
docker compose exec pipeline python scripts/run_pipeline.py run-all
```

## Imporditud dashboard

Menüüst: **Dashboards** → **Jupiteri analüüs**

| Graafik | Andmestik | Äriküsimus |
|---------|-----------|------------|
| Ühenduste kvaliteet | `mart.title_match_daily` | Ühenduste kvaliteet päeviti |
| **Päritolumaad** | `mart.v_superset_origin_pct` | 1A — struktuur % (päritolumaa) |
| **Sisutüübid** | `mart.v_superset_content_type_pct` | 1B — struktuur % (sisutüüp) |
| Esiletõstmine ja vaadatavus (sama päev) | `mart.v_featured_viewership` | 2 — viimase päeva read (ilma fallbackita) |
| Top esiletõstetud | `mart.v_superset_featured_top` | Päeva/nädala TOP (row_limit 20 chartis) |
| Korrelatsioon (päev/nädal) | `mart.v_superset_featured_correlation` | 2 — Pearson + paaride arv |

Vaated `v_superset_*` põhinevad tabelil `mart.content_structure_period_pct` (päev + nädal; ainult meta-ühendatud pealkirjad).

### Ühised filtrid

Dashboardil on kaks native filtrit:

1. **Vaade (päev/nädal)** — veerg `grain` (`daily` / `weekly`)
2. **Periood** — veerg `period_start_key` (sõltub valitud vaatest)

Filtrid mõjutavad virndiagramme ja TOP tabelit. **Korrelatsioon**, **Ühenduste kvaliteet** ja **Esiletõstmine (sama päev)** on filtritest väljas.

Pärast valikut klõpsa **Apply filters**. Ava dashboard ilma `?native_filters_key=...` URL-parameetrita, kui eelmine seis segab.

### Esiletõstmine ja vaadatavus (sama päev)

- Näitab **viimase** `staging.featured_daily.feature_date` ridu (`mart.v_featured_viewership`).
- `prominence_score_total` on alati selle päeva skoor.
- `views_total`: ainult sama päeva viewers-ist; kui fail puudub, jääb väärtus tühjaks.
- Toru **ei arvuta** Pearsoni korrelatsioonikordajat — vaid visualiseerib read.

Täpne sama päev: lisa `data/viewers/jupiter_d_YYYYMMDD-YYYYMMDD.csv` (päevafail) ja käivita `run-all`.

## Äriküsimus 1 — struktuuridiagrammid (meta CSV, päev/nädal)

Pärast `run-all` on dashboardil kaks **horisontaalset 100% virnlintdiagrammi**:

| Näidis | Graafik | Andmestik |
|--------|---------|-----------|
| [`docs/images/päritolumaad.png`](images/päritolumaad.png) | **Päritolumaad** | `mart.v_superset_origin_pct` |
| [`docs/images/sisutüübid.png`](images/sisutüübid.png) | **Sisutüübid** | `mart.v_superset_content_type_pct` |

**Paigutus (nagu PNG-del, sildid eesti keeles):**

- Kolm rida: *Kataloogi struktuur*, *Esitatud sisu struktuur*, *Vaadatud sisu struktuur*
- Telg **0–100%**, virn = `segment`, mõõdik `SUM(pct)`
- **Kataloog:** pealkirjade arv (COUNT); **esitatud:** esiletõstmise skooride summa; **vaadatud:** vaatamiste summa
- Päevavaade: konkreetne päev (`daily`)
- Nädalavaade: kataloog = union nädala päevade snapshot’itest, esitatud = nädala päevade skoorisumma, vaadatud = nädalafail `jupiter_w_*`
- Legend **paremal**; sildid tulevad `mart.ref_origin_labels` / `mart.ref_content_type_labels` tõlgetest

Kui **Vaadatud sisu struktuur** rida on tühi, puudub viewers valitud perioodi jaoks.

**Tume taust** (nagu PNG): **Dashboard properties** → **Theme** / chart **Customize** → taust `#000000`.

Kui graafik on tühi, kontrolli:

```sql
SELECT COUNT(*) FROM mart.content_structure_period_pct;
SELECT grain, period_start, structure_type, COUNT(*)
FROM mart.content_structure_period_pct
GROUP BY 1, 2, 3
ORDER BY 2 DESC, 1, 3;
```

Meta ingest + transform peavad andma ridu; `viewed` võib puududa valitud perioodis.

## Äriküsimus 2 — korrelatsioon

Imporditud dashboard sisaldab tabelit **Korrelatsioon (päev/nädal)** (`mart.v_superset_featured_correlation`):

- `corr_prominence_views` = Pearsoni korrelatsioon
- `pair_count` = mitu pealkirja läks arvutusse (mõlemad väärtused olemas)

Kui `pair_count` on väike või puudub hajuvus, võib korrelatsioon olla `NULL` (näita `N/A`).

## Scatter / bubble (korrelatsioon) käsitsi

Imporditud graafik on **tabel** (`viz_type: table`), mitte automaatne korrelatsioon.

Kui soovid scatterit, loo **Charts** → **+ Chart** → dataset `mart.v_featured_viewership_period` → **Bubble** (`bubble_v2`):

- entity = `title`
- x = `AVG(prominence_score_total)`
- y = `AVG(views_total)`

Kasuta sama `grain` + perioodi filtreid nagu dashboardi teistes plokkides.

## Andmebaasi ühendus käsitsi

Kui import ebaõnnestus:

1. **Settings** → **Database connections** → **+ Database**
2. Type: PostgreSQL
3. SQLAlchemy URI (asenda parool):

```text
postgresql+psycopg2://praktikum:praktikum@db:5432/praktikum
```

4. **+ Dataset** → vali skeem `mart` ja tabel/vaade

## Tõrkeotsing

| Probleem | Lahendus |
|----------|----------|
| Dashboard puudub | `docker compose logs superset-import`; seejärel `docker compose up -d superset` |
| Tühi struktuurgraafik | `run-all`; `SELECT COUNT(*) FROM mart.content_structure_period_pct`; meta CSV laetud? |
| Tühi „Vaadatud” rida virnas | Lisa viewers CSV sama `feature_date` jaoks; kontrolli `mart.title_match_daily` |
| TOPis `views_total` tühi | Valitud perioodis viewers puudub; tabelis kuvatakse `views_note = N/A` |
| Tühi korrelatsioon | Kontrolli `pair_count`; kui väärtusi on liiga vähe, `corr` jääb `NULL` |
| Filtrid ei muuda graafikuid | Vali periood ja klõpsa **Apply filters**; värskenda leht (Ctrl+F5). Kui ikka ei muutu, käivita `apply_virtual_dataset_sql.py` ja `apply_dashboard_filter_defaults.py` (vt import-käsk allpool) |
| Korrelatsioonis üks rida / `pair_count` = 0 | `staging.featured_daily` ja `staging.viewers_raw` päevad peavad kattuma; lisa `data/viewers/jupiter_d_YYYYMMDD-YYYYMMDD.csv` samadele päevadele mis esiletõstmine ja käivita `ingest-viewers` + `transform` |
| Tühi esiletõstmise tabel | `SELECT COUNT(*) FROM mart.v_featured_viewership_period`; käivita `run-all` |
| `superset-import` exit 1 | Logi; `10_superset_views.sql` pärast `08`; `v_featured_viewership` peab init-is olemas (stub OK) |
| `Columns missing in dataset` | `docker compose run --rm --no-deps superset-import` (sh `sync_datasets.py`) või **Datasets** → **Sync columns from source** |
| **Issue 1011** / scatter `KeyError: None` | Vana scatteri `query_context`; kustuta vana chart või dashboard; kasuta tabelit või loo uus bubble käsitsi |

Dashboardi uuesti importimiseks:

```powershell
cd C:\Users\Kasutaja\andmeanalyys2026
docker compose run --rm --no-deps superset-import
docker compose up -d superset
```

Kui import annab duplikaatvigu, kustuta vana dashboard Supersetis või lähtesta Superseti maht (ainult arenduses):

```powershell
docker compose down
docker volume rm andmeanalyys2026_superset_home
docker compose up -d --build
```

## Seos arhitektuuriga

Täpsem andmevoog, mõõdikute arvutus ja riskid: [`docs/arhitektuur.md`](arhitektuur.md).

## Kiire kontrollnimekiri (SQL)

Käivita käsud:

```powershell
docker compose exec db psql -U praktikum -d praktikum -c "SELECT COUNT(*) FROM staging.catalog_daily;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT grain, period_start, period_end, COUNT(*) FROM mart.content_structure_period_pct GROUP BY 1,2,3 ORDER BY 2 DESC,1 LIMIT 20;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT grain, period_start, period_end, COUNT(*) FROM mart.v_superset_featured_top GROUP BY 1,2,3 ORDER BY 2 DESC,1 LIMIT 20;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT grain, period_start, period_end, pair_count, corr_prominence_views FROM mart.v_superset_featured_correlation ORDER BY period_start DESC, grain LIMIT 20;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT grain, period_start, period_end, COUNT(*) FILTER (WHERE views_note='N/A') AS na_rows FROM mart.v_superset_featured_top GROUP BY 1,2,3 ORDER BY period_start DESC, grain LIMIT 20;"
```

Oodatav:

- `staging.catalog_daily` sisaldab päevaseid snapshot'e.
- `content_structure_period_pct` sisaldab nii `daily` kui `weekly` ridu.
- `v_superset_featured_top` sisaldab sama perioodistruktuuri (`grain`, `period_start`, `period_end`).
- `v_superset_featured_correlation` tagastab periooditi `pair_count` ja korrelatsiooni.
- `views_note='N/A'` read näitavad perioode, kus viewers andmed puuduvad.

