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



`run-all` käivitab neli ingesti, `scripts/01_transform.sql` (sh `mart.content_structure_pct` ja Superseti vaated) ning `quality.run_checks`.



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

| Esiletõstmine ja vaadatavus (sama päev) | `mart.v_featured_viewership` | 2 — skoor vs vaated (tabel) |

| Top esiletõstetud | `mart.v_superset_featured_top` | Viimase featured päeva TOP |



Vaated `v_superset_*` põhinevad tabelil `mart.content_structure_pct` (viimane esiletõstmise päev; ainult meta-ühendatud pealkirjad).



### Esiletõstmine ja vaadatavus (tabel)



- Näitab **viimase** `staging.featured_daily.feature_date` ridu.

- `prominence_score_total` on alati selle päeva skoor.

- `views_total`: eelistatult **sama päeva** päevane viewers CSV; kui fail puudub, täidab transform **viimase olemasoleva** vaadatavuse päeva väärtusega sama pealkirja kohta.

- Toru **ei arvuta** Pearsoni korrelatsioonikordajat — vaid visualiseerib read.



Täpne sama päev: lisa `data/viewers/jupiter_d_YYYYMMDD-YYYYMMDD.csv` (päevafail) ja käivita `run-all`.



## Äriküsimus 1 — struktuuridiagrammid (meta CSV)



Pärast `run-all` on dashboardil kaks **horisontaalset 100% virnlintdiagrammi**:



| Näidis | Graafik | Andmestik |

|--------|---------|-----------|

| [`docs/images/päritolumaad.png`](images/päritolumaad.png) | **Päritolumaad** | `mart.v_superset_origin_pct` |

| [`docs/images/sisutüübid.png`](images/sisutüübid.png) | **Sisutüübid** | `mart.v_superset_content_type_pct` |



**Paigutus (nagu PNG-del, sildid eesti keeles):**



- Kolm rida: *Kataloogi struktuur*, *Esitatud sisu struktuur*, *Vaadatud sisu struktuur*

- Telg **0–100%**, virn = `segment`, mõõdik `SUM(pct)`

- **Kataloog:** pealkirjade arv (COUNT); **esitatud:** esiletõstmise skooride summa; **vaadatud:** vaatamiste summa (päevane CSV)

- Legend **paremal**; sildid tulevad `mart.ref_origin_labels` / `mart.ref_content_type_labels` tõlgetest



Kui **Vaadatud sisu struktuur** rida on tühi, puudub viewers CSV viimase featured päevaga samal kuupäeval (vt `mart.title_match_daily.viewers_match_pct`).



**Tume taust** (nagu PNG): **Dashboard properties** → **Theme** / chart **Customize** → taust `#000000`.



Kui graafik on tühi, kontrolli:



```sql

SELECT COUNT(*) FROM mart.content_structure_pct;

SELECT structure_type, COUNT(*) FROM mart.content_structure_pct GROUP BY 1;

```



Meta ingest + transform peavad andma ridu; `viewed` võib puududa, kui päevad ei kattu.



## Scatter / bubble (korrelatsioon) käsitsi



Imporditud graafik on **tabel** (`viz_type: table`), mitte automaatne korrelatsioon.



Kui soovid scatterit või Pearsoni kordajat, loo **Charts** → **+ Chart** → dataset `mart.v_featured_viewership` → **Bubble** (`bubble_v2`):



- entity = `title`

- x = `AVG(prominence_score_total)`

- y = `AVG(views_total)`



Eelda sama päeva andmeid või mõista `views_total` fallbacki piiranguid (vt ülal).



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

| Tühi struktuurgraafik | `run-all`; `SELECT COUNT(*) FROM mart.content_structure_pct`; meta CSV laetud? |

| Tühi „Vaadatud” rida virnas | Lisa viewers CSV sama `feature_date` jaoks; kontrolli `mart.title_match_daily` |

| Tühi esiletõstmise tabel | `SELECT COUNT(*) FROM mart.v_featured_viewership`; käivita `run-all` |

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


