# Bildportalen: fotograf

Den här filen beskriver vad en fotograf behöver veta för att bidra med bilder till Bildportalen.

## Google Drive

Skapa en Google Drive-katalog för dina bilder och dela länken med administratören. Administratören lägger in länken i `photographers.json`.  
Se till att Utforskaren visar den som t ex `Google Drive (G:)`

Katalogen kan innehålla år, turneringar och underkataloger. Exempel:

```text
2026
  2026-01-10 Tjejträffen Stockholm
    Diverse
      Agnes_Näslund_Ekroth.jpg
```

## Turneringsnamn

Skriv alltid datum först i turneringskatalogens namn:

```text
2026-01-10 Tjejträffen Stockholm
```

## Filnamn

Använd beskrivande filnamn.

```text
Agnes_Näslund_Ekroth.jpg
```

Underscore används ofta för att binda ihop namn eller uttryck. Exempel: `Bo_Ek` gör att man kan söka på exakt `Bo_Ek` och slipper träffar som `Bo Björk`.

Mellanslag passar bättre i vanliga katalogrubriker och turneringsnamn.

## Extra länkar

Du kan lägga in dokument eller länkar i en katalog:

- `inbjudan.pdf`
- `fakta.txt`
- `resultat.url`

En `.url`-fil ska ha länken på andra raden, till exempel:

```text
[InternetShortcut]
URL=https://example.com/resultat
```
Enklaste sättet att skapa en .url-fil är att dra in urlen från webläsaren till rätt katalogen i Utforskaren.
Glöm inte byta namn på .url-filen. T ex Resultat, Inbjudan, Fakta eller annat lämpligt.

Dessa visas som länkar i Bildportalen när användaren står i samma katalog.
