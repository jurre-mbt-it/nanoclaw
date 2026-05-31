---
name: dj-set-builder
description: >
  Bouwt en ordent DJ-sets uit een rekordbox-collectie voor trance, hard house en house.
  Bepaalt de optimale trackvolgorde op basis van harmonisch mixen (Camelot wheel),
  BPM-progressie en een energiecurve over de set. Werkt standaard op rekordbox-metadata
  (BPM en key zitten al in de export) en gebruikt optioneel audioanalyse (librosa) voor
  energie en spectrale kenmerken, plus optioneel inspiratie uit pro-sets (1001tracklists),
  afhankelijk van wat de omgeving toelaat.
  Levert de set zowel als leesbare tracklist als in formaten die direct terug in
  rekordbox te importeren zijn (rekordbox-XML met behoud van volgorde, beatgrids en
  cues, plus een M3U8), via een meegeleverd exportscript.
  Gebruik deze skill wanneer de gebruiker vraagt om een set te bouwen, een tracklist te
  ordenen, nummers in de juiste volgorde te zetten, harmonisch te mixen, een set wil
  exporteren of importeren in rekordbox, of een rekordbox XML/collection wil omzetten
  naar een speelbare set.
---

# DJ Set Builder

Je bouwt een speelklare DJ-set uit een rekordbox-collectie. Het doel is een tracklist met een logische volgorde die harmonisch klopt, een soepele BPM-lijn heeft en een energiecurve volgt die past bij het type set. Je werkt voor trance, hard house en house.

De set is pas écht af als de DJ 'm kan draaien: lever naast de leesbare tracklist altijd ook importeerbare bestanden voor rekordbox (zie [sectie 9](#9-exporteer-naar-rekordbox-importeerbare-set)), zodat de gekozen volgorde één-op-één in rekordbox landt. Track-identificatie loopt via `TrackID` uit de export — houd die bij elke track vast, want het exportscript heeft 'm nodig.

## 0. Bepaal eerst je capability-niveau

Test bij de start zelf wat je kunt en meld kort in welk niveau je draait. Degradeer netjes: ontbreekt een capability, ga dan door op het lagere niveau in plaats van te stoppen.

- **Niveau 1 (altijd beschikbaar): metadata-only.**
  Lees de rekordbox XML en werk volledig op de aanwezige velden (BPM, key, genre, rating, comments, kleur, duur). Dit is genoeg voor een goede set.
- **Niveau 2 (als je code kunt uitvoeren): + audioanalyse.**
  Probeer `import librosa`. Lukt dat en wijzen de `Location`-paden naar bestaande audiobestanden, dan kun je energie en spectrale helderheid berekenen waar metadata ontbreekt of twijfelachtig is. Test dit met een klein script voordat je erop bouwt.
- **Niveau 3 (als je internettoegang hebt): + pro-set inspiratie.**
  Probeer een test-fetch. Lukt dat, dan mag je 1001tracklists of vergelijkbare sites raadplegen om te zien welke tracks of overgangen pro's na elkaar zetten. Gebruik dit als inspiratie, niet als harde regel.

Zeg aan het begin bijvoorbeeld: "Ik draai op niveau 2 (metadata + audioanalyse), geen internet beschikbaar."

## 1. Lees de rekordbox-export in

De rekordbox XML heeft als root `DJ_PLAYLISTS` met daarin `COLLECTION` en `PLAYLISTS`. Elke `TRACK` in `COLLECTION` heeft o.a. deze attributen die je nodig hebt:

- `Name`, `Artist` (identificatie)
- `AverageBpm` (BPM, al door rekordbox geanalyseerd)
- `Tonality` (toonsoort, bv. `Am`, `F#m`, `C`)
- `Genre`
- `Rating` (0/51/102/153/204/255 = 0 t/m 5 sterren)
- `Comments` (DJ's zetten hier vaak een energie-label of "energy 7" in)
- `Colour` of MyTag (kleurlabel, soms gebruikt voor energie/intro/peak)
- `TotalTime` (lengte in seconden)
- `Location` (bestandspad, nodig voor niveau 2)

### Drie manieren waarop de trackpool wordt bepaald

Bepaal eerst welke van deze inputs van toepassing is — de rest van de skill (verrijken, ordenen, exporteren) is daarna identiek.

1. **Bestaande playlist.** De gebruiker noemt een playlist → filter op de `PLAYLISTS`-node (let op exacte naam, soms met spaties op het eind) i.p.v. de hele collectie.
2. **Zelf samenstellen uit de collectie.** De gebruiker vraagt een set zonder playlist te noemen ("maak een trance set van ~90 min", "een peak-time hard house uurtje"). Dan stel je de pool zelf samen uit de hele `COLLECTION`: filter op het gevraagde genre/BPM-bereik en kies een **coherente subset** die past bij de gevraagde lengte/duur (zie pool-hygiëne hieronder). Forceer niet de hele collectie in één set.
3. **Aangeleverd lijstje nummers.** De gebruiker plakt of noemt een rij tracks ("zet deze in volgorde: …"). Match elke regel tegen de `COLLECTION` op genormaliseerde naam (kleine letters, alleen alfanumeriek; match op de track-`Name`, bevestig met de artiest waar mogelijk) om `BPM`, `Tonality` en `TrackID` terug te vinden. **Meld expliciet welke tracks je niet kon matchen** — zonder metadata kun je ze niet harmonisch plaatsen. Vraag dan of de gebruiker BPM/toon zelf aanlevert, of laat ze weg.

### Pool-hygiëne (verplicht bij modus 2, nuttig bij de rest)

Een collectie zit vol dingen die geen setmateriaal zijn. Sluit uit voordat je gaat ordenen, en meld kort wat je hebt weggelaten:

- **Sample-FX en one-shots:** `AverageBpm` ontbreekt of is `0`, of de `TotalTime` is heel kort (< ~90 s), of de `Location`/`Name` wijst op sample-materiaal (mappen als `Sampler`, `Loopmasters`, `Demo Tracks`; namen als `NOISE`, `SIREN`, `IMPACT KICK`).
- **Tracks zonder bruikbare key** als je harmonisch wilt mixen (geen `Tonality`) — gebruik ze alleen bewust.
- **Dubbele/edit-varianten** van hetzelfde nummer: kies er één.
- **Buiten het gevraagde genre/BPM-bereik** vallende tracks (bij modus 2).

Bij modus 2 mik je op een **coherente, niet te grote pool** en kies je daaruit het aantal tracks dat bij de gevraagde duur past (reken ~vol uitgespeeld; een echte set draait tracks korter, dus geef zowel het aantal als een geschatte mix-duur). Liever een strakke set van 15 sterke tracks dan 40 die half botsen.

## 2. Verrijk elke track

**Key naar Camelot.** Zet `Tonality` om naar een Camelot-code voor harmonisch mixen:

| Camelot | Mineur (A) | Majeur (B) |
|--------|------------|-----------|
| 1 | Abm / G#m | B |
| 2 | Ebm / D#m | F# / Gb |
| 3 | Bbm / A#m | Db / C# |
| 4 | Fm | Ab / G# |
| 5 | Cm | Eb / D# |
| 6 | Gm | Bb / A# |
| 7 | Dm | F |
| 8 | Am | C |
| 9 | Em | G |
| 10 | Bm | D |
| 11 | F#m / Gbm | A |
| 12 | Dbm / C#m | E |

(Als de gebruiker rekordbox op Camelot- of Open Key-weergave heeft staan, kan `Tonality` al een code zijn. Detecteer dat en sla de conversie over.)

**Energie bepalen** (schaal 1 tot 10), in volgorde van betrouwbaarheid:
1. Expliciet label in `Comments` of MyTag (bv. "energy 8") -> gebruik dat.
2. Kleurlabel als de gebruiker een vaste conventie heeft -> vraag of leid af.
3. Niveau 2: bereken uit audio (RMS-loudness + spectral centroid, zie script).
4. Anders heuristiek: schat op basis van BPM binnen het genre en de rating. Hogere BPM en hogere rating duwen de energie omhoog, maar dit is een grove schatting. Meld dat het een schatting is.

## 3. Ordeningslogica

Combineer drie krachten in een score per overgang van track A naar track B, en bouw de set greedy of via een korte padzoektocht (zie script).

**a) Harmonisch (Camelot).** Veilige moves vanaf een code (bv. 8A):
- Zelfde key (8A -> 8A): perfect, gelijke spanning.
- ±1 zelfde letter (8A -> 7A of 9A): vloeiend, klassieke move.
- Letter wisselen, zelfde nummer (8A -> 8B): relatieve majeur/mineur, stemmingswissel maar compatibel.
- +2 zelfde letter (8A -> 10A): energy boost, iets stijgender.
- +7 (modulatie) is een geavanceerde "lift", spaarzaam gebruiken op een hoogtepunt.
Alles daarbuiten geeft botsende tonen, vermijd dat tenzij er een harde cut of lange breakdown tussen zit.

**b) BPM-progressie.** Houd overgangen binnen ongeveer ±3 tot 4% (een paar BPM) voor een echte beatmix. Genre-banen als richtlijn:
- House: ~120 tot 128
- Trance: ~132 tot 140 (prog trance lager, uplifting rond 138)
- Hard house: ~145 tot 150
Laat de BPM over de set geleidelijk oplopen richting peak-time. Grote sprongen alleen bewust inzetten als "gear shift" tussen secties, niet midden in een flow.

**c) Energiecurve.** Kies een archetype op basis van het settype:
- **Warm-up / opening:** start laag (energie 3 tot 5), groovier, bouw rustig op.
- **Peak-time:** loop op naar 8 tot 10, grote anthems, vocals, breakdown -> build -> drop afwisselen zodat het ademt.
- **Closing:** of vasthouden op hoog, of bewust afbouwen.
Bepaal per positie in de set een doelenergie en beloon tracks die daar dichtbij zitten.

**Scoren:** combineer (bijvoorbeeld) 45% harmonisch, 30% BPM-nabijheid, 25% afstand tot de doelenergie op die positie. Begin met een passende opener (lage energie voor warm-up, of een herkenbare intro-track) en kies steeds de best scorende volgende track die nog niet gebruikt is.

## 4. (Niveau 2) Audioanalyse met librosa

Gebruik dit alleen voor energie/helderheid waar metadata tekortschiet. BPM en key uit rekordbox zijn meestal betrouwbaarder dan een snelle her-analyse, dus overschrijf die niet zonder reden.

```python
import librosa
import numpy as np

def analyse_audio(path, sr=22050, duration=120, offset=30):
    # Analyseer een representatief midden-fragment, niet de hele track.
    y, sr = librosa.load(path, sr=sr, mono=True, offset=offset, duration=duration)
    rms = float(np.mean(librosa.feature.rms(y=y)))
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    # Ruwe energie 1-10: combineer loudness en helderheid, daarna normaliseren
    # over de hele collectie (min-max) voordat je het als energie gebruikt.
    return {"rms": rms, "centroid": centroid}
```

Normaliseer `rms` en `centroid` over de hele collectie (min-max naar 1 tot 10) en middel ze tot een energiewaarde. Doe dit relatief binnen de set, niet absoluut.

## 5. (Niveau 3) Pro-set inspiratie

Als je internet hebt, mag je 1001tracklists of soortgelijke sites raadplegen om te kijken hoe ervaren DJ's tracks combineren. Gebruik dit als zachte hint: als twee tracks in jouw collectie vaak na elkaar in pro-sets opduiken, geef die overgang een kleine bonus. Laat het de harmonische en BPM-regels nooit overrulen.

## 6. Referentiescript (ordening op metadata)

```python
import xml.etree.ElementTree as ET
import re

CAMELOT = {
    "Abm":"1A","G#m":"1A","Ebm":"2A","D#m":"2A","Bbm":"3A","A#m":"3A",
    "Fm":"4A","Cm":"5A","Gm":"6A","Dm":"7A","Am":"8A","Em":"9A","Bm":"10A",
    "F#m":"11A","Gbm":"11A","Dbm":"12A","C#m":"12A",
    "B":"1B","F#":"2B","Gb":"2B","Db":"3B","C#":"3B","Ab":"4B","G#":"4B",
    "Eb":"5B","D#":"5B","Bb":"6B","A#":"6B","F":"7B","C":"8B","G":"9B",
    "D":"10B","A":"11B","E":"12B",
}

def to_camelot(tonality):
    if not tonality:
        return None
    t = tonality.strip()
    if re.fullmatch(r"\d{1,2}[AB]", t):   # al Camelot
        return t
    return CAMELOT.get(t)

def parse_camelot(c):
    m = re.match(r"(\d+)([AB])", c or "")
    return (int(m.group(1)), m.group(2)) if m else None

def harmonic_score(c1, c2):
    if not c1 or not c2:
        return 0.5
    if c1 == c2:
        return 1.0
    p1, p2 = parse_camelot(c1), parse_camelot(c2)
    if not p1 or not p2:
        return 0.5
    n1, l1 = p1; n2, l2 = p2
    diff = min((n1 - n2) % 12, (n2 - n1) % 12)
    if l1 == l2 and diff == 1: return 0.9    # vloeiend
    if l1 != l2 and n1 == n2:  return 0.85   # relatieve majeur/mineur
    if l1 == l2 and diff == 2: return 0.7    # energy boost
    if l1 == l2 and diff == 7: return 0.55   # modulatie (spaarzaam)
    return 0.2                                # botst

def bpm_score(b1, b2):
    if not b1 or not b2:
        return 0.5
    pct = abs(b1 - b2) / b1
    return max(0.0, 1.0 - pct / 0.06)         # 0 bij ~6% verschil

def target_energy(pos, total, shape="peak"):
    x = pos / max(1, total - 1)
    if shape == "warmup":   return 3 + 5 * x
    if shape == "closing":  return 9 - 4 * x
    return 4 + 6 * (1 - abs(0.5 - x) * 2)     # peak-time boog

def is_set_material(tr):
    # Pool-hygiëne: weer sample-FX / one-shots / te korte fragmenten.
    bpm = float(tr.get("AverageBpm") or 0)
    dur = float(tr.get("TotalTime") or 0)
    loc = (tr.get("Location") or "").lower().replace("%20", " ")  # paden zijn URL-encoded
    if bpm <= 0 or dur < 90:
        return False
    if any(s in loc for s in ("/sampler/", "loopmasters", "/demo tracks/")):
        return False
    return True

def load_tracks(xml_path, playlist=None, keep_ids=None, hygiene=True):
    # playlist=None + keep_ids=None -> hele collectie (modus 2).
    # keep_ids={...} -> alleen die TrackIDs (de afspeelvolgorde bepaalt order_set later).
    root = ET.parse(xml_path).getroot()
    tracks = []
    for tr in root.iter("TRACK"):
        if tr.get("Name") is None:
            continue
        if keep_ids is not None and tr.get("TrackID") not in keep_ids:
            continue
        if hygiene and keep_ids is None and not is_set_material(tr):
            continue
        tracks.append({
            "id": tr.get("TrackID"),
            "name": tr.get("Name"),
            "artist": tr.get("Artist"),
            "bpm": float(tr.get("AverageBpm") or 0) or None,
            "camelot": to_camelot(tr.get("Tonality")),
            "genre": tr.get("Genre"),
            "rating": int(tr.get("Rating") or 0) // 51,
            "energy": None,   # vul uit comments/MyTag/audio of heuristiek
        })
    return tracks

def order_set(tracks, shape="peak", w_harm=0.45, w_bpm=0.30, w_energy=0.25):
    remaining = tracks[:]
    # opener: laagste energie voor warm-up, anders middenmoot
    remaining.sort(key=lambda t: (t["energy"] or 5))
    ordered = [remaining.pop(0)]
    total = len(tracks)
    while remaining:
        prev = ordered[-1]
        tgt = target_energy(len(ordered), total, shape)
        def score(t):
            s = (w_harm * harmonic_score(prev["camelot"], t["camelot"])
                 + w_bpm * bpm_score(prev["bpm"], t["bpm"])
                 + w_energy * (1 - abs((t["energy"] or 5) - tgt) / 10))
            return s
        nxt = max(remaining, key=score)
        ordered.append(nxt)
        remaining.remove(nxt)
    return ordered
```

Het script is een startpunt. De wegingen (`w_harm`, `w_bpm`, `w_energy`) en de energieboog zijn bewust instelbaar, want de smaak van de DJ bepaalt uiteindelijk de mix.

## 7. Genre-specifiek (trance / hard house / house)

- **Trance:** key-compatibiliteit weegt extra zwaar, want vocals en lange melodische breakdowns botsen hard bij een verkeerde toon. Plan breakdown -> build -> drop als ademhaling: zet niet drie volle anthems op rij. Uplifting trance rond 138, prog lager.
- **Hard house:** hoge, vlakke energie. BPM-banen liggen dicht bij elkaar (145 tot 150), dus BPM-nabijheid is bijna altijd oke en harmonie + relentless drive worden bepalend. Houd de spanning hoog, maar plan een enkele dip zodat de piek erna landt.
- **House:** breder en groovier, vooral geschikt voor warm-up en closing. Meer ruimte voor stemmingswissels via relatieve majeur/mineur. Laat de BPM hier de geleidelijke opbouw naar de hardere secties dragen.

## 8. Outputformaat

Lever een genummerde tracklist met per track de kernkenmerken en een korte overgangsnotitie:

```
SET: <naam>  |  <aantal tracks>  |  <totale duur>  |  curve: peak-time

1. Artist - Title        128 BPM  8A  energy 4   [opener, intro long]
2. Artist - Title        128 BPM  8A  energy 5   -> zelfde key, +1 energie
3. Artist - Title        130 BPM  9A  energy 6   -> +1 Camelot, +2 BPM
...
```

Sluit af met een korte toelichting op de gekozen curve en eventuele twijfelpunten (bv. tracks waar de energie geschat is, of een overgang die scherp is maar bewust gekozen). Bied aan om de wegingen aan te passen of de set in te korten/verlengen.

## 9. Exporteer naar rekordbox (importeerbare set)

De DJ moet de set kunnen draaien, niet alleen lezen. Gebruik daarom altijd het meegeleverde script om de definitieve volgorde naar importeerbare bestanden te schrijven:

```bash
python3 scripts/export_rekordbox.py \
  --source <pad/naar/collection.xml> \
  --ids <TrackID1,TrackID2,...> \
  --name "<set-naam>" \
  --out <uitvoer/basisnaam-zonder-extensie>
```

Geef de `--ids` in **exact de afspeelvolgorde** die je hebt bepaald (komma-gescheiden TrackIDs uit de COLLECTION). Bij veel tracks is `--ids-file` handiger: een bestand met één TrackID per regel, of een JSON-array. Het script schrijft twee bestanden:

- **`<naam>.xml`** — een rekordbox-native `DJ_PLAYLISTS`-bestand. Elke track wordt **letterlijk** uit de bron gekopieerd, inclusief `Location` en de `TEMPO`/`POSITION_MARK`-kinderen, zodat **beatgrids en hot/memory cues bewaard blijven**. De volgorde staat in één `Type="1"`-playlist die per `TrackID` (`KeyType="0"`) verwijst. Dit is de betrouwbare route: rekordbox matcht op bestandslocatie aan de bestaande collectie.
- **`<naam>.m3u8`** — een platte lijst met absolute bestandspaden in volgorde. Simpeler te importeren, maar zónder cues/beatgrid en alleen bruikbaar als de audiobestanden op dezelfde paden staan.

Het script waarschuwt als een TrackID niet in de bron voorkomt (dan wordt die overgeslagen) — meld dat als het gebeurt.

**Vertel de gebruiker kort hoe te importeren** (rekordbox 6/7):

1. *rekordbox XML (aanrader, behoudt cues + beatgrids):* Voorkeuren → Geavanceerd → tab **Database** → onder **rekordbox xml** wijs je het `.xml`-bestand aan als "Geïmporteerde bibliotheek". Zet daarna in de zijbalk de **rekordbox xml**-boom aan (Voorkeuren → Weergave → Layout). De playlist verschijnt onder die boom; sleep 'm naar **Playlists** in je eigen collectie — volgorde blijft behouden.
2. *M3U8 (snel):* sleep het `.m3u8`-bestand direct op **Playlists** in rekordbox, of File → Import → Playlist.

Noem in je eindantwoord de paden van de twee bestanden en welke importmethode je aanraadt.

## Vuistregels

- BPM en key uit rekordbox zijn leidend; her-analyseer alleen als ze duidelijk fout staan.
- Forceer geen volledige set uit een te kleine of incoherente pool. Meld het als er te weinig harmonisch passende tracks zijn.
- Een scherpe, niet-harmonische overgang mag, maar alleen bewust en met een notitie erbij.
- Energie-inschattingen zonder data altijd als schatting markeren.
- Lever de set altijd ook als importeerbare bestanden (sectie 9), niet alleen als tekst — een set die je niet kunt draaien is half werk.
- De DJ heeft het laatste woord: presenteer de set als voorstel, niet als wet.
