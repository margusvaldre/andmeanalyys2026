# Arhitektuur

Jupiteri (ERR) sisu andmeanalüüsi projekt. Andmed liiguvad ERR API-st ja CSV-failidest PostgreSQL-i, transformeeritakse `mart` kihti ning visualiseeritakse Supersetis.

## Äriküsimus

1. Kuidas erinevad Jupiteri **kataloogis olemasoleva** sisu, **kasutajaliideses esiletõstetud** sisu ja **vaadatud** sisu struktuurid **sisutüüpide** ja **päritolumaad** lõikes?
2. Kui tugev on **esiletõstetuse** ja **vaadatavuse** vaheline seos?

Küsimuse 1 vastus on kaks **100% virnlintdiagrammi** (horisontaalne virn, telg 0–100%), kus võrreldakse kolme “struktuuri” read:

| Rida diagrammil | Andmeallikas | Tähendus |
|-----------------|--------------|----------|
| **Kataloogi struktuur** (catalog structure) | `staging.catalog` + meta | Mis jaotusega sisu kataloogis üldse on |
| **Esitatud sisu struktuur** (presented content structure) | `staging.featured_daily` + meta | Mis jaotusega sisu kasutajaliideses esiletõstetakse |
| **Vaadatud sisu struktuur** (viewed content structure) | `staging.viewers_raw` + meta | Mis jaotusega sisu tegelikult vaadatakse |

Küsimuse 1 täisdiagrammid eeldavad metaandmete CSV-d (`data/metadata/jupiter_metadata.csv` → `staging.content_metadata`). **Ilma meta laadimiseta** jääb alles vaheversioon (nt kataloogi API kategooria või vaadatavuse toor-`content_type`), mis ei vasta allikdiagrammidele.

### Äriküsimus 1 — mõõdikud (näidikulaud)

#### Mõõdik 1A: Päritolumaad (`Päritolumaad`)

Üks diagramm, kolm rida, 100% virn. Kategooriad (metaandmetest), näiteks:

- Eesti (Estonia)
- Euroopa Liit (European Union)
- Ühendkuningriik (United Kingdom)
- Ülejäänud maailm (Rest of the world)
- Kaastoimeline (Coproduction)
- Põhjamaad (Nordic countries)
- USA ja Kanada (USA and Canada)

**Arvutus iga rea kohta:**

| Rida | Arvutusloogika |
|------|----------------|
| Kataloog | `count(pealkirjad)` grupis `origin_country` → protsent koguarvust (100%) |
| Esitatud | `count(pealkirjad esiletõstmises)` grupis `origin_country` → protsent (100%) |
| Vaadatud | `sum(views_total)` grupis `origin_country` → protsent koguvaatustest (100%) |

Vaadatud real on mõistlik **kaaluda vaatamistega**, mitte ainult pealkirjade arvuga — nii nähtub, et väikese katalogiosaga sisu võib saada suure vaatamiste osa (nt sarjad kataloogis 7%, vaatamistes 27%).

#### Mõõdik 1B: Sisutüübid (`Sisutüübid`)

Teine diagramm, sama kolme rea loogika. Kategooriad (metaandmetest), näiteks:

- Filmid ja näidendid (Films and plays)
- Kultuur (Culture)
- Elu (Life)
- Info (Informative)
- Muusika (Music)
- Meelelahutus (Entertainment)
- Sarjad (Scripted series)
- Sport (Sport)
- Infotainment
- Uudised (News)

Arvutus on sama mis päritolumaa puhul: kataloog ja esitatud **pealkirjade arvu** järgi, vaadatud **vaatamiste summa** järgi.

#### Visuaalne võrdlus (ärianalüüs)

Diagrammid peaksid võimaldama näha **nihe** kataloogi ja vaatamise vahel, nt:

- Eesti sisu suur osa kataloogist, väiksem osa vaatamistest.
- UK või sarjad: väiksem kataloogiosakaal, suurem vaatamiste osakaal.

Supersetis: horisontaalne **100% stacked bar chart**, mõõt `metric` = protsent, dimensioonid `structure_type` + `category`.

## Äriküsimus

1. Kuidas erinevad Jupiteri kataloogis olemasoleva sisu, kasutajaliideses esiletõstetud sisu ja vaadatud sisu struktuurid žanrite ja päritolumaade lõikes?
2. Kui tugev on esiletõstetuse ja vaadatavuse vaheline seos?

### Äriküsimus 2 — mõõdikud

1. Žanrite ja päritolumaade osatähtsused (%) erinevates kihtides (kataloog, esiletõstetus, vaadatavus). Osatähtsus % = vastava žanri/päritolumaa nimetuste arv (kihis) jagatud koguarvuga * 100% . Valemit rakendatakse kõikidele kihtidele eraldi. Kihtide tulemusi võrreldakse omavahel.
2. Sisunimetuste päevased esiletõstetuse  skoorid. Iga sisunimetuse paigutus Jupiteri platvormil annab sisule teatud arvu punkte sõltuvalt sisu asukohast lehel (rida+positsioon reas) ning konkreetse lehe (esileht, sarjad, filmid, saated) nähtavuse kaalust. Lõplik skoor saadakse kõigi nende kaalutud punktide summana. Mida nähtavamatel lehtedel ja asukohtadel sisu paikneb, seda kõrgem on selle päevane esiletõstetuse skoor.
3. Korrelatsioonid esiletõstetuse ja vaadatavuse vahel. Korrelatsioonikordaja (Pearsoni korrelatsioon) valem.

## Andmeallikad

| Allikas | Tüüp | Ajas muutuv? | Roll |
|---------|------|--------------|------|
| ERR videokataloog | HTTP API | Jah, iga päev | Kataloogi koosseis (`catalog_id`, pealkiri, kategooria) |
| Jupiteri kategoorialehed (esiletõstmine) | HTTP API + konfig CSV | Jah, iga päev | Esiletõstmise skoor (`data/prominence/*.csv`) |
| Vaadatavus | CSV (`data/viewers/`) | Jah, iga päev | Vaatamiste arvud pealkirja ja päeva lõikes |
| Sisu metaandmed | CSV (`data/metadata/jupiter_metadata.csv`) | ~nädalas | **Sisutüüp** ja **päritolumaa** pealkirja kohta (küsimus 1 diagrammid) |

**Ühendusvõti** kõigi allikate vahel on **pealkiri** (`heading` kataloogis, `title` vaadatavuses ja esiletõstmises). Transform kasutab funktsiooni `mart.normalize_title()` (trim, üleliigsed tühikud).
| [Nimi] | [API / CSV / DB] | Jah, [iga X tundi / päeva] | [Milleks kasutatakse?] |
| Kataloogi sisu | API | Jah, iga päev | Kataloogi koosesisu pärimiseks |
| Esiletõstetud sisu | API | Jah, iga päev | Sisunimetuste esiletõstetuse arvutamiseks |
| Vaadatavuse andmed | CSV | Jah, iga päev | Sisunimetuste vaadatavuse pärimiseks |
| Sisu kirjeldavad metaandmed | CSV | Jah, iga nädal | Sisunimetuste žanrite, päritolumaade ja tootmisaastate pärimiseks |

## Andmevoog

```mermaid
flowchart LR
    apiCatalog[ERR kataloog API] --> ingestCatalog[ingest_catalog_api]
    apiFeatured[ERR kategooria API] --> ingestFeatured[ingest_featured_api]
    csvViewers[Vaadatavuse CSV] --> ingestViewers[ingest_viewers_csv]
    csvMeta[Meta CSV] --> ingestMeta[ingest_metadata_csv]
    configProminence[data/prominence/*.csv] --> ingestFeatured

    ingestCatalog --> stagingCatalog[(staging.catalog)]
    ingestFeatured --> stagingFeatured[(staging.featured_daily)]
    ingestViewers --> stagingViewers[(staging.viewers_raw)]
    ingestMeta --> stagingMeta[(staging.content_metadata)]

    stagingCatalog --> transform[01_transform.sql]
    stagingFeatured --> transform
    stagingViewers --> transform
    stagingMeta --> transform

    transform --> dimContent[(mart.dim_content)]
    transform --> factDaily[(mart.fact_content_daily)]
    transform --> bySource[(mart.content_by_source)]
    transform --> matchDaily[(mart.title_match_daily)]
    transform --> structurePct[(mart.content_structure_pct)]

    factDaily --> dashboard[Superset]
    bySource --> dashboard
    matchDaily --> dashboard

    scheduler[Scheduler cron 06:00] --> runAll[run_pipeline.py run-all]
    runAll --> ingestCatalog
    runAll --> ingestViewers
    runAll --> ingestFeatured
    runAll --> ingestMeta
    runAll --> transform
```

Iga ingest kirjutab käivituse logi tabelisse `staging.pipeline_runs` (`run_id`, `source_name`, `status`).


## Andmebaasi kihid

| Kiht | Roll |
|------|------|
| `staging` | Toorandmed allikatest, võimalikult lähedal API/CSV kujule. |
| `mart` | Ühendatud ja äriloogikaga tabelid analüüsiks. |
| `quality` | Andmekvaliteedi kontrollid: `quality.check_runs`, `quality.rule_results`, vaade `quality.v_latest_rule_results`; käivitus `quality.run_checks()` või `run_pipeline.py quality`. |

### Olulisemad staging tabelid

| Tabel | Kirjeldus |
|-------|-----------|
| `staging.catalog` | Üks rida `catalog_id` kohta; uued read ja pealkirja muutused |
| `staging.catalog_title_changes` | Logi, kui sama `catalog_id` pealkiri muutub |
| `staging.featured_daily` | Päevane snapshot: pealkiri + esiletõstmise skoor |
| `staging.viewers_raw` | Vaadatavus (`grain`: `daily` või `weekly`) |
| `staging.content_metadata` | Meta CSV snapshot: pealkiri, `origin_code`, `content_type_code` |
| `staging.pipeline_runs` | Toru käivituste ajalugu |

### Olulisemad mart tabelid ja vaated

| Tabel / vaade | Kirjeldus |
|---------------|-----------|
| `mart.dim_content` | Unikaalsed pealkirjad; lipud allikate ja meta kohta (`origin_country`, `meta_content_type`) |
| `mart.fact_content_daily` | Päevane ühendus esiletõstmine + vaadatavus + kataloogi kategooria |
| `mart.content_by_source` | Pealkirjade arv allika lõikes (vaheversioon ilma meta diagrammideta) |
| `mart.title_match_daily` | Päevane match rate |
| `mart.v_featured_viewership` | Read, kus sama päev on nii skoor kui vaadatavus |
| `mart.content_structure_pct` | Struktuuri %: `catalog` / `presented` / `viewed` × `origin_country` või `content_type` |
| `mart.v_superset_origin_pct` | Superset: päritolumaa 100% virn |
| `mart.v_superset_content_type_pct` | Superset: sisutüüpide 100% virn |

Tabel `mart.content_structure_pct` täidetakse transformiga: üks rida = `(structure_type, dimension, category, pct)`. Meta CSV koodid (`EST`, `FILM`, …) tõlgitakse eestikeelseteks siltideks tabelites `mart.ref_origin_labels` ja `mart.ref_content_type_labels`.

Transform kustutab mart tabelid ja täidab need uuesti (`scripts/01_transform.sql`). Staging säilitab ajaloo (sh vanemad vaadatavuse laadimised erinevate `run_id`-dega).

## Automatiseerimine

| Komponent | Kirjeldus |
|-----------|-----------|
| `scheduler` konteiner | Cron, ajavöönd `Europe/Tallinn` |
| `scheduler/crontab` | Iga päev kell **06:00** → `python scripts/run_pipeline.py run-all` (sh transform ja `quality.run_checks`) |
| `logs/pipeline.log` | Scheduleri standardväljund |

Enne cron'i peab uus vaadatavuse päevafail (`jupiter_d_YYYYMMDD-YYYYMMDD.csv`) olema kaustas `data/viewers/`, et esiletõstmise ja vaadatavuse päevad kattuksid.

## Tööjaotus

| Roll | Vastutus | Täitja |
|------|----------|--------|
| Andmeallika omanik | Kirjutab sissevõtu loogika, hoiab API-t töös | Raul Lobanov |
| Transformatsioonide omanik | Kirjutab mart kihi mudelid ja mõõdikute arvutuse | [Nimi] |
| Kvaliteedi omanik | Kirjutab testid ja vaatab läbi ebaõnnestunud kontrollid | Margus Valdre |
| Näidikulaua omanik | Ehitab näidikulaua ja seob selle äriküsimusega | Anu Aus |

## Riskid

| Risk | Mõju | Maandus |
|------|------|---------|
| [Risk 1 — näiteks: API ei vasta] | [Mis juhtub?] | [Kuidas maandad?] |
| [Risk 2 - sisnimetused erinevates kihtides ei ole vastavuses] | Sisunimetus on olemas kataloogis, kuid ei saa esletõstetuse ja/või vaadatavuse näitajaid. Sisu on vaadataud, aga sama nimetus ei esine kataloogis. Jne | [Kuidas maandad?] |
| Puuduv sisunimetus metaandmetes  | Sisunimetus ei saa endale külge žanri ja/või päritolumaad. | Hinnata osakaalu, kas jätta välja või täita käsitsi |
| Liiga lühike analüüsiperiood  | Lühike periood võib moonutada tulemust - ühekordne suur "sündmus" | Vältida põhjuslike järelduste tegemist, analüüsi kordamine pikema perioodi jooksul tulevikus |
| Unikaalse identifikaatori puudumine  | Andmete sidumine toimub pealkirjade järgi, mis võivad allikati erineda  | Lisada andmevoogu andmekvaliteedi kontrollid |

## Privaatsus ja turve

Projekt kasutab ainult avalikke andmeid. Isikuandmeid ei koguta.Andmebaasi kasutajanimi ja parool tulevad .env failist. .env faili ei tohi reposse lisada.
