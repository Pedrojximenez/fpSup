fpSup-Formats v0.6.0, fpSup-Lossless-Mem v0.1.3m3 and fpSup-Gyro-Data v1.14.1d1  (2026-10-05)  by Jose Hurtado

composer.html   fpSup-Merge (Bei's page, current version) with these sups added.  Open it in a
                browser, tick the sups you want, and copy what it gives you to the root of the card.
                Everything it needs is inside the file.
releases/       every sup as a standard fpSup release folder (fpSup.BIN, AutoRun.txt, README,
                MANIFEST, ABOUT):
                  fpsup-fmt-s16, -og2k, -og3k, -og35k, -og4k  (v0.6.0)  one format each; combine any of
                      them with each other and with Gyro, RAW-View and Lossless.  New in v0.6.0: OG4K
                      and OG3.5K follow the camera's Crop Mode (1:1 centre crop, same DNG size).
                  fpsup-lossless-mem-v0.1.3m3  fpSup-Lossless that starts ON and remembers ON/OFF on the card
                      (\FPSUP.INI).
                  fpsup-gyro-data-v1.14.1d1  fpSup-Gyro with a "Gyro Data" ON/OFF row (OFF: no gyro
                      logging, e.g. for S16 at 100 fps), remembered in \FPSUP.INI.  First
                      camera test OK.
lossless-memory/  for Bei / developers: the guide (written so an AI agent can apply it or
                  recreate it by hand), the change as ONE patch on fpSup 2aa8d9a, and the
                  shared settings file's spec.
gyro-data/        the same for fpSup-Gyro-Data (one patch, applied after lossless-memory's).
CATALOGUE.txt     the catalogue changes in composer.html (composer-src/ has the edited file).

In composer.html the older fpSup-OG2K, fpSup-OG3K, fpSup-Lossless and fpSup-Gyro are under
"Deprecated" (pick that category to see them): the Formats tiles, Lossless-Mem and Gyro-Data
replace them.

Firmware Ver.5.02 only.  RAM only: delete AutoRun.txt, remove the battery, and the camera is stock.
Test builds.  Bugs and questions to the author.
Web: https://elcacharrista.com  (El Cacharrista)
How it was made: https://elcacharrista.com/en/articles/hacking-the-sigma-fp-with-ai/
