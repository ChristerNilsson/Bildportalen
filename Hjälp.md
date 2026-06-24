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
