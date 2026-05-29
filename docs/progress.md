# Edenemisraport

## Mis on valmis

- [ ] Docker Compose käivitab PostgreSQL-i, töövoo konteineri, scheduleri ja Superseti näidikulaua.
- [ ] ERR API-dest saab kätte videokataloogi andmed ning sisu esiletõstmise info kategoorialehtedel.
- [ ] Sisu päritolumaad ja tüübid on eraldi staatilises `staging.content_metadata` tabelis, mis laetakse metaandmete CSV-failist.
- [ ] Andmed liiguvad `staging` kihist `mart` kihti
- [ ] Näidikulaud võimaldab võrrelda kataloogi struktuuri ja esiletõstetud sisu struktuure päritolumaade järgi 100% virnlintdiagrammide abil.
- [ ] Näidikulaud võimaldab võrrelda kataloogi struktuuri ja esiletõstetud sisu struktuure sisutüübi järgi 100% virnlintdiagrammide abil.
- [ ] Näidikulaual on Eesiletõstmine ja vaadatavus (sama päev).
- [ ] Scheduler käivitab töövoo vaikimisi igal hommikul kell 06:00, et uued päevaandmed sisse tõmmata ja transformeerida


## Järgmised sammud

- Lisada võimalus valida päeva, mille kohta näidikud andmeid kuvavad (ajalugu). Hetkel näitab ainult andmete sisselugemise päeva
- Nädala vaadatavuse toomine mõõdikulauale. Hetkel salvestatakse andmed baasi aga näidikulauale ei jõua
- Esitlusskoori ja vaadatavuse korrelatsiooni lisamine
- Näidikute vaate seadistamine Supersetis - vaatajasõbralikumaks

## Mis takistab

- Juhul kui arendus/testperioodil kõik nullist alustada (docker compose down -v) siis kaovad ära mõningad testimiseks vajalikud ajaloolised andmed (featured ja catalog_daily), seega tuleb oodata kuni uuesti koguneb (andmebaasist õigeaegselt koopia tegemine on vähetõenäoline)
Lahendus - andmete sisselugemisel teha päevastest snapshotidest varukoopia /data kataloogi
Kui andmetoru on lives ja cron töötab regulaarselt siis pole neid varukoopiaid tõenäoliselt vaja ja selle funktsionaalsuse võib maha võtta

## Kontrollpunkt

Käsk, millega saab kontrollida, et töövoog töötab:

```bash
docker compose exec pipeline python scripts/run_pipeline.py check
```
Oodatav tulemus:

Jupiteri toru kontroll (allikas -> staging -> mart -> Superseti vaated)

[OK  ] Fail meta CSV: jupiter_metadata.csv olemas
[OK  ] Failid viewers (daily): 10 faili kaustas data/viewers/
[OK  ] Failid viewers (weekly): 2 nädala faili
[OK  ] DB ühendus: PostgreSQL vastab
[OK  ] Tabel staging.catalog: olemas
[OK  ] Tabel staging.featured_daily: olemas
[OK  ] Tabel staging.viewers_raw: olemas
[OK  ] Tabel staging.content_metadata: olemas
[OK  ] Tabel mart.dim_content: olemas
[OK  ] Tabel mart.content_structure_pct: olemas
[OK  ] Tabel mart.fact_content_daily: olemas
[OK  ] Tabel mart.title_match_daily: olemas
[OK  ] Vaade mart.v_featured_viewership: olemas
[OK  ] Vaade mart.v_superset_origin_pct: olemas
[OK  ] Vaade mart.v_superset_content_type_pct: olemas
[OK  ] Vaade mart.v_superset_featured_top: olemas
[OK  ] staging.catalog: 3218 rida
[OK  ] staging.content_metadata: 4838 rida
[OK  ] staging.featured_daily: 1938 rida
[OK  ] staging.viewers_raw (daily): 50152 rida
[WARN] Päevade kattumine (featured vs viewers): featured=2026-05-28, viewers=2026-05-25 — views_total võib olla tühi viimasel featured päeval
[OK  ] mart.dim_content: 6440 rida
[OK  ] mart.dim_content (meta): 4838 rida
[OK  ] mart.content_structure_pct: 38 rida
[OK  ] mart.fact_content_daily: 14476 rida
[OK  ] mart.v_featured_viewership: 970 rida
[OK  ] mart.v_superset_origin_pct: 105 rida
[OK  ] mart.v_superset_content_type_pct: 180 rida
[OK  ] mart.v_superset_featured_top: 500 rida
[WARN] Struktuur: vaadatud rida: viewed struktuuri read puuduvad — viewers CSV võib puududa featured päeval
[OK  ] Quality viimane käivitus: passed (run_pipeline.py, 2026-05-28 05:21:07.875674+00:00)

Kokkuvõte: 29 OK, 2 WARN, 0 FAIL
Tulemus: HOIATUS — toru töötab, aga on tähelepanu vajavaid kohti.
