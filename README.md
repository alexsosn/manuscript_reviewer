# Manuscript reviewer — Syriac validator

Source repository: [alexsosn/manuscript_reviewer](https://github.com/alexsosn/manuscript_reviewer).

## Install from source

```sh
git clone https://github.com/alexsosn/manuscript_reviewer.git
cd manuscript_reviewer
npm ci
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python tools/fetch_data.py
export SYRIAC_PYTHON="$PWD/.venv/bin/python"
npm start
```

Choose your manuscript workspace when prompted, then configure PAGE input, images and output under **Folders / settings**. Alternatively set `SYRIAC_WORKSPACE` before launching. The repository contains app source, tests, a synthetic PAGE fixture, the PAGE schema and reference-data provenance. Manuscript scans, local transcriptions, catalog entries, credentials, builds and downloaded corpora are excluded from Git. The setup script fetches the pinned public reference datasets with their original attribution and license files; the app then works offline.

Run `npm test` and `python -m unittest discover -s tests -p 'test_*.py'` after fetching reference data. A real-page integration test additionally runs when this checkout is inside the existing manuscript workspace; it is skipped elsewhere. Build the macOS app with `npm run build`.

Local Electron editor for the BL Add MS 14,470 manuscript. Open the latest build, `dist/v0.4/mac/Syriac validator.app` on this Intel Mac. The packaged app finds this manuscript workspace automatically. Folders / settings lets you choose another workspace, PAGE input folder, image folder and output folder.

## Manuscript XML repository

The manuscript PAGE files and edit history are maintained separately in [alexsosn/BL-Add-MS-14-470](https://github.com/alexsosn/BL-Add-MS-14-470). On this Mac, the parent `HTR_WS_2026` workspace is that repository checkout; this app folder remains its separate code repository. Save XML normally, then run the workspace’s **Snapshot XML edits.command** to commit and push changes. This snapshots local files; Transkribus upload remains a separate action.

## Editing

- The page list opens native Transkribus PAGE XML. The default input is `layout_corrected/page`, with the newer `layout_v2/page` samples taking precedence where present. Opening a page does not modify it.
- Original, enhanced colour and ink-contrast images share the original coordinates. Select a line from its crop, text field or scan baseline. Zoom and pan the scan independently.
- Edit one RTL transcription field per manuscript line. Enter moves to the next line. Reference alignment uses the continuous text for passage matching, then partitions it back onto manuscript lines, including words split across lines. It never automatically replaces OCR. “Use reference fragment” is an explicit replacement of one line; check manuscript variants and punctuation before accepting.
- The book selector and optional `Luke 3:14` anchor can constrain difficult alignment. Agreement scores ignore punctuation, spaces and combining marks; they are spelling agreement, not a calibrated confidence estimate. Missing OCR and manuscript variants can distort individual boundaries even when the page score is high.
- Click any reference word to view its occurrence-specific SyrNT / SEDRA lemma, root and grammatical analysis with dictionary glosses. A word split across manuscript lines retains the same whole-word analysis in both fragments. Click differing OCR words or select text to search attested form analyses and offline SEDRA lexeme candidates. Dictionary suggestions without definitions are hidden. Other spellings remain labeled possibilities rather than asserted analyses.
- Layout modes expose draggable baseline, line-polygon and region-polygon vertices. In one of these modes, use the Vertices selector: Move drags an existing point; Add inserts a point where you click on the scan, between the nearest pair of vertices (or extends a baseline endpoint); Delete removes the point you click. Polygons keep at least three vertices and baselines at least two. These edits support undo and autosave. Draw a rectangle to add a line or marginal region. Baselines can be rotated by dragging their endpoints. Select fragment checkboxes to merge one manuscript row in RTL order; separate rows are rejected. Split at the text caret, then adjust geometry to the actual split. Arrow buttons reorder lines. “Right column first” orders the two main regions and keeps annotations separate. Re-align after changing line order.
- Changes autosave after a short pause; Ctrl/⌘+S saves immediately. Undo/redo applies to layout and transcription. Closing waits for the local save.

Edits go to `local_edits/page`; source exports and images stay unchanged. Pre-edit XML backups are in `local_edits/backups`, up to 30 per page. Save checks the opened file revision and validates PAGE XML against the bundled 2013 schema, excluding the Transkribus metadata extension. Existing IDs, custom tags and untouched confidence are preserved; changed lines lose stale word-level OCR data and confidence.

The Syriac keyboard at the bottom inserts letters, vowel marks, seyame and punctuation at the caret in the last focused manuscript text field or lexicon search field. It can replace a selection, insert a space and delete a whole marked character. Keyboard edits use the same autosave/undo path as typing.

## Transkribus

Connect using the Java client's saved login on this Mac or your account credentials. Tokens stay in memory and passwords are not persisted. The existing Java login reader depends on that client's preferences and JAR being present.

Before editing a page already changed online, use **Get server page** to download its current version. This backs up the local draft and replaces it with current server XML; reconcile your changes before upload. The app does not automatically merge local and remote changes.

**Upload this page** submits only the selected page, creates a new transcript version, preserves its current status, checks the current server transcript ID against the locally opened ID, and downloads the result to verify layout/text. A newer remote version blocks upload. There remains a small race between the version check and submission; coordinate page ownership with other editors. Accepted uploads with failed verification are reported explicitly: inspect/download before trying again. Receipts are written to `local_edits/uploads`.

The initial collection/document are 2536248 / 19244795. Upload scope defaults to pages **3, 4, 349** because other people are editing other pages. Change “Pages I am editing” only after coordinating with them. There are no batch uploads or automatic remote writes.

## Data and runtime

The reference corpus, its word-level morphology and lexicon are bundled offline, with source revisions and attribution in `data/provenance.json`. The Peshitta source is ETCBC `syrnt`, MIT. sycgloss credits are retained; its LICENSE and README give different license notices, both included.

This build uses the existing Python runtime on this Mac, including lxml and cryptography. It is not a portable Python-free distribution. Set `SYRIAC_PYTHON` to another Python with those libraries if needed. Electron is bundled in the `.app`; the local source checkout reuses the installed KTU-validator dependencies through an ignored symlink. A fresh clone uses `npm ci` and the committed lockfile.

Development: `npm start`; browser preview: `npm run preview` at http://127.0.0.1:8770. The browser preview uses the same interface but intentionally cannot save, authenticate or upload. Python backend tests: use the configured Python with `-m unittest discover -s tests -p 'test_*.py'`; geometry tests: `npm test`.

API upload checks are covered with mocks and use the previously verified single-page API route. This app's connection/download is smoke-tested against the live service; no manuscript page is uploaded during app development testing.

CAL was evaluated as an alternative. Its public server requests that automated clients obtain an academic data dump rather than scrape the website. The editor therefore uses the existing SyrNT morphology with sycgloss glosses; it does not claim to provide CAL definitions.

## Paleographical table

Open **Paleography** for a comparison table: 22 Syriac letter rows, with isolated, initial, medial, final and unclassified columns. You curate each example; the existing PAGE export has no glyph coordinates, so the app does not infer letter boundaries from OCR.

Click **Collect example from scan**, select the relevant line and drag a rectangle around a letter. The crop dialog lets you assign the letter and form, confirm the source line, and record notes. The nearest line is suggested by geometry; confirm it before saving. A letter should be cropped in enough context to show its joining form. Examples remain tied to the original image coordinates even when PAGE layout is edited.

Click an example image to change its classification/notes or remove it. Click its page/folio/line link to return to the editor with the original crop highlighted. If a line ID was removed by subsequent merging, the original crop still opens at its scan location. Filter by letter or hide empty rows. **Print / save PDF** prints the table in landscape through the operating system's print dialog.

The catalog is independent of PAGE XML: `local_edits/paleography/index.json`, with prior versions under `local_edits/paleography/backups`. It records source identities, rectangle coordinates, classification, notes and the line's text at collection time. It is not uploaded to Transkribus. Catalog saves detect changes from another window. Browser-preview collections are temporary and explicitly labeled preview only.

## Page-local reference review experiment

`tools/reference_review.py` prepares native Transkribus `unclear` spans with the SyrNT spelling in **alternative** and the book/chapter/verse in **reason**. It compares whole-page letter sequences while retaining physical line anchors and is restricted to pages 3 and 4. It does not create collection-wide tags. `prepare WORK_FOLDER` downloads current versions and validates annotation-only changes; `upload WORK_FOLDER` checks hashes and parent versions, creates new versions, and verifies read-back. Existing receipts prevent repeat submission. No Electron menu or automatic remote write was added.

`tools/fix_reference_comments.py prepare WORK_FOLDER` converts only the earlier experiment's Reference spelling / Passage comments into these native fields; `upload WORK_FOLDER PAGE` is restricted to page 3 or 4. The original comment definition showed only an empty `type` field in the web editor; adding `type` was insufficient because web serialization discarded it. Native alternative/reason fields were visually verified and survived a web save. The XML repository records the final experiment under `reference_review_3_4/native_tags`. Existing local drafts are not automatically replaced.
