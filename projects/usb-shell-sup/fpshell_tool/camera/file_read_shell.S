/* RETIRED — do not restore or assemble this template.
 *
 * The former implementation placed an arbitrary byte count at SCRATCH
 * 0xC072FD80 even though only 0x280 bytes remained before 0xC0730000.  It also
 * passed NULL instead of read()'s actual-count pointer, had no 64-bit seek,
 * and could not stream or recover an allocation after a failed host transfer.
 * Large files therefore overwrote adjacent injected code/state.
 *
 * Use the maintained bounded reader instead:
 *
 *   ../../fpsup_repo/fp_usb_shell/getfile.py
 *   ../../fpsup_repo/fp_usb_shell/templates/getfile_init.S
 *   ../../fpsup_repo/fp_usb_shell/templates/getfile_guard.S
 *   ../../fpsup_repo/fp_usb_shell/templates/getfile.S
 *   ../../fpsup_repo/fp_usb_shell/templates/getfile_free.S
 *
 * It reads at most one MiB per chunk, validates session/request/64-bit offset
 * on the raw USB path, streams directly to a temporary host file, frees the
 * camera buffer on ordinary exits, and guardedly recovers it on the next run
 * if the host process was killed.
 */

.error "file_read_shell.S is unsafe and retired; use fp_usb_shell/getfile.py"
