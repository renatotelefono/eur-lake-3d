# EUR Lake 3D

Videogioco open-world esplorabile, ambientato in una ricostruzione digitale
del **Laghetto dell'EUR** (Roma) e dintorni, generata automaticamente da dati
**OpenStreetMap**. Motore: **Godot 4.x**. Modellazione/conversione: **Blender**.

Questo repository contiene la **Milestone 1**: pipeline dati funzionante +
scheletro di progetto Godot giocabile (cammina, corri, salta, esplora),
pronto per essere popolato con la geometria reale non appena esegui la
pipeline (istruzioni sotto).

## Stato attuale (Milestone 1)

Fatto:
- Pipeline `OpenStreetMap -> Overpass API -> GeoJSON locale (metri)` (`pipeline/fetch_osm.py`), con conversione di coordinate testata (`tests/test_osm_to_geojson.py`).
- Script Blender `pipeline/blender_import.py`: GeoJSON -> edifici estrusi, strade/sentieri come ribbon, acqua, aree verdi -> export `.glb`.
- Progetto Godot 4 giocabile: personaggio (camminata/corsa/salto/telecamera terza persona), cielo/illuminazione procedurali, caricamento del mondo generato con collisioni automatiche, vegetazione procedurale via `MultiMeshInstance3D`.
- Dati di esempio già presenti in `data/osm/*.geojson` (piccolo dataset finto ma geograficamente plausibile, centrato sul vero laghetto) così puoi aprire il progetto e vederlo funzionare **prima ancora** di eseguire la pipeline reale.

Da fare per completare la Milestone 1 con dati reali:
- Eseguire `pipeline/fetch_osm.py` con una connessione internet normale (vedi "Limite noto" sotto).
- Eseguire `pipeline/blender_import.py` in Blender per generare `assets/generated/eur_world.glb` dai dati reali.
- Aprire il progetto in Godot 4 e premere Play.

## Limite noto: rete

Questo progetto è stato preparato in un ambiente cloud isolato la cui policy
di rete **blocca l'accesso a `overpass-api.de`, `openstreetmap.org` e
`nominatim.openstreetmap.org`** (verificato durante lo sviluppo: le
richieste vengono rifiutate dal proxy con "connect_rejected" / 403). Per
questo `pipeline/fetch_osm.py` **non è stato eseguito con dati reali** in
questo ambiente: al suo posto, `tests/test_osm_to_geojson.py` valida tutta
la logica di conversione con un dataset finto ma realistico, e i risultati
sono già in `data/osm/`.

**Sul tuo computer, con una connessione internet normale, `fetch_osm.py`
dovrebbe funzionare senza problemi**: Overpass API è un servizio pubblico
gratuito. Se preferisci, posso eseguirlo direttamente io collegandomi a una
cartella sul tuo computer (basta cliccare "Aggiungi cartella" nell'app
desktop di Claude) e usando la rete del tuo computer invece di questa
sandbox.

## Prerequisiti

- **Python 3.10+** con il pacchetto `pyproj` (`pip install -r pipeline/requirements.txt`)
- **Blender 4.x** (per `blender_import.py`, headless o con interfaccia)
- **Godot 4.3+** (per aprire ed eseguire il progetto)

## Pipeline: come generare il mondo dai dati reali

```bash
# 1) Scarica ed elabora i dati OpenStreetMap per l'area (bbox 1x1km attorno
#    al Laghetto dell'EUR, definita in maps/eur/origin.json)
pip install -r pipeline/requirements.txt
python3 pipeline/fetch_osm.py --config maps/eur/origin.json --out data/osm/

# 2) Genera la mesh 3D ed esporta in glTF binario, con Blender headless
blender --background --python pipeline/blender_import.py -- \
    --data-dir data/osm \
    --out assets/generated/eur_world.glb

# 3) Apri il progetto in Godot 4 (Godot rileverà e importerà eur_world.glb
#    automaticamente al primo avvio dell'editor) e premi Play (F5).
```

Se salti il passo 1 e 2, il progetto Godot funziona comunque usando i
GeoJSON di esempio già inclusi in `data/osm/` (piccola porzione finta ma
plausibile dell'area), utile per verificare subito che tutto funzioni.

## Comandi in gioco

| Tasto | Azione |
|---|---|
| W A S D | Cammina |
| Shift (tenuto) | Corri |
| Spazio | Salta |
| Mouse | Guarda intorno (telecamera terza persona) |
| Esc | Rilascia/ricattura il mouse |

## Struttura del progetto

```
eur-lake-3d/
├── project.godot              # Config Godot 4 (autoload InputSetup, ecc.)
├── scenes/
│   ├── world/eur_world.tscn   # Scena principale
│   └── player/player.tscn     # Scena del giocatore
├── scripts/
│   ├── player/player.gd       # Controller giocatore
│   ├── world/world.gd         # Setup ambiente, caricamento mondo, spawn
│   └── systems/
│       ├── input_setup.gd     # Definisce le InputMap actions (autoload)
│       └── vegetation_scatter.gd  # Scatter procedurale alberi (MultiMesh)
├── assets/
│   ├── generated/             # Output di blender_import.py (eur_world.glb)
│   └── buildings/vegetation/roads/vehicles/textures/  # Per asset futuri fatti a mano
├── maps/eur/origin.json       # Configurazione area: origine, bbox, default
├── data/osm/                  # GeoJSON locali (output di fetch_osm.py)
├── pipeline/                  # Script Python + Blender (non fanno parte del build Godot)
│   ├── coords.py              # Conversione lat/lon <-> metri locali (proiezione AEQD)
│   ├── overpass_query.py      # Costruzione query Overpass QL
│   ├── osm_to_geojson.py      # Overpass JSON -> GeoJSON locale (logica pura, testabile)
│   ├── fetch_osm.py           # CLI: orchestrazione rete + conversione
│   ├── blender_import.py      # GeoJSON -> mesh 3D -> eur_world.glb
│   └── requirements.txt
└── tests/
    └── test_osm_to_geojson.py # Validazione offline della pipeline (no rete richiesta)
```

## Note tecniche importanti

**Sistema di coordinate.** Il mondo NON usa lat/lon come coordinate 3D
(distorcerebbe le distanze). `pipeline/coords.py` usa una proiezione
azimutale equidistante centrata sull'origine (Laghetto dell'EUR,
41.828447°N 12.466024°E, fonte: Turismo Roma) per ottenere metri reali.
Convenzione assi: **X = est, Z = -nord (nord = -Z), Y = quota**, origine
= centro dell'area = `(0,0,0)`, coerente con la richiesta della spec.

**Perché Blender genera solo i contorni delle aree verdi.** La vegetazione
vera e propria (alberi) è generata **a runtime in Godot** via
`MultiMeshInstance3D` (`scripts/systems/vegetation_scatter.gd`), come
richiesto dalla spec ("eventualmente MultiMesh in Godot"): questo è molto
più leggero che avere migliaia di alberi come mesh statiche esportate da
Blender, e rende facile modificare densità/aspetto senza rigenerare il glb.

**Collisioni.** Non sono pre-calcolate in Blender: `world.gd` chiama
`create_trimesh_collision()` su ogni mesh generata al caricamento, così
edifici/terreno/strade sono automaticamente solidi.

**Altezza edifici.** Se OSM ha il tag `height`, viene usato direttamente;
altrimenti `building:levels × 3m`; altrimenti un default configurabile in
`maps/eur/origin.json` (9m).

**Limiti noti (accettabili per una Milestone 1, da migliorare in seguito):**
- Le relation multipolygon complesse di OSM (acqua/parchi con "buchi") non
  sono gestite: solo way semplici. Il Laghetto dell'EUR è comunque mappato
  come way singolo su OSM, quindi non è un problema per l'area iniziale.
- Le ribbon di strade/sentieri non hanno raccordi (miter) elaborati agli
  incroci: visivamente accettabile a bassa velocità di cammino, da
  migliorare quando si aggiungeranno veicoli.
- Nessun LOD/chunk/occlusion culling ancora implementato: rimandato a
  quando l'area supererà 1×1km (vedi Roadmap).

## Licenza e attribuzione dati

I dati geografici provengono da **OpenStreetMap**, con licenza **Open
Database License (ODbL)**: qualunque distribuzione del gioco (anche
prototipi condivisi) deve includere l'attribuzione **"© OpenStreetMap
contributors"**, visibile nella UI (da aggiungere in un pannello crediti/
menu — non ancora implementato in questa Milestone 1). Se in futuro
integrerai fotografie geolocalizzate (Mapillary, KartaView, ecc.), verifica
sempre la licenza specifica di ciascuna fonte prima di usarle come texture o
elemento di gameplay: **Google Street View non va usato per scaricare
screenshot da incorporare nel gioco**, come specificato nella progettazione
originale.

## Roadmap (dalle milestone del progetto)

1. **Milestone 1** (questa consegna): area reale visualizzata in 3D, giocatore che cammina — pipeline dati + scheletro Godot pronti, da eseguire con dati reali.
2. **Milestone 2**: rifinire edifici/vegetazione/acqua/strade con dati reali completi, aggiungere marciapiedi/segnaletica semplificata.
3. **Milestone 3**: gameplay — missioni basate su coordinate reali, POI interattivi (già estratti in `data/osm/poi.geojson`), minimappa/GPS virtuale.
4. **Milestone 4**: immagini geolocalizzate (Mapillary/KartaView, con verifica licenza) come riferimento/texture/elemento di gameplay.
5. **Milestone 5**: sistema a chunk per estendere oltre l'area iniziale (EUR → Roma → altre città) senza riscrivere la pipeline — l'architettura modulare attuale (config per area in `maps/<area>/origin.json`, pipeline parametrica) è pensata apposta per rendere questo passo incrementale.
