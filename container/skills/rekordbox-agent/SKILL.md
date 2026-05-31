---
name: rekordbox-agent
description: >-
  Levert DJ-playlists uit de gebruiker's rekordbox-library en stuurt ze als
  bestand (.m3u8 / .xml) terug via het huidige kanaal (bv. Telegram). Gebruik
  deze skill ALTIJD wanneer de gebruiker vraagt om een DJ-set, een crate, een
  rekordbox-playlist, "stuur me de trance/house/hardhouse set", een
  artiest-geïnspireerde set (Gigola, KI/KI, Tjade), of vraagt "welke sets heb
  je" / "activeer de rekordbox agent". Ook bij losse termen als "rekordbox",
  "dj set", "crate", "playlist sturen".
---

# Rekordbox agent

Je serveert kant-en-klare DJ-playlists uit de library van de gebruiker en stuurt ze als bijlage terug via het kanaal waarop het verzoek binnenkwam (Telegram).

## Waar alles staat

Alles staat in de groepsmap, gemount op **`/workspace/agent/rekordbox/`**:

- `manifest.md` — overzicht van alle beschikbare playlists (naam, #tracks, ~duur, vibe, bestandsnamen). **Lees dit eerst.**
- `playlists/` — per set een `.m3u8` (snel importeren) en een `.xml` (rekordbox-native, behoudt cues + beatgrids).
- `library.db` — vooraf-gecategoriseerde index van de hele collectie. `collection.xml` — de bron-export.

## Een playlist sturen (de hoofdtaak)

1. Lees `/workspace/agent/rekordbox/manifest.md` en kies de playlist die past bij het verzoek (genre/vibe/artiest/lengte). Bij twijfel of "welke heb je?": som kort de opties uit het manifest op en vraag welke.
2. Stuur het bestand met de **`send_file`** MCP-tool. Standaard gaat dat naar het huidige gesprek (de DM van de gebruiker) — je hoeft geen bestemming op te geven.
   - Stuur de **`.m3u8`** als primaire bijlage, met een kort tekstje (naam + #tracks + ~duur + vibe).
   - Bied aan om ook de **`.xml`** te sturen (of stuur 'm meteen mee) — die behoudt cues en beatgrids bij import.
   - Voorbeeld: `send_file` met `path: "rekordbox/playlists/Trance-crate.m3u8"` (paden zijn relatief t.o.v. `/workspace/agent/`).
3. Geef één regel import-tip: *.m3u8 = op Playlists slepen; .xml = Voorkeuren → Geavanceerd → Database → rekordbox xml, dan de playlist naar je eigen Playlists slepen (behoudt cues/beatgrids).* De paden wijzen naar `/Volumes/JURRE MUSIC`.

## Een nieuwe set op maat bouwen

Als de gebruiker iets vraagt dat niet in het manifest staat (andere lengte, andere mix, specifieke BPM/energie), kun je 'm bouwen met de **dj-set-builder** skill (`/app/skills/dj-set-builder/`):

- Dat vereist **python3** in de container. Test eerst: `python3 --version`.
- **Lukt dat:** bouw met de index — `python3 /app/skills/dj-set-builder/scripts/library.py query --db /workspace/agent/rekordbox/library.db ...` om kandidaten te kiezen, orden volgens de dj-set-builder skill, en exporteer met `python3 /app/skills/dj-set-builder/scripts/export_rekordbox.py --db /workspace/agent/rekordbox/library.db --ids <ids> --name "<naam>" --out /workspace/agent/rekordbox/playlists/<naam>`. Stuur daarna de nieuwe `.m3u8` met `send_file`.
- **Lukt dat niet** (geen python3 — standaard het geval): zeg dat eerlijk, stuur de dichtstbijzijnde kant-en-klare playlist uit het manifest, en meld dat on-demand bouwen pas kan als python3 aan het container-image is toegevoegd (een rebuild). Verzin geen set met de hand.

## Vuistregels

- Verstuur altijd via `send_file` (niet de inhoud in een chatbericht plakken — het moet een bijlage zijn).
- Houd het bericht kort: naam, #tracks, ~duur, vibe, en één import-regel.
- Energie/volgorde in deze sets zijn een voorstel op basis van rekordbox-metadata — de DJ heeft het laatste woord.
- Match niet té streng: "een hardere set" → Hardhouse crate of Tjade; "iets rustigs" → House crate; "trance" → Trance crate of KI/KI.
