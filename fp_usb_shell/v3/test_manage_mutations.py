"""Bounded mutations of isolated source copies; shared source is never edited."""
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from . import test_allsups as A


class ManagementMutationTests(unittest.TestCase):
    def test_behavior_assertions_reject_broken_variants(self):
        A.built()
        source = (A.HERE / 'allsups.c').read_text()
        mutations = (
            ('wrong page row', 't->page * FT6_VISIBLE + k - 1u', 'k - 1u',
             'test_explicit_choices_write_only_the_selected_sup'),
            ('failed write left in RAM', 'if (ok != 1u) copy(d, was, DS_BYTES);',
             'if (ok != 1u) {}', 'test_a_failed_write_rolls_back_the_persistent_list'),
            ('disabled provider exposed', 'r && r->bin && r->boot == BOOT_ON',
             'r && r->boot == BOOT_ON', 'test_more_settings_is_forwarded_only_while_enabled_and_loaded'),
            ('normal vector growth refused', 'rd32(app + APP_SCREENS_N) > rd32(app + APP_SCREENS_CAP)',
             'rd32(app + APP_SCREENS_N) + FT6_PAGES > rd32(app + APP_SCREENS_CAP)',
             'test_normal_full_screen_vector_is_left_to_the_native_registrar'),
            ('Disable selection opens settings', 'choice == 2u && t->selected[k - 1u] == 0u && ft6_more(t, r)',
             'choice == 2u && ft6_more(t, r)', 'test_audio_style_settings_hint_tracks_popup_selection_and_cancel'),
            ('fifth choice targets fourth slot', ': (uintptr_t)&allsups_choice5;',
             ': (uintptr_t)&allsups_choice4;', 'test_fifth_slot_has_its_own_choice_and_selection_callbacks'),
        )
        original_unity = A.B.allsups_unity
        for name, before, after, method in mutations:
            with self.subTest(mutation=name), tempfile.TemporaryDirectory(prefix='ft6-mutation-') as tmp:
                self.assertEqual(source.count(before), 1)
                mutant = pathlib.Path(tmp) / 'allsups.c'
                mutant.write_text(source.replace(before, after))
                def unity(directory):
                    path = original_unity(directory)
                    path.write_text(path.read_text().replace(str(A.HERE / 'allsups.c'), str(mutant)))
                    return path
                with patch.object(A.B, 'allsups_unity', unity):
                    vbin, _info = A.B.loader_bin(allsups=True)
                result = unittest.TestResult()
                with patch.dict(A._cache, {'vbin': vbin}):
                    A.AllSupsTests(method).run(result)
                self.assertFalse(result.errors, result.errors)
                self.assertEqual(len(result.failures), 1, 'mutation must break a behavior assertion')
                print('detected:', name)


if __name__ == '__main__':
    unittest.main()
