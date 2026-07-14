# TODO

[Try it!](https://christernilsson.github.io/Bildportalen/)

## HIGH 

### PYTHON Automatisk exekvering av update.py

Denna sker med hjälp av Win11 Task Scheduler.  
Den är inställd på uppdatering varje timme 00:17, 01:17 osv.  
Resultatet loggas i yyyy.log. T ex 2026.log.  

Github Actions testades först, men den visade sig inte vara tillförlitlig.
Ex: Jag ville köra update en gång per timme. Det blev var tredje timme. Detta för en enkel loggning.

## LOW ###################

### PYTHON Logga filer som saknar datum i namnet tillsammans med fotografens nyckel.

### PYTHON Effektivisering

* [ ] update.py kan fråga efter flera fotografer samtidigt.


## DONE 

### GUI Katalogknappar

* Typ 2026, turneringskataloger samt grupper.
* Visa antalet träffar i katalogerna med ().
* `Upp` för att komma tillbaka.

### PYTHON och GUI Länk till Inbjudan och Fakta
* I12345, F12345, T12345 och C1234567 tas bort
* Ersätts med följande alternativ
	* inbjudan.pdf
	* fakta.txt
	* övrigt.url
		* Kan peka på godtycklig webbsida

### GUI Knappar
* [x] Share kan skippas. Urlen ska vara up to date. Dvs vald katalog och söksträng
* [x] Download skippas. Enstaka bilder sköts av enbildsvisningen.
* [x] Clear Bort
* [x] Case bort
* [x] All bort
* [x] Help bort
* [x] "found 66424 images in 52 ms" bort
* [x] AB:7 A:2 bort

### GUI Selektion med kryssrutor och bildspel
* [x] Tas bort - verkar inte användas.


## SKA EJ GÖRAS

### Krockar mellan fotografer

* De ska hålla sig till exakt samma namn för turneringskatalogen
* De ska ha olika bildfilnamn annars tappar man en bild
* Då blir merge korrekt och båda bilderna kommer med i samma katalog

