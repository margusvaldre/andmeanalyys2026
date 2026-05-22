# Superset — Jupiteri näidikulaud

Apache Superset ühendub sama PostgreSQL-iga (`mart` skeem) ja kuvab kataloogi, esiletõstmise ja vaadatavuse mõõdikuid.

## Käivitus

```powershell
cd C:\Users\Kasutaja\andmeanalyys2026
docker compose up -d --build
```

Esimene kord võtab Superseti ehitamine mitu minutit. Kontrolli importi:

```powershell
docker compose logs superset-import
```

Ava brauseris: **http://localhost:8089** (või `.env` → `SUPERSET_PORT_HOST`)

- Kasutaja: `admin` (või `.env` → `SUPERSET_ADMIN_USER`)
- Parool: `jupiter26` (või `.env` → `SUPERSET_ADMIN_PASSWORD`)

Kui port 8088 on hõivatud, muuda `.env` failis `SUPERSET_PORT_HOST=8089`.

## Enne dashboardi

Veendu, et mart andmed on olemas:

```powershell
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/10_superset_views.sql
docker compose exec pipeline python scripts/run_pipeline.py run-all
```

## Imporditud dashboard

Menüüst: **Dashboards** → **Jupiteri analüüs**

| Graafik | Andmestik | Äriküsimus |
|---------|-----------|------------|
| Ühenduste kvaliteet | `mart.title_match_daily` | Andmekvaliteet / ühendused |
| **Päritolumaad** | `mart.v_superset_origin_pct` | 1A (100% virn, horisontaalne) |
| **Sisutüübid** | `mart.v_superset_content_type_pct` | 1B (100% virn, horisontaalne) |
| Esiletõstmine ja vaadatavus (sama päev) | `mart.v_featured_viewership` | 2 (tabelina) |
| Top esiletõstetud | `mart.v_superset_featured_top` | Esiletõstmise ülevaade |

Kui esiletõstmise päev on uuem kui viimane viewers CSV (nt featured 21.05, daily viewers 19.05), täidab `mart.v_featured_viewership` `views_total` **viimase olemasoleva** vaadatavuse päevaga sama pealkirja kohta (mitte sama kalendripäev). Täpne sama päev: lisa `data/viewers/jupiter_d_YYYYMMDD-YYYYMMDD.csv` ja käivita `run-all`.

## Äriküsimus 1 — struktuuridiagrammid (meta CSV)

Pärast `run-all` imporditakse dashboardile kaks **horisontaalset 100% virnlintdiagrammi**, vastavalt näidistele:

| Näidis | Graafik | Andmestik |
|--------|---------|-----------|
| [`docs/images/päritolumaad.png`](images/päritolumaad.png) | **Päritolumaad** | `mart.v_superset_origin_pct` |
| [`docs/images/sisutüübid.png`](images/sisutüübid.png) | **Sisutüübid** | `mart.v_superset_content_type_pct` |

**Paigutus (nagu PNG-del, sildid eesti keeles):**

- Kolm rida: *Kataloogi struktuur*, *Esitatud sisu struktuur*, *Vaadatud sisu struktuur*
- Telg **0–100%**, virn = `segment` (päritolumaa või sisutüüp), mõõdik `SUM(pct)`, väärtused ribadel
- Legend **paremal**; kategooriad tulevad `mart.ref_origin_labels` / `mart.ref_content_type_labels` tõlgetest

**Tume taust** (nagu PNG): Supersetis **Dashboard properties** → **Theme** / chart **Customize** → taust `#000000` (imporditud YAML ei sea alati teemat üle).

Olemasolevas DB-s uuenda vaated:

```powershell
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/10_superset_views.sql
```

Kui graafik on tühi, kontrolli: `SELECT COUNT(*) FROM mart.content_structure_pct;` peab olema > 0 (meta ingest + transform).

## Scatter / bubble (korrelatsioon) käsitsi

Imporditud **legacy scatter** võis jääda andmebaasis `aggregate: null` olekusse (`KeyError: None`). Uus import kasutab **tabelit** sama vaatega.

Kui sul on sama päeva andmed, loo scatter **Charts** → **+ Chart** → dataset `mart.v_featured_viewership` → **Bubble** (`bubble_v2`): entity = `title`, x = `AVG(prominence_score_total)`, y = `AVG(views_total)`.

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
| Dashboard puudub | `docker compose logs superset-import`; seejärel `docker compose up -d --build superset` |
| Tühi graafik | Käivita `run-all`; kontrolli `SELECT COUNT(*) FROM mart.fact_content_daily` |
| `superset-import` exit 1 | Vaata logi; kontrolli, et `10_superset_views.sql` on käinud (pärast `08`) |
| `Columns missing in dataset` | Vale graafik dashboardil (parandatud `chartId` impordis) või dataset ilma veergudeta. **Lahendus:** `docker compose run --rm --no-deps superset-import` (sisaldab `sync_datasets.py`) või **Data** → **Datasets** → **Sync columns from source**. |
| **Issue 1011** / scatter `KeyError: None` | Superset salvestab graafiku **query_context**; import **ei kirjuta** olemasolevat chart UUID-d alati üle. Legacy scatter jättis `aggregate: null`. **Lahendus:** uus graafik **UUID** + **tabel** (repo uuendatud). Käivita import uuesti; **kustuta vana dashboard** Supersetis, kui näed kahte sama nimega plokki. Scatteri saad hiljem **Explore** → chart tüüp **Bubble** või **Bar**. |

Dashboardi uuesti importimiseks (pärast `dashboard_export` muudatusi, nt veergude parandus):

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
