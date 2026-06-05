# Edenemisraport

## Mis on valmis

- [x] Docker Compose käivitab PostgreSQL-i, töövoo konteineri, scheduleri ja Superseti näidikulaua.
- [x] ERR API-dest saab kätte videokataloogi andmed ning sisu esiletõstmise info kategoorialehtedel.
- [x] Sisu päritolumaad ja tüübid on eraldi staatilises `staging.content_metadata` tabelis, mis laetakse metaandmete CSV-failist.
- [x] Andmed liiguvad `staging` kihist `mart` kihti.
- [x] Näidikulaud võimaldab võrrelda kataloogi, esitatud ja vaadatud sisu struktuuri päritolumaade järgi (`mart.v_superset_origin_pct`, filter `grain` + periood).
- [x] Näidikulaud võimaldab võrrelda struktuuri sisutüübi järgi (`mart.v_superset_content_type_pct`).
- [x] Näidikulaud kuvab esiletõstmise skoori ja vaadatavust valitud perioodil (`mart.v_superset_featured_viewership`, `views_note`).
- [x] Korrelatsioon esiletõstmise ja vaatamiste vahel (`mart.v_superset_featured_correlation`, `pair_count`).
- [x] Scheduler käivitab töövoo vaikimisi igal hommikul kell 06:00 (`run-all`: ingest + transform + quality + check).
- [x] Päevased kataloogi ja featured snapshotid salvestatakse `data/catalog_daily/` ja `data/featured/` (taastamine: `ingest-archives`).

## Järgmised sammud

- Ajaloolise perioodi valik dashboardil (praegu filtrid `grain` + `period_start_key`; vajadusel rohkem UX-i).
- Parem pealkirja ühendus (id-põhine sidumine või fuzzy mapping), et tõsta `viewers_match_pct`.
- Näidikulaua viimistlus Supersetis (filtrid, paigutus).

## Mis takistab

- `docker compose down -v` kustutab andmebaasi; ajaloolised `featured` / `catalog_daily` read tuleb uuesti `ingest-archives` või cron-iga koguda.
- Vaadatavuse CSV (`data/viewers/`) peab enne cron'i olemas — muidu jääb viimane featured päev ilma `views_total`-ita.

## Kontrollpunkt

```bash
docker compose exec pipeline python scripts/run_pipeline.py check
```

Oodatav: peamiselt **OK**, võimalikud **WARN** (nt `viewers_match_pct` &lt; 70%, featured vs viewers päevade vahe). **FAIL** tähendab toru katkestust `run-all` lõpus.

Täpsemad läved ja tõrkeotsing: [`README.md`](../README.md), [`docs/arhitektuur.md`](arhitektuur.md), [`docs/superset.md`](superset.md).
