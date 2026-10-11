"""Bounded reads of firmware-owned geometry scalars, with no pointer chasing.

Source: out/decomp/full/blk_c01.c, C01D1630 (canvas publication),
C01D69D0 (plane dimensions) and C01D7248 (consumer surface dimensions).
The optional path flags are traced through C01CEF08 -> C01D10D0 ->
C01A5F50 -> C01A5310 -> C06297D8, and read by C06295C0.
These independent reads do not constitute an atomic frame/DMA snapshot.
The caller must already hold the camera lease and validate the running build.
"""

GROUPS = (
    ('engine_fps_word', 0xc31df574, 1),
    ('preview_geometry', 0xc31df58c, 8),
    ('plane_routes', 0xc31df8e4, 5),
    ('plane0_enabled_width_height', 0xc31e10f4, 3),
    ('plane1_enabled_width_height', 0xc31e116c, 3),
    ('consumer0_mode_type_enabled_width_height_count', 0xc30254b4, 6),
    ('consumer1_mode_type_enabled_width_height_count', 0xc3025534, 6),
    ('near60_switch_word_low_byte', 0xc2f16594, 1),
    ('matrix_bypass_current_previous', 0xc37cf6f0, 2),
)


def read_geometry(mem_get, clock, phase):
    result = {'phase': phase,
              'limitation': 'independent fixed BSS reads; no atomic snapshot or DMA completion proof',
              'groups': {}}
    for name, address, count in GROUPS:
        begin = clock.mark('geometry_read_begin', phase=phase, group=name,
                           address=hex(address), count=count)
        words = mem_get(address, count, tries=1)
        assert len(words) == count and all(isinstance(w, int) for w in words)
        end = clock.mark('geometry_read_end', phase=phase, group=name,
                         begin_sequence=begin['sequence'], words=words)
        result['groups'][name] = {'address': hex(address), 'words': words,
                                  'begin_sequence': begin['sequence'],
                                  'end_sequence': end['sequence']}
    return result
