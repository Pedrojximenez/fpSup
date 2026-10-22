#!/usr/bin/env python3
"""Decide, from read-only evidence, whether the loader will put a word back.

Since 2026-09-25 the shared loader owns power-off restoration: stage2 registers
ONE callback in both of `XC_PowerOffMgr`'s lists before it places anything,
copies every firmware word outside the cave into a journal first, and the
callback writes the journal back. A sup that arms a hook at run time declares the
site as a four-byte section holding the firmware's own word, so the journal has
it; **a sup does not register a power-off routine of its own**
(fpSup/HOOKS_AT_POWER_OFF.md, gyro's `hook_sites()`).

So this module verifies the maintained mechanism instead of adding another one:

* the card's VBIN section table, to see the site declared with the stock word;
* the manager's two lists, read from the camera, to find the loader's journal
  block and walk it.

`POFF_ADD` (C0024118) fills the first free of ten slots at mgr+0x0C (ordinary)
and mgr+0x34 (forced). The firmware itself fills 8 of the ordinary list and 1 of
the forced one, so there is very little room left -- another reason not to spend
a slot. Nothing here writes, registers or installs. A verdict is about the words
it names in the boot it was taken in; it is not a hook-quiescence proof.
"""
from __future__ import annotations

import struct

MANAGER = 0xC30756C4
ORDINARY_LIST = MANAGER + 0x0C
FORCED_LIST = MANAGER + 0x34
LIST_SLOTS = 10
CAVE_LO, CAVE_HI = 0xC072D000, 0xC0735000
POOL_BELOW = 0x40000000
FIRMWARE_BASE = 0xC0000000
# Bounds on the walk: the journal is sized from the card's section table, and a
# card that needed more than this would not fit the loader's block either.
MAX_ENTRIES = 64
MAX_ENTRY_BYTES = 4096
MAX_JOURNAL_WORDS = 4096
READ_CHUNK = 64


class ShutdownRestoreError(Exception):
    """The evidence does not support a power-off restore of the named word."""


# --- the card ---------------------------------------------------------------

def vbin_sections(vbin):
    """Every section as (destination, padded length, data), in table order.

    Layout, from asm/stage2.S: "VBIN", count, entry, data bytes, then the
    {destination, length} table, then the data -- each section starting on a word.
    """
    if len(vbin) < 16 or vbin[:4] != b'VBIN':
        raise ShutdownRestoreError('not a VBIN image')
    count = struct.unpack_from('<I', vbin, 4)[0]
    if not 0 < count <= 64 or 16 + 8 * count > len(vbin):
        raise ShutdownRestoreError('implausible section count')
    out, cursor = [], 16 + 8 * count
    for index in range(count):
        dest, length = struct.unpack_from('<II', vbin, 16 + 8 * index)
        padded = (length + 3) & ~3
        if cursor + padded > len(vbin):
            raise ShutdownRestoreError(f'section {index} runs past the image')
        out.append((dest, padded, vbin[cursor:cursor + length]))
        cursor += padded
    return out


def journaled_sections(vbin):
    """The sections the loader journals: at or above 0x40000000, outside the cave."""
    return [(dest, padded) for dest, padded, _ in vbin_sections(vbin)
            if dest >= POOL_BELOW and not CAVE_LO <= dest < CAVE_HI]


def journal_covers(vbin, address):
    return any(dest <= address < dest + length
               for dest, length in journaled_sections(vbin))


def declares_hook_site(vbin, address, word):
    """Is the site declared as its own four-byte section holding the stock word?

    That is what puts a run-time hook site into the journal. A longer section
    covering the address also journals it, so it counts, but its own word must
    still be the stock one.
    """
    for dest, _padded, data in vbin_sections(vbin):
        if dest <= address and address + 4 <= dest + len(data):
            offset = address - dest
            found = struct.unpack_from('<I', data, offset)[0]
            return dict(declared=True, exact=(dest == address and len(data) == 4),
                        word=found, matches=found == word,
                        section=dict(destination=dest, bytes=len(data)))
    return dict(declared=False, exact=False, word=None, matches=False, section=None)


# --- the camera -------------------------------------------------------------

def read_lists(read):
    """Both power-off lists, as the manager will walk them."""
    out = {}
    for name, at in (('ordinary', ORDINARY_LIST), ('forced', FORCED_LIST)):
        words = read(at, LIST_SLOTS)
        if len(words) != LIST_SLOTS:
            raise ShutdownRestoreError(f'{name} list read short')
        prefix = []
        for value in words:
            if not value:
                break
            prefix.append(value)
        out[name] = dict(address=at, slots=LIST_SLOTS, objects=prefix,
                         free=LIST_SLOTS - len(prefix), raw=list(words),
                         trailing_nonzero=any(words[len(prefix) + 1:]))
    return out


def _walk_journal(read, start):
    """{ address, bytes, original words }..., terminated by a zero address."""
    entries, at, words = [], start, 0
    for _ in range(MAX_ENTRIES + 1):
        address = read(at)[0]
        if not address:
            return entries
        if len(entries) == MAX_ENTRIES:
            raise ShutdownRestoreError('journal exceeds the walk bound')
        length = read(at + 4)[0]
        if (address & 3 or address < POOL_BELOW or CAVE_LO <= address < CAVE_HI
                or not 0 < length <= MAX_ENTRY_BYTES or length % 4):
            raise ShutdownRestoreError(f'implausible journal entry at {at:08X}')
        words += length // 4
        if words > MAX_JOURNAL_WORDS:
            raise ShutdownRestoreError('journal exceeds the word bound')
        original = []
        for offset in range(0, length // 4, READ_CHUNK):
            take = min(READ_CHUNK, length // 4 - offset)
            original += read(at + 8 + offset * 4, take)
        entries.append(dict(address=address, bytes=length, words=original))
        at += 8 + length
    raise ShutdownRestoreError('unreachable')


def decode_journal_block(read, obj):
    """Decode one power-off object as the loader's journal block, or return None.

    Layout, from stage2.S `lh_setup`: X+0 is X-8 so that the manager's
    [vtbl+0xC] lands on X+4, X+4 is the routine copied to X+12, and X+8 points at
    the journal that follows it. Anything that does not fit is somebody else's
    object, which is the normal case for the firmware's own eight.
    """
    if obj & 3 or obj < FIRMWARE_BASE:
        return None
    try:
        vtable, routine, journal = read(obj, 3)
    except Exception:
        return None
    if vtable != (obj - 8) & 0xffffffff or routine != obj + 12 or not journal > routine:
        return None
    if journal - routine > MAX_JOURNAL_WORDS * 4:
        return None
    try:
        entries = _walk_journal(read, journal)
    except (ShutdownRestoreError, Exception):
        return None
    return dict(block=obj, routine=routine, journal=journal, entries=entries,
                routine_bytes=journal - routine)


def find_journal(read, *, lists=None):
    """The loader's journal block, which must be registered in BOTH lists."""
    lists = read_lists(read) if lists is None else lists
    found = {}
    for name in ('ordinary', 'forced'):
        for obj in lists[name]['objects']:
            block = decode_journal_block(read, obj)
            if block:
                found.setdefault(obj, dict(block=block, lists=set()))
                found[obj]['lists'].add(name)
    both = [v for v in found.values() if v['lists'] == {'ordinary', 'forced'}]
    if not both:
        raise ShutdownRestoreError(
            'no loader journal block registered in both power-off lists; '
            f'candidates={sorted(hex(k) for k in found)}')
    if len(both) > 1:
        raise ShutdownRestoreError('more than one journal block; ambiguous owner')
    return both[0]['block'], lists


def journal_word(block, address):
    """The original word the journal holds for `address`, or None."""
    for entry in block['entries']:
        if entry['address'] <= address < entry['address'] + entry['bytes']:
            return entry['words'][(address - entry['address']) // 4]
    return None


def verify_site(read, address, stock_word, *, vbin=None, lists=None):
    """A verdict on one word: will the loader put it back at power-off?"""
    block, lists = find_journal(read, lists=lists)
    recorded = journal_word(block, address)
    card = declares_hook_site(vbin, address, stock_word) if vbin is not None else None
    return dict(schema='fp.af-shutdown-restore/v2', address=address,
                stock_word=stock_word, journalled=recorded is not None,
                recorded_word=recorded, matches=recorded == stock_word,
                complete=recorded == stock_word,
                journal=dict(block=block['block'], journal=block['journal'],
                             entries=[dict(address=e['address'], bytes=e['bytes'])
                                      for e in block['entries']]),
                lists=lists, card=card, mechanism='shared loader journal',
                # The journal restores words. It says nothing about whether a
                # suspended hook body has exited, nor about a battery pull, for
                # which no callback runs at all.
                quiescence_proven=False, covers_battery_pull=False)


def require_site(read, address, stock_word, *, vbin=None, lists=None):
    verdict = verify_site(read, address, stock_word, vbin=vbin, lists=lists)
    if not verdict['journalled']:
        raise ShutdownRestoreError(
            f'{address:08X} is not in the loader journal: declare it as a '
            'four-byte section holding the stock word and cold boot that card')
    if not verdict['matches']:
        raise ShutdownRestoreError(
            f'{address:08X} is journalled as {verdict["recorded_word"]:08X}, '
            f'not the stock {stock_word:08X}; a missed power-off may have left '
            'a patched word that the next load recorded as if it were stock')
    return verdict
