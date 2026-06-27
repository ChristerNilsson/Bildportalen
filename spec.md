UTF-8 gäller i alla textfiler.

Detta projekt består av:

1. Ett pythonprogram, update.py, som sammanställer photos.json för ett antal fotografer

2. Ett webprogram, index.html, som tillåter sökning och visning mha photos.json

# update.py

Struktur:
```
2026
	Evenemang
	Diverse
2025
	Evenemang
	Diverse
2024
	Evenemang
	Diverse
...
Klubbar
Help.pdf
```

Filer på toppnivån ska hanteras så här i photos.json:
```"Help.pdf": "64-kodning"```

Se till att Help.pdf kommer med i photos.json. Den ska ligga på toppnivå och hanteras av photographers.json

Inga manifest.json ska skapas.

Pythonprogrammet ska hämta tillkomna/ändrade katalognamn och filnamn i fotografernas kataloger.

Dessutom ska pythonprogrammet ta med .pdf och .txt i den resulterande json-filen
        "inbjudan.pdf": "1PDqhYAQJhzBgbhCZ8fEfiKaPTA_g_IRq"
        "fakta.txt": "1PDqhYAQJhzBgbhCZ8fEfiKaPTA_g_IRq"

.url-filer hanteras så här:
	1. Läs in url-filens andra rad (länken)
	2. "resultat": "https://..."

Dessa filer ska visas som länkar när katalogen dessa ligger i är aktuell katalog. Länktexten i ovanstående fall blir "inbjudan".  
Alla länkar ska skapas i samma flik som aktuell nuvarande.

Fotografernas kataloger ligger på olika Google Drives.

photos.json ska innehålla ett katalogträd där löven utgörs av länkar till bilder.

photographers.json innehåller registrerade fotografer samt url till deras bilder.

För att få bättre prestanda, ska varje fotograf ska sparas i en egen json-fil. T ex CN.json.

Denna json-fil ska sparas i katalogen photographers

Fotografens .json ska bara återskapas om något ändrats på fotografens Google Drive

Logga till update.log. Ska även innehålla tidpunkter. Logga varje json-fil som skapas.
Före "Startar uppdatering" ska en blank rad skrivas ut.

Vill se lite indenteringar i logfilen:
```
2026-06-20T18:06:00 Startar uppdatering.
2026-06-20T18:06:00  OAuth används för Drive API och ändringskontroll.
2026-06-20T18:06:00  Hämtar CN21.
2026-06-20T18:06:00   Inga Drive-ändringar för CN. CN.json lämnas oförändrad.
2026-06-20T18:06:00  Hämtar LOAH.
2026-06-20T18:06:01   Inga Drive-ändringar för LOAH. LOAH.json lämnas oförändrad.
2026-06-20T18:06:01  Skapade photos.json med 2311 bilder.
2026-06-20T18:06:01 Uppdatering klar.
```
# photographers.json

Denna fil uppdateras manuellt.

{
	"CN": ["Christer Nilsson", "https://drive.google.com/drive/folders/1IQSQUGml83eFJQAxqi_ymg1UXhtqSv4K?usp=sharing"]
}

https://drive.google.com/drive/folders/1IQSQUGml83eFJQAxqi_ymg1UXhtqSv4K?usp=sharing pekar på denna dators drive-katalog där bilderna ligger.

# photos.json:

Denna fil underhålls av update.py

{ 
	"2025": {
		"2025-09-21 Knatte-Lag-DM Stockholm_I10748_T16960": {
			"Knattelag-DM_01.Wasa_SK_2025-09-21.jpg":                        ["1u_AMCbDDgpBuUKPFiR-lB0IYuEJbrWzS","LOAH", 1234567891],
			"Knattelag-DM_01.Wasa_SK_med_samtliga_lagtränare_2025-09-21.jpg":["1u_AMCbDDgpBuUKPFiR-lB0IYuEJbrWzT","LOAH", 1234567892],
			"Knattelag-DM_03_Wasa_SK_II_2025-09-21.jpg":                     ["1u_AMCbDDgpBuUKPFiR-lB0IYuEJbrWzU","CN21", 1234567893]
			}
		}	
}

Förklaring:

* 1u_AMCbDDgpBuUKPFiR-lB0IYuEJbrWzS = Bildfilens nyckel
* LOAH = Fotografens nyckel
* 1234567891 = sekunder sedan 1900-01-01 00:00:00. Dvs EXIF-tiden för bildens tagande.
Knäpptiden är felaktig. Enligt den har alla bilder tagits senaste dygnet.

# index.html

## prefix

Gå igenom träffarna innan ett sökresultat presenteras. 
Identifiera största gemensamma prefix och se till att det inte visas

Exempel: 
```
Vy_Pelle_Adam
Vy_Pelle_Bertil
```
ska resultera i att bara följande visas.
```
Adam
Bertil
```

Motsvarande gäller för den path som visas baserad på katalogdelen av kortets text.

Målet är att undertrycka störande upprepning av information.

## gemensamt datum i filnamn

Undertryck även gemensamt datum i filnamnens slut och text före detta datum.
Exempel:
```
Adam_Öppen klass_2026-06-26-X.jpg
Bertil_Öppen klass_2026-06-26.jpg
```
ska resultera i 
```
Adam-X
Bertil
```

`â€¢` visas felaktigt i pathen på varje kort.

När jag står på pathen `2026 • 2026-05-20 Stockholmsmästerskap 60+ snabb, • Diverse` visas Diverse på varje kort. Detta är onödigt.

## scrollande panel införs

Panelen med sökrutan och alla knappar måste gå att scrolla bort. Den ska inte vara oberoende av bilderna.

Fliknamnet ska vara Bildportalen.

Lägg in en `Try it!` länk i readme.md

Starta inte någon web server, jag använder Go Live!

## Input 

* photographers.json
* photos.json

## Visning

Länkarna ska ligga ovanför knapparna.

Wrappa .txt och .pdf med `https://drive.google.com/file/d/DRIVELINK/preview`.
Ungefär som .jpg wrappas.

Filer av typen .url ska visas i webläsaren.  

Då man står på toppnivån ska Bildportalen visas

Sökrutan ska stå högst upp på sidan.

Öka minimum-bredden till 270px.

Visa namnet på aktuell path eller Bildportalen. Direkt till höger om denna ska antalet bilder visas som (123).
Detta antal ska räknas om med varje tangenttryckning i sökrutan
Antalet bilder till höger om sökrutan ska bort.
Visa inte katalogknappar med (0) bilder.  
Om det finns underkataloger till en turnering ska dessa räknas rekursivt.  

Bara de bilder som syns i fönstret ska hämtas. När man scrollar ska fler bilder hämtas.

Håll reda på aktuell katalog. Från start visas alla kataloger, i fallande ordning.
Alla kataloger på aktuell nivå som visas som knappar.
Visa så många knappar som möjligt i bredd. Just nu verkar bara 60% av bredden utnyttjas.
Kommatecken i knapptext ska undertryckas.

När man klickar på en katalog blir den katalogen aktuell katalog.
Man ska kunna gå upp till föräldrakatalogen med knappen `Upp`.

Varje katalog ska visa hur många träffar som finns i den. Detta ska stå inom parentes i knappen.

Man ska kunna se alla bilder i aktuell katalog, även på toppnivån.

Bilderna ska alltid visas i fallande tidsordning (EXIF-timestamp då bilden togs)

I katalognamn och filnamn ska följande tecken bytas ut (enbart vid visning):

|Från|Till|
|-|-|
|_|mellanslag|
|Vy-||
|.jpg||
|60plus|60+|
| 16x9 |mellanslag|

Avgränsarna / samt | ska ersättas med •

Bildtexten ska även visa EXIF-timestamp på formatet YYYY-MM-DD HH:MM:SS

När fotografens key visas ska suffixet tas bort. Detta gäller enbart visning på Card.
T ex LOAH_26 => LOAH, LOAH_0E => LOAH

Exempel på den undre bildtexten:
```
2022-07-02 Schack-SM Uppsala • Sverigemästarklassen, 2022
LOAH @ 2022-07-10 15:58
```
Fotograf och timestamp ligger på en egen rad.
Fotografen kan ha olika key.

## Sökning

Då man ändrar i queryfältet ska urlen uppdateras. Den ska även läsa in det som står där initialt.
Aktuell folder ska visas i urlen.

Programmet ska ha sökmöjligheter på katalognamn och bildfilsnamn.  
Färskaste bilden ska visas först.  

Sökning ska kunna ske på flera termer. Om två termer, A och B, används ska resultaten visas i ordningen AB, A, B.

## Helskärmsläge

Då man klickar på en bild ska den direkt gå till Googles visningsprogram.
Typ: https://drive.google.com/drive/home?dmr=1&ec=wgc-drive-%5Bmodule%5D-goto
Finns ingen anledning att klicka två gånger.

# Skapa README_admin.md

* Denna förklarar hur producers läggs upp, dvs fotografer.
```
  "LOAH":["Lars OA Hedlund","https://drive.google.com/drive/folders/1jAaO5eTMgH7jYr1O7stv1dlxO4ylbICX?usp=sharing"]
```
* Var man hittar filen, hur den hamnar på github.

# Skapa README_producer.md

* Denna förklarar vad en fotograf behöver veta.
* Introduktion till Google Drive.
* Vad man skickar till admin.
* Hur man skapar kataloger och bildfiler.
* T ex vad som ska stå i ett turneringsnamn och i ett bildfilsnamn.
* Förklara skillnaden mellan att använda underscore och mellanslag.
	* underscore används oftast för att binda ihop förnamn och efternamn. T ex Bo_Ek
		* Då kan man söka på Bo_Ek och slipper falska träffar som Bo Björk

# Skapa README_consumer.md

* Denna förklarar vad en användare behöver veta.
* Hur man söker
* Hur man kan använda urlen.
* Hur man zoom och panorerar.
* Hur man hämtar ner en bild
