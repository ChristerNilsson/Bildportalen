# Bildportalen - användare

En söksida för bilder tagna av olika fotografer.

## Söka 

Skriv i sökfältet för att söka på katalognamn och bildfilnamn.

Du kan söka på ett eller flera ord: 

```anna cramling```

Träffar som innehåller alla orden visas först. Därefter visas träffar på första ordet och så vidare.

Om sökfältet är tomt visas alla bilder i den aktuella katalogen.  
Du kan binda ihop ord. anna_cramling  
Bilder läses in efter hand när du scrollar.  

## Kataloger

Katalogknapparna visar katalogerna på aktuell nivå. Siffran inom parentes visar hur många bilder som finns i katalogen. Klicka på en katalog för att gå ner i den. Använd `Upp` för att gå tillbaka till föräldrakatalogen.

Sökfältet visas högst upp. Aktuell sökväg visas under sökfältet, med antal matchande bilder direkt till höger, till exempel `2026 • Turnering (123)`. På toppnivån visas `Bildportalen`. Antalet räknas om när du skriver i sökfältet.

Sökning och bildlistan gäller inom den aktuella katalogen.

Koder som `T18469` eller `C1209676` visas inte i katalog- eller bildtext. När aktuell katalog innehåller en sådan kod visas länken `Turnering` på egen rad ovanför katalogknapparna. 
PDF-, URL- och TXT-filer i aktuell katalog visas också som länkar, med filnamnet som länktext. 
Bildtexten visar katalognamn, fotograf och knäpptidpunkt, till exempel `LOAH @ 2022-07-10 15:58:00`.

## URL

Sökning och aktuell katalog sparas i URL:en. Det betyder att du kan kopiera länken och skicka samma vy till någon annan.

Exempel:

```https://christernilsson.github.io/Bildportalen?q=anna cramling&folder=2026/2026-05-20 Stockholmsmästerskap 60plus snabb```

## Visa stor bild

Klicka på en bild för att visa den i Googles visningsprogram. Där kan du zooma, panorera, hämta och använda Drive-menyn.



# Bildportalen - fotograf

Den här filen är för dig som bidrar med bilder till Bildportalen

## Google Drive 

Lägg bilderna i en Google Drive-katalog som du delar med alla (enbart läsning). Administratören behöver länken till din bildkatalog.

Skicka detta till administratören:

- ditt namn
- önskad kort nyckel, till exempel `LOAH`
- Google Drive-länken till din bildkatalog

Exempel på kataloglänk:

```text
https://drive.google.com/drive/folders/1jAaO5eTMgH7jYr1O7stv1dlxO4ylbICX?usp=sharing
```

.pdf, .txt och .url kan läggas i turneringskataloger eller direkt i rotkatalogen. De kommer att visas som länkar när katalogen är aktuell.

Turneringsresultat kan även visas med T12345 eller C1234567.
* T : member.schack.se
* C : chess-results.com

Exempel: `2022-04-12_Tyresö SK 50år, Jubileumsturnering 2022_C1209676`

## Kataloger

Följande katalognamn används på de högsta nivåerna:

```text
2026
2025
osv
0000 Klubbar
	Seniorschack Stockholm
	Farsta SK
	osv
0000 Evenemang
	2026
	2025
	osv
0000 Diverse
	2026
	2025
	osv
```

Under året, skapa en katalog per turnering eller händelse. Ta med datum och tydligt namn:

```text
2026-03-14 Skol-SM Stockholm_T12345
```

Bra katalognamn gör bilderna lättare att hitta.

## Bildfilnamn

Använd beskrivande filnamn. Bra filnamn kan innehålla:

- turnering eller klass
- namn på spelare, lag eller situation
- datum
- löpnummer om det finns många bilder

Exempel:

```text
Klass_A_Edvin_Trost_2026-03-14_01.jpg
Lagbild_Wasa_SK_2026-03-14.jpg
Prisutdelning_Klass_B_2026-03-14_03.jpg
```

Undvik namn som bara är kamerans standardnamn, till exempel:

```text
IMG_1234.JPG
```

## Mellanslag och underscore

Använd mellanslag eller bindestreck för vanliga ord i katalog- och turneringsnamn:

```text
2026-03-14 Skol-SM Stockholm
```

Använd underscore när flera ord ska höra ihop vid sökning. Det är särskilt användbart för förnamn och efternamn:

```text
Bo_Ek
Edvin_Trost
Wasa_SK
```

Om filnamnet innehåller `Bo_Ek` kan man söka på exakt `Bo_Ek` och undvika falska träffar där `Bo` och `Ek` råkar finnas på olika ställen, till exempel `Bo Björk`.

En bra tumregel:

- mellanslag skiljer ord som får sökas var för sig
- underscore binder ihop ord som bör sökas som ett begrepp

## Byta namn

Du kan byta namn på kataloger och bildfiler i Google Drive. Bildportalen använder Google Drive-filens id för att öppna bilden.

Undvik däremot att radera en bild och ladda upp den igen om den redan finns i Bildportalen. Då får den ett nytt id.

## Delning

Kontrollera att administratören har åtkomst till katalogen. Om bilderna inte kan läsas kommer de inte med i nästa uppdatering.




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
