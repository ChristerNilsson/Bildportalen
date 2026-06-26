# Bildportalen: fotograf

Den här filen beskriver vad en fotograf behöver veta för att bidra med bilder till Bildportalen.

## Google Drive

Skapa en Google Drive-katalog för dina bilder och dela länken med administratören. Administratören lägger in länken i `photographers.json`.

Katalogen kan innehålla år, turneringar och underkataloger. Exempel:

```text
2026/
  2026-01-10 Tjejträffen Stockholm I10765 T17724/
    Diverse/
      Vy-Tjejträffen_Agnes_Näslund_Ekroth_2026-01-10.jpg
```

## Turneringsnamn

Skriv gärna datum först i turneringskatalogens namn:

```text
2026-01-10 Tjejträffen Stockholm I10765 T17724
```

Koder kan läggas sist i katalognamnet:

- `T12345` länkar till Medlemssystemet.
- `C1234567` länkar till Chess-Results.
- `V123456789` länkar till Vimeo.
- `I12345`, `F12345` och `R12345` visas inte som text.

## Filnamn

Använd beskrivande filnamn. Datum i filnamnet är bra, särskilt om EXIF-tid saknas.

```text
Vy-Tjejträffen_Agnes_Näslund_Ekroth_2026-01-10.jpg
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

Dessa visas som länkar i Bildportalen när användaren står i samma katalog.

