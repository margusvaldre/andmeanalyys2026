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
docker compose exec db psql -U praktikum -d praktikum -f /docker-entrypoint-initdb.d/06_superset_views.sql
docker compose exec pipeline python scripts/run_pipeline.py run-all
```

## Imporditud dashboard

Menüüst: **Dashboards** → **Jupiteri analüüs**

| Graafik | Andmestik | Äriküsimus |
|---------|-----------|------------|
| Ühenduste kvaliteet | `mart.title_match_daily` | Andmekvaliteet / ühendused |
| Struktuuri protsendid | `mart.v_superset_structure_pct` | 1 (vaheversioon) |
| Esiletõstmine ja vaadatavus (sama päev) | `mart.v_featured_viewership` | 2 (tabelina; scatter eemaldatud impordi piirangute tõttu) |
| Top esiletõstetud | `mart.v_superset_featured_top` | Esiletõstmise ülevaade |

Kui scatter on tühi, puuduvad sama päeva vaadatavuse andmed (vt `docs/arhitektuur.md`).

## Äriküsimus 1 — täisversioon (meta CSV)

Kui `data/metadata/jupiter_metadata.csv` on laetud ja transform käinud, ehita kaks **horisontaalset 100% virnlintdiagrammi**:

1. **Päritolumaad** — dataset `mart.v_superset_origin_pct` (read: kataloog / esitatud / vaadatud).
2. **Sisutüübid** — dataset `mart.v_superset_content_type_pct` (sama loogika).

Olemasolev imporditud graafik **Struktuuri protsendid** kasutab vaadet `mart.v_superset_structure_pct`, mis pärast meta laadimist näitab sisutüüpe meta CSV-st (mitte vaadatavuse toor-koode ega kataloogi kategooriat).

Superseti seaded (Bar chart):

- **X-axis:** `structure_label` (või sarnane väli)
- **Metrics:** `SUM(pct)` või eelarvutatud `pct`
- **Dimensions / Series:** kategooria (päritolumaa või sisutüüp)
- **Stacked:** Stack
- **Normalize / Contribution mode:** 100% (kui Superset pakub “Percentages” või “Contribution”)

Vaadatud rea puhul arvuta protsent **vaatamiste summast**, mitte ainult pealkirjade arvust.

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
| `superset-import` exit 1 | Vaata logi; kontrolli, et `06_superset_views.sql` on käinud |
| `Columns missing in dataset` | Imporditud datasetil polnud veergude metaandmeid. **Lahendus A:** käivita uuesti import (vt allpool). **Lahendus B:** Supersetis **Data** → **Datasets** → vali dataset → **Columns** → **Sync columns from source**. |
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
