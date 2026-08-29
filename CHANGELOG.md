# Changelog

Tutte le modifiche rilevanti del plugin **GeoPackage Converter**.
Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.1.0/),
versionamento semantico ([SemVer](https://semver.org/lang/it/)).

## [Da fare] — idee future

Funzionalità valutate ma non implementate, da rivalutare in base al feedback d'uso reale:

- **Modalità "Da progetto" → raggruppamento per cartella sorgente dei layer.**
  Replicare l'organizzazione del filesystem dei file sorgente dei layer caricati
  in QGIS, mantenendo la simbologia personalizzata. Sovrappone il caso d'uso
  della modalità "Da cartella" + `.qml` di default; tenuta in stand-by per
  evitare ridondanza UI. Rivalutare se richiesta esplicitamente da utenti.

- **Editor avanzato dei gruppi (drag & drop / regole regex).**
  Permettere di riorganizzare manualmente i layer in gruppi custom prima della
  conversione, con interfaccia ad albero o pattern matching. Utile per dataset
  legacy molto disordinati.

- **Compilazione automatica delle traduzioni `.qm` nello zip di release.**
  Attualmente i file `.qm` devono essere generati a mano via
  `i18n/build_translations.bat`. Da automatizzare in CI.

- **Header copyright nei file `.py`.**
  Aggiungere boilerplate GPL-3.0 in cima a ogni sorgente Python.

- **Raster dentro gli archivi (ZIP e RAR).**
  Oggi dagli archivi vengono estratti solo i file vettoriali (come per lo
  ZIP fin dall'inizio). Estendere l'espansione anche ai raster interni, per
  entrambi i formati contemporaneamente, non in modo asimmetrico.

## [0.3.2] — 2026-08-24

Compatibilità Qt6 completa per il controllo "QGIS 4 Ready" del repository
ufficiale. Nessuna modifica funzionale.

### Corretto

- Tutti gli enum convertiti alla forma con ambito, valida sia su Qt5 sia
  su Qt6: `QgsMapLayer.LayerType.*`, `QgsTask.Flag.CanCancel`,
  `QMessageBox.StandardButton.*`, `QgsProjectionSelectionWidget.CrsOption.
  CrsNotSet`, `QgsProcessing.SourceType.TypeMapLayer`,
  `QgsProcessingParameterNumber.Type.*`, `QgsProcessingParameterFile.
  Behavior.Folder`, `QgsVectorFileWriter.WriterError.NoError`,
  `QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer`,
  `QgsRasterFileWriter.WriterError.NoError` (21 occorrenze).
- Verificato con smoke test su QGIS 3.44 (Qt 5.15) e QGIS 4.2 (Qt 6.11):
  enum risolti, algoritmi di Processing costruiti, conversione doppia con
  append riuscita su entrambi.

## [0.3.1] — 2026-08-20

Irrobustimento di sicurezza/qualità per lo scanner del repository ufficiale
dei plugin QGIS (Bandit + Flake8). Nessuna modifica funzionale.

### Corretto

- Sostituiti i blocchi `try/except: pass` con `contextlib.suppress`
  (segnalati da Bandit B110): callback di progresso, snapshot degli stili,
  caricamento stile di default, teardown di menu/toolbar.
- L'apertura della cartella/report di output ora usa
  `QDesktopServices.openUrl` invece di `subprocess`/`os.startfile`
  (segnalati da Bandit B603/B606/B607); più corretto e multipiattaforma.
- Rimossi import inutilizzati (`typing.Callable`, `QgsLayerTree`,
  `subprocess`, `sys`) e la variabile `result` non usata; sistemati gli
  E402 in `processing/provider.py` e il nome di variabile ambiguo `l`.

## [0.3.0] — 2026-08-20

Conversione di sorgenti remote e non-file dalla modalità progetto, e
supporto agli archivi `.rar` in modalità cartella.

### Aggiunto

- **Layer remoti e non-file in modalità "Da progetto"** — i layer
  vettoriali che non provengono da un file (WFS/OGC API Features, ArcGIS
  REST FeatureServer, memoria, testo delimitato/CSV, PostGIS, SpatiaLite…)
  vengono ora convertiti in GeoPackage passando al writer un **clone del
  layer vivo** invece di riaprirne la sorgente con il provider `ogr` (che
  non ne conosce l'URI). Prima venivano scartati con l'errore fuorviante
  "Source file does not exist".
- **Raster remoti (WCS, ArcGIS MapServer, WMS)** — vengono campionati in
  un GeoTIFF temporaneo tramite il *raster pipe* di QGIS e poi convertiti
  in tile GeoPackage riusando le opzioni di tiling esistenti. Estensione
  e risoluzione sono **modificabili** in una nuova riga di opzioni
  (estensione intera del layer o della mappa corrente; risoluzione nativa
  o personalizzata), con **stima della dimensione** dell'output e avviso
  quando è molto grande.
- **Archivi `.rar` in modalità "Da cartella"** — letti senza estrazione
  tramite GDAL `/vsirar/` (richiede GDAL ≥ 3.7 con libarchive, es. QGIS
  3.44+). Verifica automatica della capacità: se il GDAL installato non
  supporta i RAR, l'archivio produce un avviso chiaro e la conversione
  degli altri file prosegue.
- **Riconoscimento `/vsirar/` e `/vsi7z/`** anche in modalità progetto per
  i layer già caricati da un archivio.
- **Fallback all'inglese** quando la lingua di QGIS non ha una traduzione
  del plugin (prima ricadeva sull'italiano di origine). Vale sia per
  l'interfaccia sia per il report HTML.
- **Nuovi parametri di Processing** nell'algoritmo "Da progetto":
  estensione e risoluzione per i raster remoti.
- **Marcatori di provider** nell'elenco dei layer di progetto (`[WFS]`,
  `[ArcGIS FS]`, `[PostGIS]`…) ed etichette di provider negli errori/report
  al posto di percorsi finti.

### Note tecniche

- Nuovo modulo `core/provider_policy.py` (routing per provider, unica
  fonte per i prefissi VSI e le etichette).
- `core/converter.py`: `_write_layer` accetta un `QgsVectorLayer` già
  valido; gli item con `layer_ref` saltano il controllo di esistenza su
  disco. Il clone è creato sul thread principale e rilasciato dopo ogni
  item.
- `core/raster_converter.py`: nuovo `_write_remote_raster` + helper puri
  `default_remote_resolution`/`estimate_remote_pixels`/`is_output_huge`.
- `core/folder_scanner.py`: `rar_supported()`, `_list_rar_members()`,
  `_iter_rar_vector_entries()`; corpo di espansione archivio condiviso tra
  ZIP (stdlib `zipfile`, invariato) e RAR (`gdal.ReadDirRecursive`).
- Sviluppato con assistenza IA. Licenza GPL-3.0-or-later.
- **i18n**: le nuove stringhe dell'interfaccia sono avvolte in `tr()` ma la
  traduzione EN/ES e la ricompilazione dei `.qm` restano da fare
  manualmente (`i18n/build_translations.bat` con pylupdate6 + Qt Linguist).
  Fino ad allora le stringhe nuove ricadono sull'italiano di origine.
- **Packaging**: nuovo `scripts/build_release_zip.py` (esclude `CLAUDE.md`,
  `tests/`, `.bat`, sorgenti `.ts` e file di marketing; percorsi con `/`).

## [0.2.2] — 2026-05-27

### Corretto

- In modalità "Da cartella" lo snapshot dell'albero dei layer del
  progetto non viene più riutilizzato per il caricamento dei GeoPackage
  generati: `_collect_items` azzera `_original_tree_snapshot`, così i
  layer convertiti vengono caricati con la struttura della cartella e non
  con quella (errata) del progetto.

## [0.2.1] — 2026-05-22

### Modificato

- Solo bump di versione / ri-pacchettizzazione. Nessuna modifica
  funzionale rispetto alla 0.2.0.

## [0.2.0] — 2026-05-21

Supporto raster completo e miglioramenti alla modalità progetto.

### Aggiunto

- **Conversione raster** — i layer raster (GeoTIFF, ASC, IMG, ECW, …)
  vengono convertiti in tile raster GeoPackage. Nuovo modulo
  `core/raster_converter.py` con classe `RasterConverter`.
- **Opzioni raster nella GUI** — formato tile (AUTO/PNG/JPEG/WEBP),
  dimensione tile (64–1024), qualità compressione (1–100).
- **Scansione raster nella modalità "Da cartella"** — `folder_scanner`
  rileva ora anche `.tif`, `.tiff`, `.asc`, `.img`, `.ecw`, `.jp2`, `.dt0`,
  `.dt1`, `.dt2`.
- **Preservazione dell'albero dei layer** — in modalità "Da progetto" i
  layer convertiti vengono ricaricati con lo **stesso ordine, gli stessi
  gruppi e la stessa visibilità** del progetto originale.
- **Clonazione completa degli stili raster** — poiché GeoPackage non può
  salvare stili raster (limitazione GDAL), il plugin copia automaticamente
  renderer, opacità, resampling, luminosità/contrasto dal layer originale
  tramite `exportNamedStyle`/`importNamedStyle`.
- **Nascondimento dei layer originali** — dopo il caricamento dei layer
  convertiti, gli originali vengono nascosti per evitare duplicazione
  visiva.
- **GPKG individuale per layer senza gruppo** — nella strategia "per gruppo
  della legenda", i layer non raggruppati ottengono ciascuno il proprio
  file `.gpkg` con il nome del layer (prima finivano tutti in un unico
  `ungrouped.gpkg`).
- **Breakdown vettoriali/raster nel report** — la card "Conversioni
  riuscite" mostra il dettaglio "N vettoriali + M raster" quando presenti
  entrambi i tipi.
- **Algoritmi di Processing aggiornati** — sia "Da cartella" che "Da
  progetto" supportano ora la conversione raster con parametri dedicati.

### Corretto

- Tooltip della strategia di raggruppamento: rimossa l'opzione inesistente
  "Per CRS" e aggiornata la descrizione "Per gruppo della legenda".
- `RasterConversionError` aggiunta a `core/exceptions.py`.

### Note tecniche

- Nuovo file: `core/raster_converter.py`.
- `gui/main_dialog.py` esteso con snapshot dell'albero layer, caricamento
  da snapshot, nascondimento originali, clonazione stili raster.
- `gui/main_dialog_base.ui` aggiornato con pannello opzioni raster.

## [0.1.0] — 2026-05-03

Prima versione sperimentale. Funzionalmente completa.

### Aggiunto

- **Modalità "Da progetto"** — converte i layer vettoriali del progetto QGIS
  attivo in GeoPackage, preservando la simbologia personalizzata.
- **Modalità "Da cartella"** — scansiona ricorsivamente una cartella e converte
  tutti i file vettoriali trovati. Formati: `.shp`, `.tab`, `.kml`, `.kmz`,
  `.gml`, `.geojson`, `.json`, `.dxf`, `.gpx`, `.mif`. Supporto nativo `.zip`
  via GDAL `/vsizip/` (niente estrazione su disco).
- **Selettore CRS standard QGIS** (`QgsProjectionSelectionWidget`) con preset
  italiani: ETRS89/UTM 32-33N, WGS 84/UTM 32-33N, RDN2008 (6875/6876),
  Gauss-Boaga (3003/3004), WGS 84 (4326).
- **Strategie di raggruppamento**:
  - Tutto in un unico GeoPackage.
  - Un GeoPackage per sottocartella (modalità cartella).
  - Un GeoPackage per gruppo della legenda (modalità progetto).
- **"Replica struttura su disco"** — l'output ricrea la gerarchia delle
  cartelle sorgenti in mirror, con un GeoPackage per cartella.
- **Riproiezione opzionale** verso qualsiasi CRS supportato da QGIS.
- **Salvataggio degli stili QML** dentro il GeoPackage (tabella
  `layer_styles`), con applicazione automatica al ricaricamento.
- **Validazione geometrie** opzionale via `native:fixgeometries`.
- **Modalità dry-run** (anteprima senza scrittura).
- **Caricamento opzionale dei layer generati nel progetto** con gruppi
  nidificati che riflettono la struttura del filesystem di output.
- **Auto-detect dell'encoding** per shapefile (sidecar `.cpg`, `chardet`,
  fallback UTF-8).
- **Suggerimento del nome di output** basato sul nome del progetto/cartella
  (modificabile dall'utente).
- **Persistenza delle preferenze** via `QSettings`.
- **Esecuzione in background** via `QgsTask` (UI mai bloccata).
- **Annullamento** dei task lunghi.
- **Notifica QGIS** non intrusiva al termine (`messageBar`) con bottone
  "Apri report".
- **Report HTML** dettagliato con statistiche, errori e avvisi.
- **Algoritmi di Processing** (modello / batch process):
  - "Converti cartella in GeoPackage"
  - "Converti layer del progetto in GeoPackage"
- **Compatibilità Qt5/Qt6** — funziona su QGIS 3.34+ (Qt5), 3.44 (Qt5/Qt6),
  4.0+ (Qt6). Centralizzata in `compat.py`.
- **Long-path support su Windows** — uso del prefisso `\\?\` per superare
  il limite MAX_PATH 260 char (utile per cartelle nidificate o con caratteri
  speciali come `°`).
- **Gestione OneDrive online-only placeholders** con messaggio chiaro
  all'utente.
- **Internazionalizzazione (i18n)** — italiano (sorgente), inglese, spagnolo.
- **Tooltips ricchi (HTML)** su ogni controllo, bottoni di aiuto ⓘ
  contestuali con esempi pratici.
- **Suite test 112 casi** (`pytest`), copertura `core/` 77%.
- **CI GitHub Actions** su Python 3.9/3.11/3.12 con `ruff` lint, coverage
  gate 70%, scan compatibilità PyQt6, build artefatto zip.

### Note tecniche

- Sviluppato con assistenza IA.
- Licenza GPL-3.0-or-later.
- Status: sperimentale (`experimental=True` in `metadata.txt`).
