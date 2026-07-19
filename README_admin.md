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

Fotografens katalog kan innehålla årskataloger, turneringskataloger och underkataloger. `Klubbar` behandlas som en egen toppgren. `Evenemang` och `Diverse` ligger under respektive år, till exempel `2026/Evenemang`.

## Uppdatera bilddata

Kör:

```bash
python update.py
```

`update.py` läser `photographers.json`, hämtar katalog- och filinformation från fotografernas Google Drives och skriver:

- `bildportalen.sqlite`
- `photos.json`
- `2026.log`

Varje fotografs katalogstruktur lagras i databasen. photos.json uppdateras kirurgiskt enbart när Drive-ändringar hittas.

## Publicering

Efter uppdatering kontrolleras ändringarna lokalt och committas till GitHub. GitHub Pages använder filerna i detta repo, inklusive `index.html`, `photos.json` och `photographers.json`.
