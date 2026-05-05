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
