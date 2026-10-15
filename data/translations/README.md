# Public-domain English comparisons

Imported 2026-10-15. Historical translations by James Murdock and John Wesley Etheridge are public domain. Only translation text and printed notes are included, not the hosting sites' design or navigation. Both editions contain all 260 New Testament chapter files. Chapter presence does not imply that every verse is separately numbered or present.

Sources:
- Murdock: https://aramaicnewtestament.org/peshitta/murdock/gospel/matthew_1.htm
- Etheridge: https://aramaicnewtestament.org/peshitta/etheridge/gospel/matthew_1.htm
- Etheridge public-domain statement: https://www.studylight.org/site-resources/copyright-statements/eng/jet.html
- Official public-domain SWORD Murdock edition: https://ftp.crosswire.org/sword/modules/ModInfo.jsp?modName=Murdock

Each JSON records source-page URLs and SHA-256 hashes. `tools/import_translations.py` discovers the linked chapter pages, caches their HTML under ignored `downloads/translations`, parses translation content and preserves verse/paragraph/chapter references. Some pages contain Windows-1252 punctuation despite declaring UTF-8; decoding is checked before parsing to avoid silent truncation.

Murdock's site mislabels Revelation 2 with incorrect chapter text. That chapter is supplied from the official SWORD module's Revelation 2 (GBF, zText book block 26); its archive URL, checksum, public-domain license and 29 decoded verses are preserved in `murdock-revelation-2.json`. The importer reapplies this correction reproducibly. The linked Murdock text and its historical electronic SWORD source omit some separately numbered verses; the UI explicitly reports unavailable verse addresses instead of filling them from another translation.

Etheridge is displayed in its printed paragraph ranges. Chapters without verse-labelled paragraphs remain whole chapters. Romans 7 has an out-of-range printed section number; it is displayed as an intact chapter with an explanatory note. No English word alignment or artificial verse segmentation is inferred. Manuscript breaks and SyrNT word fragments remain independent of these English spans.
