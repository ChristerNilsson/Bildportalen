# Bildportalen - admin

Den här filen är för den som administrerar Bildbanken och lägger till producenter, dvs fotografer.

## Lägg till fotograf

Fotografer registreras manuellt i `photographers.json`.

Formatet är: 

```json
{
  "LOAH": [
    "Lars OA Hedlund",
    "https://drive.google.com/drive/folders/1jAaO5eTMgH7jYr1O7stv1dlxO4ylbICX?usp=sharing"
  ]
}
```

Nyckeln, till exempel `LOAH`, används i `photos.json` för att visa vem som äger bilden. Välj en kort och stabil nyckel som inte behöver bytas senare.

URL:en ska vara en Google Drive-länk till fotografens rotkatalog. Fotografen behöver dela katalogen så att den kan läsas av kontot som kör `update.py`.

## Uppdatering

Kör:

```powershell
python update.py
```

Programmet läser `photographers.json`, hämtar katalogträden från Google Drive och uppdaterar:

- `photos.json`
- `photographers/<KEY>.json`
- `photographers/<KEY>.changes.json`
- `update.log`

`credentials.json` och `token.json` används lokalt för Google OAuth och ska inte committas. OAuth behöver skrivskyddad Drive-behörighet för att kunna läsa innehållet i `.url`-filer. Om en äldre token bara har metadata-behörighet begär `update.py` ett nytt godkännande och ersätter `token.json`.

## GitHub

Efter en lyckad uppdatering committas datafilerna:

```powershell
git add photos.json photographers/*.json photographers/*.changes.json update.log
git commit -m "Update photo index"
git push
```

Om GitHub Actions används ska motsvarande Google-credentials ligga som GitHub Secrets. Lägg inte hemligheter i repot.

## Krockar

Kataloger med samma namn mergeas. Om två fotografer har `2026` hamnar bådas innehåll under samma `2026`.

Exakt samma sökväg och filnamn kan däremot krocka, till exempel:

```text
2026/SM/bild.jpg
```

Om två fotografer har samma sökväg kan den senare skriva över den tidigare i `photos.json`. Be fotograferna använda tydliga turneringskataloger och filnamn.

## Viktigt

Google Drive-filens id är det stabila. Fotografen kan byta katalognamn och filnamn utan att bilden slutar fungera, så länge filen inte raderas och laddas upp igen.

## Länkar

* T: member.schack.se
* C: chess-results
* pdf-filer: Lägges i lämplig turneringskatalog
