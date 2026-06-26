# Bildportalen: admin

Den här filen beskriver hur fotografer, även kallade producers, läggs in i Bildportalen.

## Registrera fotograf

Fotografer registreras manuellt i `photographers.json`.

Format:

```json
{
  "LOAH": ["Lars OA Hedlund", "https://drive.google.com/drive/folders/1jAaO5eTMgH7jYr1O7stv1dlxO4ylbICX?usp=sharing"]
}
```

Nyckeln, till exempel `LOAH`, används i `photos.json` och visas på bildkorten. Om samma fotograf har flera Drive-kataloger kan nyckeln ha suffix, till exempel `LOAH_26`. Suffixet döljs i den publika visningen.

## Drive-katalog

URL:en ska peka på fotografens Google Drive-katalog med bilderna. Katalogen måste vara åtkomlig för uppdateringsprogrammet.

Fotografens katalog kan innehålla årskataloger, turneringskataloger och underkataloger. Toppnivåkatalogerna `0000 Klubbar`, `0000 Evenemang` och `0000 Diverse` behandlas som egna huvudgrenar.

## Uppdatera bilddata

Kör:

```bash
python update.py
```

`update.py` läser `photographers.json`, hämtar katalog- och filinformation från fotografernas Google Drives och skriver:

- `photos.json`
- `photographers/<fotografnyckel>.json`
- `update.log`

Varje fotograf får en egen json-fil i `photographers/`. Filen återskapas bara när Drive-ändringar hittas, om OAuth och ändringskontroll är aktiverat.

## Publicering

Efter uppdatering kontrolleras ändringarna lokalt och commitas till GitHub. GitHub Pages använder filerna i detta repo, inklusive `index.html`, `photos.json` och `photographers.json`.

