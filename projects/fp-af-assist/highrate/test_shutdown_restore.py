"""Tests for the loader-journal verdict. No Unicorn, no camera, no card written.

The subject is the maintained mechanism: stage2 journals every firmware word a
card changes and its one power-off callback writes them back, so a run-time hook
site is covered by declaring it as a four-byte section. These tests build VBIN
images and emulated journal blocks and check what the verdict says about them.
"""
from pathlib import Path
import struct
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import af_batch as fmt
import hook_site_section as sites
import shutdown_restore as check

BLOCK = 0xC0810000          # a journal block, as the allocator would place it
JOURNAL_CODE = 0x40         # bytes of lh_unhook copied in front of the journal


def vbin(*sections, entry=0):
    """A VBIN image: header, {destination, length} table, then the data."""
    table, data = b'', b''
    for dest, payload in sections:
        table += struct.pack('<II', dest, len(payload))
        data += payload + bytes(-len(payload) % 4)
    return b'VBIN' + struct.pack('<III', len(sections), entry, len(data)) + table + data


def site_section(word=fmt.ORIGINAL_WORD):
    return (fmt.CALLSITE, struct.pack('<I', word))


class Memory:
    """A word store with the same bounded-read contract as the live transport."""

    def __init__(self):
        self.words = {}
        self.reads = []

    def put(self, address, *values):
        for index, value in enumerate(values):
            self.words[address + index * 4] = value

    def read(self, address, count=1):
        if address & 3 or not 1 <= count <= 4096:
            raise ValueError('invalid bounded read')
        self.reads.append((address, count))
        return [self.words.get(address + index * 4, 0) for index in range(count)]

    def journal(self, entries, *, block=BLOCK, code=JOURNAL_CODE, lists=('ordinary', 'forced')):
        """Lay out a loader journal block and register it where asked."""
        self.put(block, block - 8, block + 12, block + 12 + code)
        at = block + 12 + code
        for address, words in entries:
            self.put(at, address, len(words) * 4, *words)
            at += 8 + len(words) * 4
        self.put(at, 0)
        for name in lists:
            base = check.ORDINARY_LIST if name == 'ordinary' else check.FORCED_LIST
            slot = next(index for index in range(check.LIST_SLOTS)
                        if not self.words.get(base + index * 4))
            self.put(base + slot * 4, block)
        return block

    def stock_journal(self):
        return self.journal([(fmt.CALLSITE, [fmt.ORIGINAL_WORD]),
                             (0xC03DA420, [0xEB0000CC])])


class CardTests(unittest.TestCase):
    def test_sections_are_read_with_their_data(self):
        image = vbin((0xC03DA420, b'\x01\x02\x03\x04'), site_section(),
                     (0x1000, b'\xaa' * 6))
        sections = check.vbin_sections(image)
        self.assertEqual([(dest, padded) for dest, padded, _ in sections],
                         [(0xC03DA420, 4), (fmt.CALLSITE, 4), (0x1000, 8)])
        self.assertEqual(sections[2][2], b'\xaa' * 6)      # data, not the padding

    def test_only_firmware_words_outside_the_cave_are_journaled(self):
        image = vbin((0xC03DA420, bytes(4)), (0xC072E100, bytes(8)), (0x2000, bytes(4)))
        self.assertEqual(check.journaled_sections(image), [(0xC03DA420, 4)])

    def test_the_site_is_declared_with_the_stock_word(self):
        found = check.declares_hook_site(vbin(site_section()), fmt.CALLSITE,
                                         fmt.ORIGINAL_WORD)
        self.assertTrue(found['declared'] and found['exact'] and found['matches'])

    def test_a_declared_site_holding_the_wrong_word_is_not_a_match(self):
        found = check.declares_hook_site(vbin(site_section(0xEA000000)),
                                         fmt.CALLSITE, fmt.ORIGINAL_WORD)
        self.assertTrue(found['declared'])
        self.assertFalse(found['matches'])

    def test_a_longer_section_covering_the_site_still_counts(self):
        payload = struct.pack('<3I', 0, fmt.ORIGINAL_WORD, 0)
        found = check.declares_hook_site(vbin((fmt.CALLSITE - 4, payload)),
                                         fmt.CALLSITE, fmt.ORIGINAL_WORD)
        self.assertTrue(found['declared'] and found['matches'])
        self.assertFalse(found['exact'])

    def test_an_undeclared_site_is_reported_as_such(self):
        found = check.declares_hook_site(vbin((0xC03DA420, bytes(4))),
                                         fmt.CALLSITE, fmt.ORIGINAL_WORD)
        self.assertFalse(found['declared'] or found['matches'])

    def test_implausible_images_are_refused(self):
        for bad in (b'', b'VBIN', b'NOPE' + struct.pack('<III', 1, 0, 0),
                    b'VBIN' + struct.pack('<III', 0, 0, 0),
                    b'VBIN' + struct.pack('<III', 65, 0, 0),
                    b'VBIN' + struct.pack('<III', 1, 0, 0) + struct.pack('<II', 0xC0000000, 64)):
            with self.subTest(bad=bad[:8]):
                with self.assertRaises(check.ShutdownRestoreError):
                    check.vbin_sections(bad)


class ListTests(unittest.TestCase):
    def test_the_lists_are_where_poff_add_puts_them(self):
        self.assertEqual(check.ORDINARY_LIST, check.MANAGER + 0x0C)
        self.assertEqual(check.FORCED_LIST, check.MANAGER + 0x34)

    def test_the_prefix_stops_at_the_first_zero(self):
        memory = Memory()
        memory.put(check.ORDINARY_LIST, 0x11, 0x22, 0, 0x44)
        lists = check.read_lists(memory.read)
        self.assertEqual(lists['ordinary']['objects'], [0x11, 0x22])
        self.assertTrue(lists['ordinary']['trailing_nonzero'])
        self.assertEqual(lists['forced']['free'], check.LIST_SLOTS)

    def test_reads_are_bounded(self):
        memory = Memory()
        check.read_lists(memory.read)
        self.assertEqual(memory.reads, [(check.ORDINARY_LIST, 10),
                                        (check.FORCED_LIST, 10)])


class JournalTests(unittest.TestCase):
    def test_a_stock_journal_yields_the_site_word(self):
        memory = Memory()
        memory.stock_journal()
        verdict = check.require_site(memory.read, fmt.CALLSITE, fmt.ORIGINAL_WORD)
        self.assertTrue(verdict['complete'] and verdict['journalled'])
        self.assertEqual(verdict['recorded_word'], fmt.ORIGINAL_WORD)
        self.assertEqual(verdict['journal']['block'], BLOCK)
        self.assertFalse(verdict['quiescence_proven'] or verdict['covers_battery_pull'])

    def test_a_site_that_is_not_journaled_is_refused(self):
        memory = Memory()
        memory.journal([(0xC03DA420, [0xEB0000CC])])
        with self.assertRaises(check.ShutdownRestoreError) as caught:
            check.require_site(memory.read, fmt.CALLSITE, fmt.ORIGINAL_WORD)
        self.assertIn('four-byte section', str(caught.exception))

    def test_a_journal_holding_a_patched_word_is_refused(self):
        # The known open case: a power-off callback that never ran leaves a
        # patched word, and the next load journals it as if it were stock.
        memory = Memory()
        memory.journal([(fmt.CALLSITE, [0xEA001234])])
        with self.assertRaises(check.ShutdownRestoreError) as caught:
            check.require_site(memory.read, fmt.CALLSITE, fmt.ORIGINAL_WORD)
        self.assertIn('not the stock', str(caught.exception))

    def test_a_block_in_only_one_list_is_not_accepted(self):
        for lists in (('ordinary',), ('forced',)):
            with self.subTest(lists=lists):
                memory = Memory()
                memory.journal([(fmt.CALLSITE, [fmt.ORIGINAL_WORD])], lists=lists)
                with self.assertRaises(check.ShutdownRestoreError) as caught:
                    check.require_site(memory.read, fmt.CALLSITE, fmt.ORIGINAL_WORD)
                self.assertIn('both power-off lists', str(caught.exception))

    def test_other_objects_in_the_lists_are_ignored(self):
        memory = Memory()
        for index, value in enumerate((0xC3000100, 0xC3000200)):
            memory.put(check.ORDINARY_LIST + index * 4, value)
        memory.put(check.FORCED_LIST, 0xC3000300)
        memory.stock_journal()
        verdict = check.require_site(memory.read, fmt.CALLSITE, fmt.ORIGINAL_WORD)
        self.assertEqual(verdict['journal']['block'], BLOCK)
        self.assertEqual(verdict['lists']['ordinary']['free'], check.LIST_SLOTS - 3)

    def test_a_block_whose_header_does_not_fit_the_layout_is_not_a_journal(self):
        for offset, value in ((0, BLOCK), (4, BLOCK + 16), (8, BLOCK)):
            with self.subTest(offset=offset):
                memory = Memory()
                memory.stock_journal()
                memory.put(BLOCK + offset, value)
                with self.assertRaises(check.ShutdownRestoreError):
                    check.require_site(memory.read, fmt.CALLSITE, fmt.ORIGINAL_WORD)

    def test_an_entry_in_the_cave_or_the_pool_is_not_a_journal(self):
        # The loader never journals those, so a block that claims to is not the
        # loader's -- even when it also carries the word we are looking for.
        for address in (0xC072E100, 0x1000):
            with self.subTest(address=hex(address)):
                memory = Memory()
                memory.journal([(fmt.CALLSITE, [fmt.ORIGINAL_WORD]), (address, [0])])
                with self.assertRaises(check.ShutdownRestoreError) as caught:
                    check.require_site(memory.read, fmt.CALLSITE, fmt.ORIGINAL_WORD)
                self.assertIn('both power-off lists', str(caught.exception))

    def test_the_walk_stops_at_its_bound(self):
        memory = Memory()
        entries = [(0xC03DA420 + index * 8, [0]) for index in range(check.MAX_ENTRIES + 1)]
        block = memory.journal(entries)
        start = memory.read(block + 8)[0]
        with self.assertRaises(check.ShutdownRestoreError) as caught:
            check._walk_journal(memory.read, start)
        self.assertIn('walk bound', str(caught.exception))
        # And the block as a whole is then refused, not silently truncated.
        with self.assertRaises(check.ShutdownRestoreError):
            check.require_site(memory.read, fmt.CALLSITE, fmt.ORIGINAL_WORD)

    def test_the_card_is_cross_checked_when_it_is_supplied(self):
        memory = Memory()
        memory.stock_journal()
        verdict = check.verify_site(memory.read, fmt.CALLSITE, fmt.ORIGINAL_WORD,
                                    vbin=vbin(site_section()))
        self.assertTrue(verdict['card']['declared'] and verdict['card']['exact'])
        verdict = check.verify_site(memory.read, fmt.CALLSITE, fmt.ORIGINAL_WORD,
                                    vbin=vbin((0xC03DA420, bytes(4))))
        # The journal is what decides; the card only explains why it is there.
        self.assertTrue(verdict['complete'])
        self.assertFalse(verdict['card']['declared'])


class SectionToolTests(unittest.TestCase):
    def test_the_word_comes_from_the_rom(self):
        self.assertEqual(sites.stock_word(fmt.CALLSITE), fmt.ORIGINAL_WORD)
        self.assertEqual(sites.section(fmt.CALLSITE),
                         struct.pack('<I', fmt.ORIGINAL_WORD))

    def test_a_wrong_image_is_refused(self):
        with self.assertRaises(ValueError):
            sites.stock_word(fmt.CALLSITE, rom=b'\0' * 64)

    def test_misaligned_or_outside_addresses_are_refused(self):
        for address in (fmt.CALLSITE + 1, 0xBFFFFFFC, 0xD0000000):
            with self.subTest(address=hex(address)):
                with self.assertRaises(ValueError):
                    sites.stock_word(address)

    def test_check_card_accepts_only_the_stock_word(self):
        self.assertTrue(check_all(vbin(site_section()))['all_declared'])
        self.assertFalse(check_all(vbin(site_section(0xEA000000)))['all_declared'])
        self.assertFalse(check_all(vbin((0xC03DA420, bytes(4))))['all_declared'])


def check_all(image):
    return sites.check_card(image)


if __name__ == '__main__':
    unittest.main(verbosity=2)
