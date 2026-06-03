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

Oodatav: zip loomine, dashboard import, `apply_chart_export.py` (graffikute YAML → Superset), `sync_datasets.py` ridade logi. `superset-import` peab lõppema edukalt — muidu `superset` ei käivitu.

Ava brauseris: **http://localhost:8089** (või `.env` → `SUPERSET_PORT_HOST`)

- Kasutaja: `admin` (või `.env` → `SUPERSET_ADMIN_USER`)
- Parool: `jupiter26` (või `.env` → `SUPERSET_ADMIN_PASSWORD`)

Kui port 8088 on hõivatud, muuda `.env` failis `SUPERSET_PORT_HOST=8089`.

## Enne dashboardi

Veendu, et mart andmed on olemas:

```powershell
docker compose exec pipeline python scripts/run_pipeline.py run-all
```

`run-all` käivitab: kataloog, viewers, featured API, meta CSV, transform, `quality.run_checks` ja `check` (arhiive ei lae). Uus andmebaas: enne seda `ingest-archives` (vt README).

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
| Esiletõstmine ja vaadatavus (valitud periood) | `mart.v_superset_featured_viewership` | 2 — skoor ja vaated valitud perioodil |
| Top esiletõstetud | `mart.v_superset_featured_top` | Päeva/nädala TOP (row_limit 20 chartis); vaated veerus `views_total` (tühi = puudub) |
| Korrelatsioon (päev/nädal) | `mart.v_superset_featured_correlation` | 2 — Pearson + paaride arv |

Vaated `v_superset_*` põhinevad `mart.content_structure_period_pct` või `mart.v_featured_viewership_period` (päev + nädal). Struktuuri % (päritolu ja sisutüüp) põhineb **meta CSV-l**; pealkirjad ilma meta vasteta lähevad segmenti `Määramata (meta puudub)` (`UNKNOWN`). Viewers CSV `type` (S/Y) ei kasutata.

**Native filtrid** ei impordita automaatselt — loo need käsitsi (vt allpool). Pärast importi on dashboard ilma filtriteta kuni seadistad need UI-s.

### Esiletõstmine ja vaadatavus (valitud periood)

- Andmestik: `mart.v_superset_featured_viewership` (põhi: `mart.v_featured_viewership_period`).
- **daily:** esiletõstmine ja vaated sama päeva kohta.
- **weekly:** skooride summa nädala jooksul, vaated weekly failist.
- **`views_note`** — ainult graafikus **Esiletõstmine ja vaadatavus** (mitte TOP). Staatus **selle rea** pealkirja kohta:
  - tühi andmebaasis — `views_total` leiti; Superset võib tühja lahtrit siiski kuvada kui „N/A“ (UI, mitte andmeviga);
  - **`N/A`** andmebaasis — esiletõstmise pealkirjal **puudub** vastav rida viewers andmes (`views_total` jääb tühjaks).
- Ühendus on **täpne pealkirja vaste** pärast `mart.normalize_title` (trim, üleliigsed tühikud). Fuzzy match’i ei ole. Näide: featured `Eurovisiooni lauluvõistlus 2026. Finaal (eesti viipekeeles)` ja viewers `Eurovisiooni lauluvõistlus 2026` on erinevad read — teine võib saada vaated, esimene jääb `N/A`-ks.
- Viewers **fail** võib perioodil olemas olla, aga osa ridu on siiski `N/A` (erinev pealkiri esiletõstmises vs vaatajate ekspordis). Ülevaade: graafik **Ühenduste kvaliteet** → `viewers_match_pct` (nt ~66% 28.05.2026).
- Vajab dashboardi filtreid `grain` + `period_start_key` (sama loogika mis TOP).

### Top esiletõstetud

- Andmestik: `mart.v_superset_featured_top` (sort `prominence_score_total` DESC, chartis `row_limit` 20).
- Veerud: `title`, `prominence_score_total`, `views_total`, `in_catalog`, `primary_category_name`.
- **`views_total` tühi** = selle pealkirja vaated puuduvad valitud perioodil (pealkirja mismatch viewers CSV-ga). **`views_note` veergu TOP tabelis ei kuvata** — vaated loe otse `views_total`-ist.

Kui **kogu** perioodil viewers puudub, lae fail ja käivita pipeline:

`data/viewers/jupiter_d_YYYYMMDD-YYYYMMDD.csv` või `jupiter_w_*` → `ingest-viewers` + `transform`.

## Native filtrid käsitsi

Imporditud dashboard **ei sisalda** valmis filtreid. Loo need üks kord Supersetis.

### Eeltingimus

Andmestikel peavad olema veerud **`grain`** ja **`period_start_key`** (nt `v_superset_origin_pct`). Kontrolli: **Data** → **Datasets** → vali andmestik → veerud nähtaval.

### Filter 1 — Vaade (päev/nädal)

1. Ava **Jupiteri analüüs** → **Edit dashboard** → **Filters** → **+ Add filter**.
2. **Filter type:** Value.
3. **Filter name:** `Vaade (päev/nädal)`.
4. **Dataset:** `v_superset_origin_pct`.
5. **Column:** `grain`.
6. Soovitus: lülita sisse **Filter value is required** ja **Select first filter value by default** (või default `daily`).
7. Vahekaart **Scoping** — lülita **sisse** graafikud:
   - Päritolumaad
   - Sisutüübid
   - Top esiletõstetud
   - Esiletõstmine ja vaadatavus (valitud periood)
8. **Välista:** Ühenduste kvaliteet (kui seda filtrit ei vaja).
9. Salvesta filter.

Ühte datasetti filtri definitsioonis piisab; teised graafikud kasutavad sama veerunime oma andmestikus.

### Filter 2 — Periood

1. **+ Add filter** → **Value**.
2. **Filter name:** `Periood`.
3. **Dataset:** `v_superset_origin_pct`.
4. **Column:** `period_start_key`.
5. Kui on **Parent filter / Cascade**, vali vanemaks **Vaade (päev/nädal)**. Kui Apply jääb halliks, jäta cascade välja.
6. **Scoping** — **sama** graafikute valik nagu filter 1.
7. Salvesta, seejärel **Save** dashboard.

### Kasutamine

1. Vali **Vaade** (`daily` / `weekly`) ja **Periood** (nt `2026-05-29`).
2. Klõpsa **Apply filters**.
3. Kontroll: graafiku menüü **View query** — SQL-is peab olema `WHERE grain IN (...)` ja `period_start_key IN (...)`.

Ava dashboard ilma `?native_filters_key=...` URL-parameetrita, kui vana filteriseis segab.

### Korrelatsioon eraldi

Kui korrelatsioonitabel peaks näitama **kõiki** perioode (mitte ühte), jäta **Korrelatsioon** mõlema filtri **Scoping**-ist välja. Kui üks rida valitud perioodi kohta, lülita korrelatsioon sisse (nagu teised graafikud).

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
| TOP näitab vale järjekorda või &lt; 20 rida | Chart `row_limit` + dashboardi perioodifiltrid; `run_pipeline.py check` → **TOP vaate globaalne limiit** (kui vaates on taas globaalne LIMIT) |
| TOPis `views_total` tühi | **Selle pealkirja** jaoks viewers reas puudub (pealkirja mismatch); kontrolli `viewers_match_pct` graafikul **Ühenduste kvaliteet** |
| Esiletõstmise tabelis `views_total` tühi, `views_note = N/A` | Sama mis ülal; vaata graafikut **Esiletõstmine ja vaadatavus** |
| Tühi korrelatsioon | Kontrolli `pair_count`; kui väärtusi on liiga vähe, `corr` jääb `NULL` |
| Filtrid puuduvad pärast importi | Loo käsitsi (vt **Native filtrid käsitsi**); import ei lisa filtreid |
| Filtrid ei muuda graafikuid | Klõpsa **Apply filters**; kontrolli **View query** (`grain`, `period_start_key`); värskenda Ctrl+F5 |
| Korrelatsioonis üks rida / `pair_count` = 0 | `staging.featured_daily` ja `staging.viewers_raw` päevad peavad kattuma; lisa `data/viewers/jupiter_d_YYYYMMDD-YYYYMMDD.csv` samadele päevadele mis esiletõstmine ja käivita `ingest-viewers` + `transform` |
| Tühi esiletõstmise tabel | `SELECT grain, period_start_key, COUNT(*) FROM mart.v_superset_featured_viewership GROUP BY 1,2`; käivita `transform`; lisa viewers CSV |
| `superset-import` exit 1 | Logi; `10_superset_views.sql` pärast `08`; `v_featured_viewership` peab init-is olemas (stub OK) |
| `Columns missing in dataset` | `docker compose run --rm --no-deps superset-import` (sh `sync_datasets.py`) või **Datasets** → **Sync columns from source** |
| **Issue 1011** / scatter `KeyError: None` | Vana scatteri `query_context`; kustuta vana chart või dashboard; kasuta tabelit või loo uus bubble käsitsi |
| `Item with key "bar" is not registered` | Superset 6 ei toeta legacy `bar`; YAML-is peab olema `echarts_timeseries_bar`; käivita `apply_chart_export.py` |

Dashboardi uuesti importimiseks:

```powershell
cd C:\Users\Kasutaja\andmeanalyys2026
docker compose run --rm --no-deps superset-import
docker compose up -d superset
```

Import käivitab ka `apply_chart_export.py`, mis kirjutab graafikute nimed ja andmestikud YAML-ist üle (import ei uuenda vanu charte).

Ainult graafikud YAML-ist:

```powershell
docker compose exec superset python /app/jupiter_superset/apply_chart_export.py
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
docker compose exec db psql -U praktikum -d praktikum -c "SELECT grain, period_start_key, COUNT(*) FILTER (WHERE views_total IS NOT NULL) AS with_views, COUNT(*) FILTER (WHERE views_note='N/A') AS na_rows FROM mart.v_superset_featured_viewership GROUP BY 1,2 ORDER BY 2 DESC, 1 LIMIT 20;"
```

Oodatav:

- `staging.catalog_daily` sisaldab päevaseid snapshot'e.
- `content_structure_period_pct` sisaldab nii `daily` kui `weekly` ridu.
- `v_superset_featured_top` sisaldab sama perioodistruktuuri (`grain`, `period_start`, `period_end`).
- `v_superset_featured_correlation` tagastab periooditi `pair_count` ja korrelatsiooni.
- `views_note='N/A'` read = esiletõstmise pealkirjal **puudub** täpne vaste viewers CSV-s valitud perioodil (fail võib siiski olemas olla).

