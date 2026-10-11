# What each sup changes in the native UI — inventory for a shared UI service

2026-10-01. Read-only inventory (no code changed). Purpose: decide the
operations a shared UI service must offer so that sups add rows, hide rows,
add options (Settings + Quick Set + LV) and grey options out **without claiming
coordinates** and while each card still works alone.

Sources: releases in `fpSup/releases` (newest per product), `projects/open-gate/build`
(OG3K/OG2K UI, Sensor Lab `imx410_rate_*`), `projects/rawview/README.md`,
`fpSup/lossless/native/menu_page.c`, section inventory
`projects/lossless-sup/build/hook-inventory/`.

## 1. Per product

| product | what it adds | layers it touches | how | timing |
|---|---|---|---|---|
| **OG3K / OG2K** | a 3rd **resolution option** (OG3K / OG2K) | CSV `B2_5_4` (NBR, in place); controller max `C1A709BC` (B2_5); ~360 NBU records: QS layout keys 315, state-end 36, literal deltas 6, summary 1, QS limits 2; 3 XCI in a private NBR pack; string aliases | parser hooks `C05E6400` (per-record copy by address+FNV), `C05E5B58` (string alias F2..F6, requires stock pool), `C05E84D8` (register private NBR), `C05D90F0` (release cached QS layout so it re-parses) | QS is cached from boot → forced re-parse; B2_5 parses on open |
| **Sensor Lab** | options **240 fps** (frame rate) and **14-bit** (bit depth); **grey-out** by mode; 10th **summary label**; LV frame-rate **text** incl. 240/15 | CSV variants (`B2_5_5`, `_excl*`, `B2_5_2`…) in place incl. `Enabled,Enabled2`; controller max; ListItem instance count; per-value `controlValueEvent`+`controlFocus` (inserted, space from an empty Icon); B2_5 **whole set rebuilt in its slot**; 4 LV sets rebuilt in their slots; enum converter immediates (movw/movt/count) | data sections written by the loader + 5 native hooks (value lists, normaliser, cached table) | B2_5 on open; LV sets per rebuild of the screen |
| **raw-view** | a 17th **option** in COLOR (ColorButtonMenu) + QS | 3 CSV (`ListColorButtonMenu`, `_EXCL`, `_EXCL2`) in place; controller max (Color page, COLOR key page, 3 QS pages); text clip keys; per-value controlValueEvent; QS group ends 01F4→0215; getter table (movw/movt) + GUI→enum call-site stubs | data in place (milestones 1–2 done); record hook planned for text (would need to chain with OG3K's) | COLOR menu released on close → re-parses; QS needs CINE↔STILL |
| **lossless** | a new **row** under Audio Recording (SHOOT 2 CINE) | whole MainB2 page replaced (clone of same-page Audio row + renames), extended string pool, 3 private app variables | runtime: page redirect (`entry+08`) + pool switch (`reader+0x10/+0x14`) + `C05DB309` register | MainB2 re-parses on every menu open |

## 2. What collides today

- **String pool** (`reader+0x14`): lossless replaces it; OG's alias hook requires the stock one.
- **B2_5 set**: OG edits a word inside it (`C1A709BC`); Sensor Lab rebuilds the whole set in place.
- **QS pages**: OG copies records by address at parse; raw-view plans limit/group edits in the same pages.
- **Parser hook `C05E6400`**: OG owns it; raw-view's plan would need a second one ("chain with OG3K").
- **Enum converter immediates**: each product repoints the converter of its own control. They collide only if two products extend the same control.

Section-level code patches do not collide between products that can be selected together (hook inventory). The collisions are all in **UI resources and the runtime structures that serve them**.

## 3. Kinds of edit found (what a service would have to express)

| kind | example | today done by |
|---|---|---|
| add a row to a page | lossless | page replacement |
| hide a row | (requested) | — |
| add an option to a list: CSV row, controller max, ListItem instances, per-value controlValueEvent+controlFocus | 240 fps, 14-bit, RAW, OG3K | in-place data / record hook |
| option's summary label (IconText child / text keys) | 240 summary, RAW text | borrowed Icon / clip keys |
| option's QS tile state (companion keys, state ends, limits, images) | OG3K (≈360 records) | record hook + private NBR |
| option's LV text/icon | 240 LV | LV set rebuilt in slot |
| grey an option in/out (`Enabled,Enabled2` in CSV variants) | Sensor Lab mode gating | CSV variant in place |
| row↔enum and enum↔state tables | all option adders | movw/movt repoint |
| private strings | OG labels, lossless names | alias hook / own pool |
| private icons | OG3K QS | private NBR pack |
| setting-layer acceptance (value lists, normaliser) | Sensor Lab | native hooks — **product semantics, stays in the product** |

## 4. Timing facts every edit depends on

- Settings subpages (B2_x, MainB2, COLOR menu): parsed when shown, released on close/menu open → a runtime edit before the next open takes effect.
- QS layouts: parsed at boot and **held**; an edit needs a forced re-parse (OG's `C05D90F0` release) or a CINE↔STILL switch.
- LV sets: rebuilt with the screen; Sensor Lab writes them in place from the loader.
- NBR directory entries are dead after first lookup (repoint does not work); NBR **content** in place works; a private NBR pack needs `C05E84D8`.
