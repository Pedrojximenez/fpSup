# Jose Hurtado

Third-party work by **Jose Hurtado** (El Cacharrista, https://elcacharrista.com).
All credit for the formats, the menu work and the camera tests is his; questions
about the original packages go to him.

| Folder | What |
|---|---|
| `formats-v0.6.0/original/` | His fpSup-Formats v0.6.0 packages S16, OG3.5K, OG4K, **untouched**, plus the package `README.txt` and `CATALOGUE.txt` |
| `formats-v0.6.1/original/` | The same for v0.6.1 (2026-10-06: video clamp against high-ISO shadow flicker), package README as `PACKAGE_README.txt`. ⚠ Only three of the five v0.6.1 packages: OG2K (slot 2) and OG3K (slot 3) are still only in `~/Downloads/fpSup-Formats-v0.6.1/releases/` (notes/JOSE_VS_OURS.md) |
| `formats/tools/` | Offline analysis of those binaries (VBIN reader, disassembly, layout); `FMT_VERSION=0.6.0\|0.6.1` picks the package, default the newest |
| `formats/v3/` | The three as one Loader v3 sup `31FMT.BIN`: builder, entry, tests |
| `formats-v0.6.0/cards/`, `formats-v0.6.1/cards/` | Test cards built from each (never written to a camera); the v0.6.0 card predates the uishare string layer and Loader service version 3 |
| `formats-v0.6.0/analysis/` | The v0.6.0 code listing |
| `notes/FORMATS_V3.md` | How the conversion was done, what it claims, what is open |

## Source

- `~/Downloads/fpSup-Formats-v0.6.0/` (package dated 2026-10-05), copied 2026-10-06.
- `~/Downloads/fpSup-Formats-v0.6.1/` (package dated 2026-10-06), copied 2026-10-06.
- PR https://github.com/ijigen/fpSup/pull/7 (v0.4.0a, head `jahurtado:formats-v0.4.0a`
  `d78073c`). Neither the PR nor his fork `jahurtado/fpSup` contains the Formats
  source, only release binaries. The research tree the v0.3.0a MANIFEST names
  (`projects/open-gate/build/registry/`) is not on this machine.

SHA-256 checked against each package's `MANIFEST.txt` (all match):

| Package | fpSup.BIN | AutoRun.txt |
|---|---|---|
| fpsup-fmt-s16-v0.6.0 | `cbbad4ec8bac80d416a2423df4e7dbcfd1c6fd6140894a9f1dea8af85eb2dbcd` | `3a0eb242304245fd9442de03409523834a92b390ad418703d349578862ea651d` |
| fpsup-fmt-og35k-v0.6.0 | `948da9c0f75faa60e8cc47b203603a9c2c91fd74e8ca91097983a65db6f481a6` | `c2d377b71b7770a3b84cfec357801dd1ac02b5a5ca1b0149b81bee4719bb707b` |
| fpsup-fmt-og4k-v0.6.0 | `5be8ac400db11bed51d969e3eb3b33e391bcdcd96e3fd48bdb991b92c889a1c0` | `c69a1cc913bbc28fe7c4436120fb2cbd8270c43b507a725173366c495699773d` |
| fpsup-fmt-s16-v0.6.1 | `57da65dad07c96477d7946931470b6b57ac824cd1388a733ac0c1ecb253cb91d` | `b10608e2145266aa40632a6e01c33d071ef0151d96d5390603d1d6e205a5a07c` |
| fpsup-fmt-og35k-v0.6.1 | `6e2d4f6384fe43c93a24da7255937335b747ba5124d2c80b73ef58ddbcd4a9c5` | `bb6ab78c00a614cc9cc046247897e8b5ff4b0cf9aa2f2f5851459df8520d53a2` |
| fpsup-fmt-og4k-v0.6.1 | `e54013735cbc516b5e379e91ce942c03512260155778812a23bce839a62ee3b5` | `87613eccba0c33e74c084e9be7040195b1a7fe3476728f3c729b0ff0695327af` |

The packages state "Test build. By Jose Hurtado". No licence file comes with them;
treat them as his work, shared with this project. Do not republish without his
agreement.
