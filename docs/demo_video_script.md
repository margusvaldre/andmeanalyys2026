# Demo video skript (alla 10 min)

See fail koondab ühte kohta:

1. slaidide outline'i,
2. minutipõhise kõneteksti,
3. vastavad copy-paste käsuplokid.

Soovituslik kogupikkus: 8:30-9:30.

---

## 1) Slaidide outline (10 slaidi)

### Slaid 1 - Projekt ja eesmärk
- Projekt: Jupiteri andmeanalüüsi toru
- Eesmärk 1: võrrelda kataloogi/esitatud/vaadatud sisu struktuuri
- Eesmärk 2: hinnata esiletõstmise ja vaadatavuse seost

### Slaid 2 - Kohustuslikud nõuded (checklist)
- [x] Mitmest allikast ingest (API + CSV + metadata CSV)
- [x] Automatiseeritud workflow (`run-all`, scheduler)
- [x] SQL transform `staging -> mart`
- [x] Andmekvaliteedi kontrollid (`quality`, `check`)
- [x] Näidikulaud (Superset)
- [x] Reprodutseeritav käivitus (Docker + README)

### Slaid 3 - Arhitektuur
- Allikad: ERR API, viewers CSV, metadata CSV
- Kihid: `staging`, `mart`, `quality`
- Väljund: Superset dashboard
- Lisa skeem pildina (`docs/arhitektuur.md` põhjal)

### Slaid 4 - Andmevoog sammudena
- 1) ingest (`ingest-all`)
- 2) transform (`01_transform.sql`)
- 3) quality (`quality.run_checks`)
- 4) read-only kontroll (`check`)
- 5) visualiseerimine Supersetis

### Slaid 5 - Andmekvaliteet
- Tühjad pealkirjad / negatiivsed väärtused / kuupäeva loogika
- `viewers_match_pct` läved
- `pair_count` kontroll korrelatsioonile
- `SUM(pct)` kontroll struktuurigraafikule (~100%)

### Slaid 6 - SQL väljundid (äriküsimus 1)
- `mart.content_structure_period_pct`
- Kataloog vs esitatud vs vaadatud struktuur
- Päritolumaa + sisutüüp

### Slaid 7 - SQL väljundid (äriküsimus 2)
- `mart.v_superset_featured_correlation`
- `pair_count` + `corr_prominence_views`
- `mart.title_match_daily` (`viewers_match_pct`)

### Slaid 8 - Dashboard (Superset)
- Graafikud:
  - Päritolumaad
  - Sisutüübid
  - Esiletõstmine ja vaadatavus
  - TOP esiletõstetud
  - Korrelatsioon
- Filtrid: `grain`, `period_start_key`

### Slaid 9 - Demo kokkuvõte
- Workflow käivitus edukalt
- SQL arvutused andsid ootuspärase tulemuse
- Dashboard peegeldab mart vaateid
- Nõuded täidetud

### Slaid 10 - Piirangud ja järgmised sammud
- Pealkirja-põhine matching (mitte fuzzy)
- Metadata katvus mõjutab segmente
- Järgmine samm: parem title mapping / id-põhine sidumine

---

## 2) Kõnetekst + käsud (minutite kaupa)

### 0:00-0:40
"Tere! Näitan lühidalt Jupiteri andmeanalüüsi projekti. Eesmärk oli ehitada töötav andmevoog, mis vastab kohustuslikele nõuetele: ingest mitmest allikast, SQL transform, kvaliteedikontrollid ja Superseti näidikulaud."

### 0:40-1:30
"Siin on nõuete checklist. Iga punkt on projektis implementeeritud: ingest-allikad, automatiseeritud run-all, quality/check kontrollid, mart vaated ja dashboard. Demo teises osas näitan live'is, et toru käivitub otsast lõpuni."

### 1:30-2:15
"Arhitektuur on kihiline: allikad tulevad stagingusse, transform SQL arvutab mart kihi tabelid ja vaated, quality salvestab kontrolli tulemused, ning Superset loeb mart vaateid."

### 2:15-3:00
"Workflow sammud on: ingest, transform, quality, check. `run-all` teeb need järjest automaatselt."

### 3:00-4:00 (Terminal)
"Käivitan workflow ja näitan, et kõik sammud jooksevad järjest."

```powershell
cd C:\Users\Kasutaja\andmeanalyys2026
docker compose ps
docker compose exec pipeline python scripts/run_pipeline.py run-all
docker compose exec db psql -U praktikum -d praktikum -c "SELECT started_at, source_name, status, row_count FROM staging.pipeline_runs ORDER BY started_at DESC LIMIT 8;"
```

Mida öelda:
- "Kontrollin, et teenused on üleval: db, pipeline, scheduler, superset."
- "`run-all` teeb ingest + transform + quality + check."
- "Siit on näha iga toru sammu käivitused ja staatused."

### 4:00-5:15 (SQL - äriküsimus 1)
"Esimene SQL kontroll vastab äriküsimusele 1: sisu struktuur. See näitab protsente kategooriate kaupa ning võrdlust kataloogi, esitatud ja vaadatud sisu vahel."

```powershell
docker compose exec db psql -U praktikum -d praktikum -c "SELECT structure_type, category_label, pct FROM mart.content_structure_period_pct WHERE grain='daily' AND period_start='2026-05-30' AND dimension='content_type' ORDER BY structure_type, pct DESC LIMIT 18;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT structure_type, category_label, pct FROM mart.content_structure_period_pct WHERE grain='daily' AND period_start='2026-05-30' AND dimension='origin_country' ORDER BY structure_type, pct DESC LIMIT 18;"
```

Mida öelda:
- "Need päringud näitavad, kuidas struktuur erineb kataloogi, esitatud ja vaadatud sisu vahel."

### 5:15-6:20 (SQL - äriküsimus 2)
"Teine SQL kontroll näitab ühenduste kvaliteeti ja korrelatsiooni: kui hästi featured pealkirjad kattuvad viewers andmetega ning kui palju ridu korrelatsioonis osaleb."

```powershell
docker compose exec db psql -U praktikum -d praktikum -c "SELECT activity_date, featured_count, viewers_match_pct, catalog_match_pct FROM mart.title_match_daily ORDER BY activity_date DESC LIMIT 5;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT grain, period_start_key, pair_count, corr_prominence_views FROM mart.v_superset_featured_correlation ORDER BY period_start DESC, grain LIMIT 10;"
```

Mida öelda:
- "`viewers_match_pct` näitab ühenduste kvaliteeti."
- "`pair_count` näitab, kui usaldusväärne korrelatsioon on."

### 6:20-7:40 (Dashboard)
"Avan Superseti dashboardi, panen päevafiltri ja näitan samu tulemusi visuaalselt: struktuur, TOP ja korrelatsioon."

Dashboard sammud:
1. Ava brauseris `http://localhost:8089`
2. Ava dashboard **Jupiteri analüüs**
3. Sea filtrid:
   - `grain = daily`
   - `period_start_key = 2026-05-30`
4. Näita graafikuid:
   - Päritolumaad
   - Sisutüübid
   - Esiletõstmine ja vaadatavus
   - TOP esiletõstetud
   - Korrelatsioon

Mida öelda:
- "Need graafikud loevad samu mart vaateid, mida SQL päringutega just kontrollisime."

### 7:40-8:30 (Kvaliteedikontroll)
"Kvaliteedireeglid kontrollivad kriitilisi andmevigu ja analüüsi usaldusväärsust, sh viewers match protsenti, pair_count'i ja struktuuriprotsentide summat."

```powershell
docker compose exec pipeline python scripts/run_pipeline.py quality
docker compose exec pipeline python scripts/run_pipeline.py check
docker compose exec db psql -U praktikum -d praktikum -c "SELECT rule_name, severity, message, failing_count FROM quality.v_latest_rule_results WHERE severity <> 'pass' ORDER BY severity DESC, rule_name;"
```

Mida öelda:
- "Siin on viimase käivituse kvaliteeditulemused, sh warningud ja võimalikud failid."

### 8:30-9:00 (Lõpp)
"Kokkuvõtteks: projekt täidab nõuded, andmevoog töötab, kvaliteedikontrollid on implementeeritud ja dashboard vastab äriküsimustele."

---

## 3) 30-sekundiline fallback (kui aeg saab otsa)

Kui video lõpus jääb aega väga vähe, kasuta ainult neid:

```powershell
docker compose exec pipeline python scripts/run_pipeline.py run-all
docker compose exec pipeline python scripts/run_pipeline.py check
docker compose exec db psql -U praktikum -d praktikum -c "SELECT grain, period_start_key, pair_count, corr_prominence_views FROM mart.v_superset_featured_correlation ORDER BY period_start DESC, grain LIMIT 5;"
```

Lõpulause:
- "Workflow käivitus, kontrollid läbisid ja korrelatsiooni vaade on olemas; dashboard visualiseerib sama andmemudelit."

