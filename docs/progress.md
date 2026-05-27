# Edenemisraport

> **Juhend:** See fail on projektitöö teise nädala väljund. Uuenda lühidalt iga esitamise eel. Kustuta see juhendrida.

## Mis on valmis

- [ ] Docker Compose käivitab PostgreSQL-i, töövoo konteineri, scheduleri ja Superseti näidikulaua.
- [ ] ERR API-dest saab kätte videokataloogi andmed ning kategoorialehtede esiletõstmise info.
- [ ] Sisu päritolumaad ja tüübid on eraldi staatilises `staging.content_metadata` tabelis, mis laetakse metaandmete CSV-failist.
- [ ] Andmed liiguvad `staging` kihist `mart` kihti
- [ ] Näidikulaud võimaldab võrrelda kataloogi struktuuri ja esiletõstetud sisu struktuure päritolumaade järgi 100% virnlintdiagrammide abil.
- [ ] Näidikulaud võimaldab võrrelda kataloogi struktuuri ja esiletõstetud sisu struktuure sisutüübi järgi 100% virnlintdiagrammide abil.
- [ ] Näidikulaual on Eesiletõstmine ja vaadatavus (sama päev).
- [ ] Scheduler käivitab töövoo vaikimisi igal hommikul kell 06:00, et uued päevaandmed sisse tõmmata ja transformeerida

[Täpsusta lühidalt, mis täpselt valmis on]

## Järgmised sammud

- [Esimene tegevus, mis ees ootab]
- [Teine tegevus]
- [Kolmas tegevus]

## Mis takistab

- [Probleem 1 — näiteks: API tagastab vigaseid väärtusi ühes linnas]
- [Probleem 2 — või: "Praegu pole blokeerivaid probleeme"]

## Kontrollpunkt

Käsk, millega saab kontrollida, et töövoog töötab:

```bash
# [Lisa siia käsk, mis näitab, et andmed liiguvad allikast näidikulauani]
# Näiteks:
docker compose exec pipeline python scripts/run_pipeline.py check
```

Oodatav tulemus: [Kirjelda, mida töötav süsteem väljastab]
