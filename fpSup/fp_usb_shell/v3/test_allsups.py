#!/usr/bin/env python3
"""Loader v3's built-in fpSup management (allsups.c) under unicorn: the real
loader.S and a LOADER.BIN built with allsups=True load \\fpSup\\UI\\ALLSUPS.BIN
from a card, against the real image.  The UI app is test_ft6's fake (the stock
NBR loader C05E84D8 is Python); uishare's string layer and the page-id layer
run for real.

    cd fpSup/fp_usb_shell && python3 -B -m unittest v3.test_allsups
"""
import pathlib
import struct
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
TAB = HERE.parents[1] / 'uishare' / 'tab'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TAB))
import test_ft6 as F6                                         # noqa: E402 (fake app, sys.path)
import build_ft6 as FT                                        # noqa: E402
import manager_logo as LOGO                                   # noqa: E402
import build_v3 as B                                          # noqa: E402
import test_v3 as T                                           # noqa: E402

DATA_PATH = '\\fpSup\\UI\\' + B.ALLSUPS_FILE
SELF_PATH = '\\fpSup\\LOADER.BIN'

_cache = {}


def built():
    if not _cache:
        _cache['vbin'], _cache['info'] = B.loader_bin(allsups=True)
        _cache['data'], _cache['dinfo'] = FT.data_file()
    return _cache


def loader_with(ids=()):
    """LOADER.BIN with these sup_ids on its disabled list (sloader.c DS_*)."""
    v = bytearray(built()['vbin'])
    at = len(v) - (8 + 4 * B.DS_MAX)
    assert struct.unpack_from('<II', v, at) == (B.DS_MAGIC, 0)
    struct.pack_into('<II', v, at, B.DS_MAGIC, len(ids))
    for i, sid in enumerate(ids):
        v[at + 8 + 4 * i:at + 12 + 4 * i] = sid.encode()
    return bytes(v)


def disabled(blob):
    at = len(blob) - (8 + 4 * B.DS_MAX)
    magic, n = struct.unpack_from('<II', blob, at)
    assert magic == B.DS_MAGIC
    return [blob[at + 8 + 4 * i:at + 12 + 4 * i].decode() for i in range(n)]


def boot(data=True, sups=(), vbin=None, **kw):
    b = built()
    vbin = vbin or b['vbin']
    files = {'\\fpSup\\LOADER.BIN': vbin}
    ents = [('LOADER.BIN', 0x20, len(vbin)), ('UI', 0x10, 0)]
    if data:
        files[DATA_PATH] = data if isinstance(data, bytes) else b['data']
    for name, blob in sups:
        files['\\fpSup\\' + name] = blob
        ents.append((name, 0x20, len(blob)))
    cam = F6.Cam(files, {'\\fpSup': ents}, **kw)
    cam.boot()
    return cam


def log(cam):
    return [(code, a, b, name) for code, a, b, name in cam.log()]


def block(cam):
    return next(a for code, a, _b, name in cam.log() if code == 'LOADED' and name == 'LOADER.BIN')


def lines(cam):
    return [t for code, _a, _b, t in cam.log() if t.startswith('FT6')]


def tab_word(cam, i):
    return cam.w(block(cam) + 4 * i)


def soff(cam):
    """{text: offset} the string layer handed out (struct ft6_tab soff)."""
    strings = built()['dinfo']['strings']
    return {t: cam.w(block(cam) + tab_word(cam, 6) + 4 * i) for i, t in enumerate(strings)}


def card_sups():
    """A sup that loads, one that does not (bad header), one that is off, one
    entered that answered RELEASE (its claim refused: kind 9)."""
    ok = T.test_sup('TOKA', [])
    loss = T.test_sup('LOSS', [])                         # a product the table knows
    img = T.IMAGE.read_bytes()
    rel = T.test_sup('TREL', [(T.SITE_A, T.word(img, T.SITE_A), 9, 0)])
    dis = T.test_sup('DSBL', [])                          # on the disabled list (DIS_CARD)
    return [('10TEST.BIN', loss), ('20BAD.BIN', b'NOPE' * 8), ('30OLD.OFF', ok), ('40REL.BIN', rel),
            ('50DIS.BIN', dis), ('55EXTRA.BIN', T.test_sup('EXTR', []))]


KEY_OK = 1000 + 1 * 10 + 1          # written, the list found at boot (allsups.c)


def parts(cam, k):
    v = cam.vars
    return tuple(v[f'FT_{p}{k}'][1] for p in 'NGVRE')


def check_tabs(test, cam, pages, active):
    """Visible tabs cover the screen once, with one current page highlight."""
    v = cam.vars
    tabs = [k for k in range(1, 8) if v[f'FT_TabVisible{k}'][1]]
    test.assertEqual(tabs, list(range(1, pages + 1)))
    test.assertEqual([k for k in tabs if v[f'FT_TabActive{k}'][1]], [active])
    edge = 0
    for k in tabs:
        test.assertEqual(v[f'FT_TabX{k}'][1], edge)
        width = v[f'FT_TabWidth{k}'][1]
        test.assertGreater(width, 0)
        edge += width
    test.assertEqual(edge, 1024)


class AllSupsTests(unittest.TestCase):
    def test_loads_last_as_the_loader(self):
        cam = boot()
        self.assertEqual(lines(cam), ['FT6 s=00'])
        loaded = [name for code, _a, _b, name in cam.log() if code == 'LOADED']
        self.assertEqual(loaded[-1], 'LOADER.BIN')
        (image_args, image_sp, image_pack), (r, sp, pack) = cam.nbr_calls
        self.assertEqual(image_args[0], F6.APP)
        self.assertEqual(image_args[3], 0, 'image reader keeps its own filename pool')
        self.assertEqual(image_sp & 7, 0)
        self.assertEqual({r['name'] for r in FT.NBR.inspect(image_pack)['resources']},
                         {name for name, _color, _blob in LOGO.images()})
        self.assertEqual(r[0], F6.APP)
        self.assertEqual(sp & 7, 0)
        self.assertEqual(cam.machines()[0], FT.MACHINE)
        self.assertNotEqual(cam.w(F6.SITE), 0xEB000005)

    def test_normal_full_screen_vector_is_left_to_the_native_registrar(self):
        cam = boot(machine_capacity=F6.STOCK_MACHINES)
        self.assertEqual(lines(cam), ['FT6 s=00'])
        self.assertEqual(cam.w(F6.APP + 0x80), 226)
        self.assertGreaterEqual(cam.w(F6.APP + 0x84), 226)
        self.assertNotEqual(cam.w(F6.APP + 0x8C), F6.SCREENS)
        self.assertNotEqual(cam.w(F6.APP + 0x104), F6.MACHS)
        self.assertEqual(cam.machines()[0], FT.MACHINE, 'priority after native vector growth')
        self.assertEqual(len(cam.nbr_calls), 2, 'image pack and all five pages use separate readers')

    def test_every_private_field_gets_its_layer_offset(self):
        from ui import chain
        cam = boot()
        _r, _sp, pack = cam.nbr_calls[-1]
        offs = soff(cam)
        for text, off in offs.items():
            self.assertGreaterEqual(off, 0x40000000, text)
            self.assertEqual(chain.resolve(cam.w, off, F6.READER), text)
        data = built()['data']
        n_refs, refs_off = struct.unpack_from('<II', data, 28)
        strings = built()['dinfo']['strings']
        for i in range(n_refs):
            at, k = struct.unpack_from('<II', data, refs_off + 8 * i)
            self.assertEqual(struct.unpack_from('>I', pack, at)[0], offs[strings[k]])   # pack offsets
        names = [chain.name(cam.w, chain.outer(cam.w, 'resolve'))]
        self.assertEqual(names, ['LOADER'], "the layer carries the loader's name")

    def test_the_list_and_its_variables(self):
        cam = boot(sups=card_sups())
        self.assertEqual(cam.vars['FT_Key'], (0, 0))
        self.assertEqual(cam.vars['FT_Focus'], (0, 3451))
        ver = 'v' + built()['dinfo']['versions']['LOSS']
        self.assertEqual(parts(cam, 1), ('Lossless', ' ', ver, ' ', ' '))
        self.assertEqual(parts(cam, 2), (' ', 'BAD', ' ', 'Load failed', ' '))
        self.assertEqual(parts(cam, 3), (' ', 'OLD', ' ', ' ', ' '))
        self.assertEqual(parts(cam, 4), (' ', 'REL', ' ', 'Load failed', ' '))
        self.assertEqual(cam.vars['FT_PageText'][1], '1 / 2')
        self.assertEqual(len(cam.vars), 96)
        check_tabs(self, cam, 2, 1)
        self.assertEqual(cam.vars['FT_VersionX1'][1], 187, 'version follows the native Lossless name width')
        self.assertEqual(sorted(n for _o, n, _f in cam.subs),
                         sorted(['FT_Focus', 'FT_Key'] +
                                [f'FT_{kind}{k}' for kind in ('Choice', 'Selected') for k in range(1, 6)]))
        for _o, _n, fn in cam.subs:
            self.assertTrue(fn & 1, 'Thumb subscribers')

    def test_res_lab_name_and_version_come_from_filename(self):
        self.assertNotIn('RLAB', FT.PRODUCTS)
        cam = boot(sups=[('50RES-Lab v0.1.0test.BIN', T.test_sup('RLAB', []))])
        self.assertEqual(parts(cam, 1), ('RES-Lab v0.1.0test', ' ', ' ', ' ', ' '))
        cam.notify('FT_Choice1', 1)
        self.assertEqual(parts(cam, 1)[0], 'RES-Lab v0.1.0test')
        self.assertEqual(parts(cam, 1)[3], 'Unload on restart')

    def test_explicit_choices_write_only_the_selected_sup(self):
        original = loader_with(['DSBL'])
        cam = boot(sups=card_sups(), vbin=original)
        cam.notify('FT_Choice1', 1)             # Disable loaded Lossless
        first = cam.written[SELF_PATH]
        self.assertEqual(sorted(disabled(first)), ['DSBL', 'LOSS'])
        self.assertEqual(first[:-(8 + 4 * B.DS_MAX)], original[:-(8 + 4 * B.DS_MAX)])
        self.assertEqual(len(first), len(original))
        ver = 'v' + built()['dinfo']['versions']['LOSS']
        self.assertEqual(parts(cam, 1)[3], 'Unload on restart')
        self.assertEqual(parts(cam, 1)[2], ver, 'version stays beside the name during pending changes')
        self.assertEqual(cam.vars['FT_Default1'][1], 1)
        cam.notify('FT_Choice1', 1)             # Disable again stays disabled
        self.assertEqual(cam.written[SELF_PATH], first)
        cam.notify('FT_Choice1', 0)
        self.assertEqual(disabled(cam.written[SELF_PATH]), ['DSBL'])
        self.assertEqual(parts(cam, 5)[:2], (' ', 'DIS'))
        cam.notify('FT_Choice5', 0)
        self.assertEqual(disabled(cam.written[SELF_PATH]), [])
        self.assertEqual(parts(cam, 5)[4], 'Load on restart')
        cam.press(11)                          # second page, slot 1 = EXTR
        cam.notify('FT_Choice1', 1)
        self.assertEqual(disabled(cam.written[SELF_PATH]), ['EXTR'])
        cam.notify('FT_Choice1', 0)
        for slot in (2, 3, 4, 5):
            self.assertEqual(parts(cam, slot), (' ',) * 5)
            self.assertEqual(cam.vars[f'FT_Visible{slot}'][1], 0)
            self.assertEqual(cam.vars[f'FT_Lock{slot}'][1], 1)
            before = cam.written[SELF_PATH]
            cam.notify(f'FT_Choice{slot}', 1)
            self.assertEqual(cam.written[SELF_PATH], before)
        self.assertEqual(cam.renames, [])

    def test_more_settings_is_forwarded_only_while_enabled_and_loaded(self):
        from armasm import assemble
        btn = B.make_sup(assemble(HERE / 'button_sup.S'), B.SL_HEADER_LEN, 'BTNS')
        sups = card_sups() + [('60BTN.BIN', btn)]
        cam = boot(sups=sups)
        cam.press(11)                          # BTN = second page slot 2
        self.assertEqual(cam.vars['FT_Selected2'][1], 0)
        self.assertEqual(cam.vars['FT_More2'][1], 1)
        cam.notify('FT_Choice2', 2)
        self.assertEqual(cam.vars['FT_Key'][1], 2107)
        self.assertNotIn(SELF_PATH, cam.written, 'settings does not change boot configuration')
        cam.notify('FT_Choice2', 1)
        self.assertEqual(cam.vars['FT_Selected2'][1], 1)
        self.assertEqual(cam.vars['FT_More2'][1], 0)
        cam.notify('FT_Choice2', 2)             # stale/forged choice cannot run provider
        self.assertEqual(cam.vars['FT_Key'][1], 0)
        cam.notify('FT_Choice2', 0)
        cam.notify('FT_Choice2', 2)
        self.assertEqual(cam.vars['FT_Key'][1], 2207, 'loaded provider still owns the callback')
        cold = boot(sups=sups, vbin=loader_with(['BTNS']))
        cold.press(11); cold.notify('FT_Choice2', 0)
        self.assertEqual(cold.vars['FT_More2'][1], 0, 'Enable schedules next boot; no provider loaded')
        cold.notify('FT_Choice2', 2)
        self.assertEqual(cold.vars['FT_Key'][1], 0)

    def test_audio_style_settings_hint_tracks_popup_selection_and_cancel(self):
        from armasm import assemble
        btn = B.make_sup(assemble(HERE / 'button_sup.S'), B.SL_HEADER_LEN, 'BTNS')
        cam = boot(sups=card_sups() + [('60BTN.BIN', btn)])
        cam.press(11)
        cam.press(22)                           # popup slot 2, enabled selection
        self.assertEqual(cam.vars['FT_RightFooter'][1], FT.NATIVE_ENGLISH['Footer02'])
        self.assertEqual(cam.vars['FT_OK'][1], FT.NATIVE_ENGLISH['Footer05'])
        self.assertEqual(cam.vars['FT_Version'][1], ' ')
        cam.notify('FT_Selected2', 1)           # highlight Disable, without confirming
        self.assertEqual(cam.vars['FT_RightFooter'][1], ' ')
        self.assertEqual(cam.vars['FT_More2'][1], 0)
        cam.notify('FT_Choice2', 2)             # Right must not open settings from Disable
        self.assertEqual(cam.vars['FT_Key'][1], 0)
        self.assertNotIn(SELF_PATH, cam.written)
        cam.notify('FT_Selected2', 0)
        cam.notify('FT_Choice2', 2)
        self.assertEqual(cam.vars['FT_Key'][1], 2107)
        cam.press(20)                          # close/cancel popup
        self.assertEqual(cam.vars['FT_RightFooter'][1], ' ')
        self.assertIn('Loader v3', cam.vars['FT_Version'][1])
        self.assertEqual(cam.vars['FT_OK'][1], FT.NATIVE_ENGLISH['Footer01'])
        cam.notify('FT_Focus', 3451)
        self.assertIn('Page', cam.vars['FT_OK'][1])
        self.assertNotIn('Select', cam.vars['FT_OK'][1])

    def test_a_failed_write_rolls_back_the_persistent_list(self):
        cam = boot(sups=card_sups(), write_ok=False)
        cam.notify('FT_Choice1', 1)
        self.assertEqual(parts(cam, 1)[3], 'Write failed')
        self.assertEqual(parts(cam, 1)[2], 'v' + built()['dinfo']['versions']['LOSS'])
        self.assertEqual(cam.vars['FT_Default1'][1], 0)
        self.assertEqual(cam.vars['FT_Key'][1], 6)
        cam.write_ok = True
        cam.notify('FT_Choice5', 1)
        self.assertEqual(disabled(cam.written[SELF_PATH]), ['DSBL'], 'failed LOSS change was rolled back')

    def test_pagination_reaches_every_sup_including_past_seventeen(self):
        sups = [(f'{i:02}SUP.BIN', T.test_sup(f'T{i:03}', [])) for i in range(1, 33)]
        cam = boot(sups=sups)
        self.assertEqual(lines(cam), ['FT6 s=00'], 'management keeps its own slot at loader capacity')
        self.assertEqual(cam.vars['FT_PageText'][1], '1 / 7')
        cam.press(10)
        self.assertEqual(cam.vars['FT_PageText'][1], '1 / 7')
        for page in range(7):
            self.assertEqual(cam.vars['FT_PageText'][1], f'{page + 1} / 7')
            check_tabs(self, cam, 7, page + 1)
            for slot in range(1, 6):
                if page * 5 + slot > 32:
                    self.assertEqual(cam.vars[f'FT_Visible{slot}'][1], 0)
                    continue
                # Query selected file's unique sup_id through its persisted Disable.
                cam.notify(f'FT_Choice{slot}', 1)
                self.assertIn(f'T{page * 5 + slot:03}', disabled(cam.written[SELF_PATH]))
                cam.notify(f'FT_Choice{slot}', 0)
            self.assertEqual(cam.vars['FT_Focus'][1], 3451, 'paging preserves the title focus')
            cam.press(11)
        self.assertEqual(cam.vars['FT_PageText'][1], '7 / 7')
        cam.press(10)
        self.assertEqual(cam.vars['FT_PageText'][1], '6 / 7')

    def test_no_sup_and_legacy_rows_are_not_switchable(self):
        empty = boot()
        empty.press(11); empty.press(10)
        self.assertEqual(empty.vars['FT_PageText'][1], ' ')
        check_tabs(self, empty, 1, 1)
        for k in range(1, 6):
            self.assertEqual(empty.vars[f'FT_Visible{k}'][1], 0)
            empty.notify(f'FT_Choice{k}', 1)
        self.assertNotIn(SELF_PATH, empty.written)
        cam = boot(sups=card_sups())
        for k in (2, 3):
            cam.notify(f'FT_Choice{k}', 1)
        self.assertNotIn(SELF_PATH, cam.written, 'invalid header and legacy OFF are read-only')

    def test_fifth_slot_has_its_own_choice_and_selection_callbacks(self):
        from armasm import assemble
        btn = B.make_sup(assemble(HERE / 'button_sup.S'), B.SL_HEADER_LEN, 'BTNS')
        sups = [(f'{k}0BASE.BIN', T.test_sup(f'BS{k}X', [])) for k in range(1, 5)]
        cam = boot(sups=sups + [('50BTN.BIN', btn)])
        self.assertEqual(cam.vars['FT_PageText'][1], ' ', 'single-page lists hide the count')
        cam.press(25)
        self.assertEqual(cam.vars['FT_RightFooter'][1], FT.NATIVE_ENGLISH['Footer02'])
        cam.notify('FT_Selected5', 1)
        self.assertEqual(cam.vars['FT_More5'][1], 0)
        cam.notify('FT_Choice5', 2)
        self.assertEqual(cam.vars['FT_Key'][1], 0)
        cam.notify('FT_Selected5', 0)
        cam.notify('FT_Choice5', 2)
        self.assertEqual(cam.vars['FT_Key'][1], 2105)
        cam.notify('FT_Choice5', 1)
        self.assertEqual(disabled(cam.written[SELF_PATH]), ['BTNS'])
        cam.notify('FT_Choice5', 0)
        self.assertEqual(disabled(cam.written[SELF_PATH]), [])

    def test_page_ids(self):
        cam = boot()
        for name in ('FT_Y6', 'FT_LIST', 'FT_UPDATES', 'FT_CARD', 'FT_ABOUT'):
            self.assertEqual(cam.page_id(name), FT.GUI_ID)
        img = T.IMAGE.read_bytes()
        import sl_pages as SL
        for name in ('MainY5', 'MainB1'):
            self.assertEqual(cam.page_id(name), SL.gui_id(img, name), name)

    def test_no_data_file_changes_nothing(self):
        cam = boot(data=False)
        self.assertIn(('OPEN_FAIL', 0, 0, 'UI\\' + B.ALLSUPS_FILE), log(cam))
        self.assertEqual(cam.w(F6.SITE), 0xEB000005)
        self.assertEqual((cam.nbr_calls, cam.vars, cam.subs), ([], {}, []))
        self.assertEqual([c for c, *_ in cam.log()][-1], 'DONE')

    def test_bad_data_file_changes_nothing(self):
        bad = bytearray(built()['data'])
        bad[0] ^= 1
        cam = boot(data=bytes(bad))
        self.assertIn('BAD_HEADER', [c for c, *_ in cam.log()])
        self.assertEqual(cam.w(F6.SITE), 0xEB000005)

    def test_refused_registration_keeps_only_the_string_layer(self):
        cam = boot(nbr_result=1)
        self.assertEqual(lines(cam), ['FT6 s=06'])
        self.assertEqual(cam.w(F6.SITE), 0xEB000005)
        self.assertNotIn('RELEASED', [c for c, *_ in cam.log()])

    def test_site_held_exclusively_releases_the_page(self):
        img = T.IMAGE.read_bytes()
        other = T.test_sup('OTHR', [(F6.SITE, T.word(img, F6.SITE), 2, 0)])
        cam = boot(sups=[('00OTHR.BIN', other)])
        self.assertEqual(lines(cam), ['FT6 s=01'])
        self.assertIn(('RELEASED', 1, 0, 'LOADER.BIN'), log(cam))
        for site in FT.STRING_SITES:
            self.assertEqual(cam.w(site), T.word(img, site))
        self.assertEqual((cam.vars, cam.subs), ({}, []))
        self.assertEqual([c for c, *_ in cam.log()][-1], 'DONE')

    def test_power_off_puts_every_site_back(self):
        cam = boot()
        img = T.IMAGE.read_bytes()
        cam.power_off()
        for site in (F6.SITE,) + FT.STRING_SITES:
            self.assertEqual(cam.w(site), T.word(img, site), hex(site))

    def test_without_allsups_restores_the_ui_without_waiting(self):
        # Frozen releases keep their original loader. New builds intentionally
        # remove its splash hold while keeping the plain loader independent.
        vbin, _ = B.loader_bin()
        files, dirs = T.card()
        files[SELF_PATH] = vbin
        cam = T.Camera(files, dirs, stale={T.DRAW: T.DRAW_PAUSED})
        cam.boot()
        self.assertEqual(cam.slept, 0)
        self.assertNotIn('D_SLEEP', cam.calls)
        self.assertEqual(cam.w(T.DRAW), T.DRAW_STOCK)
        self.assertIn('UI_FORCE', cam.calls)
        self.assertNotIn(DATA_PATH, cam.opened)


if __name__ == '__main__':
    unittest.main()
