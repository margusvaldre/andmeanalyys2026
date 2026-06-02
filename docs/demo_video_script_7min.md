# Demo video skript (7 min)

Luhiversioon hindamisvideo jaoks, kui aeg on piiratud.

Eesmärk:
- katta kohustuslikud nõuded,
- näidata töötavat andmevoogu,
- tõestada SQL + dashboard seos.

Soovituslik pikkus: 6:30-7:00.

---

## 1) Slaidid (max 5 slaidi)

### Slaid 1 - Eesmärk ja äriküsimused
- Kuidas erinevad kataloogi/esitatud/vaadatud sisu struktuurid?
- Kui tugev on esiletõstmise ja vaadatavuse seos?

### Slaid 2 - Nõuete checklist
- [x] ingest mitmest allikast
- [x] automatiseeritud workflow
- [x] SQL transform
- [x] quality/check kontrollid
- [x] Superset dashboard

### Slaid 3 - Arhitektuur (üks pilt)
- `API + CSV -> staging -> mart -> Superset`

### Slaid 4 - Peamised tulemused
- workflow käivitus edukalt
- kvaliteedikontrollid olemas
- dashboardis mõõdikud olemas

### Slaid 5 - Piirang + järgmine samm
- pealkirja-põhine matching
- järgmine samm: parem title mapping / id-põhine sidumine

---

## 2) Minutipõhine kõnetekst + käsud

### 0:00-0:40
"Näitan lühidalt, kuidas projekt täidab nõuded: ingest, transform, kvaliteedikontrollid ja dashboard."

### 0:40-1:30
"Siin on nõuete checklist ja arhitektuur: andmed tulevad allikatest stagingusse, transform arvutab mart vaated, Superset visualiseerib tulemuse."

### 1:30-3:00
"Teen live demo: käivitan `run-all` ja näitan, et sammud töötavad otsast lõpuni."

```powershell
cd C:\Users\Kasutaja\andmeanalyys2026
docker compose ps
docker compose exec pipeline python scripts/run_pipeline.py run-all
docker compose exec db psql -U praktikum -d praktikum -c "SELECT started_at, source_name, status, row_count FROM staging.pipeline_runs ORDER BY started_at DESC LIMIT 6;"
```

Mida öelda:
- "Kontrollin, et teenused on üleval."
- "Käivitan täistoru: ingest, transform, quality, check."
- "Tabelist on näha, et sammud päriselt käisid."

### 3:00-4:20
"Näitan SQL päringutega äriküsimuse 1 tulemust: struktuuri protsendid."

```powershell
docker compose exec db psql -U praktikum -d praktikum -c "SELECT structure_type, category_label, pct FROM mart.content_structure_period_pct WHERE grain='daily' AND period_start='2026-05-30' AND dimension='content_type' ORDER BY structure_type, pct DESC LIMIT 15;"
```

Mida öelda:
- "See näitab struktuuri võrdlust kataloogi, esitatud ja vaadatud sisu vahel."

### 4:20-5:20
"Näitan SQL päringutega äriküsimuse 2 tulemust: viewers_match_pct, pair_count ja korrelatsioon."

```powershell
docker compose exec db psql -U praktikum -d praktikum -c "SELECT activity_date, featured_count, viewers_match_pct FROM mart.title_match_daily ORDER BY activity_date DESC LIMIT 5;"
docker compose exec db psql -U praktikum -d praktikum -c "SELECT grain, period_start_key, pair_count, corr_prominence_views FROM mart.v_superset_featured_correlation ORDER BY period_start DESC, grain LIMIT 8;"
```

Mida öelda:
- "`viewers_match_pct` näitab ühenduste kvaliteeti."
- "`pair_count` näitab, kas korrelatsioon on usaldusväärne."

### 5:20-6:30
"Näitan Supersetis samu tulemusi graafikutena sama päevafiltriga."

```powershell
docker compose exec pipeline python scripts/run_pipeline.py check
```

Supersetis ava:
- http://localhost:8089
- Dashboard: **Jupiteri analüüs**
- Filtrid: `grain = daily`, `period_start_key = 2026-05-30`

Näita graafikud:
- Päritolumaad
- Sisutüübid
- Esiletõstmine ja vaadatavus
- TOP esiletõstetud
- Korrelatsioon

Mida öelda:
- "Need graafikud kasutavad samu mart vaateid, mida SQL-iga just näitasin."
- "`check` kinnitab, et workflow on terviklik."

### 6:30-7:00
"Kokkuvõte: nõuded täidetud, andmevoog töötab, SQL ja dashboard vastavad äriküsimustele."

---

## 3) Ultralühike varuplaan (3 min)

Kui aega jääb väga vähe, tee ainult:

```powershell
docker compose exec pipeline python scripts/run_pipeline.py run-all
docker compose exec pipeline python scripts/run_pipeline.py check
docker compose exec db psql -U praktikum -d praktikum -c "SELECT period_start_key, pair_count, corr_prominence_views FROM mart.v_superset_featured_correlation ORDER BY period_start DESC LIMIT 3;"
```

Lõpulause:
- "Workflow töötas, kontrollid läbisid ja dashboard visualiseerib mart vaateid."

