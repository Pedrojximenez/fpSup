"""Four-box boot artwork and AutoRun commands (offline only).

The two small alpha masks are rendered logo artwork, not a bundled font.
The builder needs only Python's standard library. The actual camera format is
little-endian ARGB4444; all five frames have a transparent background.
See research/display/notes/{BOOT_BANNER,SPLASH_BAND}.md for measured formats.
"""
import base64
import struct
import zlib

SCREEN_WIDTH = 1024
# osdfile starts at (0,0): retain transparent leading pixels but omit everything
# past the artwork's right/bottom edge. Each call reads only one 71.75 KiB frame.
WIDTH, HEIGHT = 656, 56
FRAME_BYTES = WIDTH * HEIGHT * 2
ASSET_NAME = 'FPSUPUI'
DRAW = 0xC0528700
DRAW_ORIGINAL = 0xE92D4BF0
DRAW_PAUSED = 0xE12FFF1E
ECHO_SLOT, ECHO_ORIGINAL = 0xC0BAC2F8, 0xC03D99A0
DCACHE, ICACHE = 0xC000E91C, 0xC000EABC
HOLD_MS = 2000
# User reference: white fp and Sup pink sampled near #E03959.
# Native 4-bit channels quantize the pink to #DD3355.
WHITE, PINK, OUTLINE, FILL = 0xFFFFFF, 0xDD3355, 0x666666, 0xEEEEEE
# Helvetica Neue Bold Italic, rendered on the host with a shared baseline.
# Masks are cropped to their 4-bit-alpha ink bounds; fp includes a 1px separator.
MASK_HEIGHT = 36
FP_WIDTH = 37
FP_MASK = (
    'c-nPTTS!$=5S_ix_VzM}^!gE(%v&OTWChVjNm7s>6+JQRMNoZ7^ilNsD~ukWg+x&|jUs}qp9(37B9ls@mtl(Zppw'
    'AKit6e)XYW1D?4y!)@BEyz_gOQuX3fk2V3PoIwjMlIv$Jvn2*_*_%I=5gYzjMMG7lCJ#Dsp@f0`u>2r>RWhG;p^1'
    'yGqm3br|nX>Pc-gu-TFblYlc`zuBykaDO7FGm&pKpWz97(Gf!q1Xg?5q~vQMj0B)w|-a{fZQp`xT}hC9jZI~kU$o'
    '1rp~1jkbgRrI#V|ns;+<X!*5S&5{xRuf6UK=3iq<`(%@Ck3PP>4p)u}geRB(7Z`c=vZyK>*qt@00s22bn3HpKv6Q'
    'qMf01e2x@<sFvv3(50laqI&rsKxKqQYEIUHrx1+v?KfvU}0{2Cn2dh8F)6xT>ZFtSUZ;I{|N#yS7(Ac=8cygD)hR'
    'f;Ak~e8`6!DPvGd-WJ<Qki73K<#{eu!BHZiaUJADO?`#NVmEy%BXEe@xw8_QIBLg$&JylWHUcTw;krAY-~w_#bJQ'
    'aPqadJ#L7jBGz`T1W(v^hS)>?y0qfrnLdq)KEF7>(%jm8%4mVzzpU`nFtlu$xiX*>at=;I8voI$}U2K}BCffQ6bC'
    'ToG3WeB~QK>}KtLr~;E!V}N=_=Pmv&uBZ7?ghkulB33@f)o%j3Z&^{Jvm(EqPxcu#Dj9~gT|(4rWU7ZUbUSC5bI>'
    '#w>W`<UEEcxv98z?iG4nW4e%s6Pw!{mhnbQGm(gvXM!%!|7dp(daWv^wCNzOv<)rjpvn<VzG3}s6YkZa99B14xO{'
    'G@}MLtJ8P~1a^Amlx~oaYL?*!JROTcdKkm-A#`6(sAwvS;s&WiWE-71XelVKLq3mshTyM-wK+umxhDMpmOM2jsvO'
    '%m21nz?hG$Mgw<OcuIL9)3VR7JXm|O{W2m-n+RfXQMO-31gd4;KMS({>ITP9V{0bNUueb=)B'
)
SUP_WIDTH = 72
SUP_MASK = (
    'c-o~_eN2{B6hHSq&-<d_atkM-HAn|$)1aLF!HoRKGz)dfSAwnnY%R;OY-F=GT_~)%HLDG16=t(Y!U#WD+4=`oEt&'
    '`cX?|?batYQ@c;Dx__jJyAo)^mg5xk7|y<g{d&i$R=J@*BmrWCkq_O<;Uv)3+sy)zfUfyp!t@Kgtmwb4UalLAt3Y'
    'YU?F4K-_xk2tuBu_p?nr?q3;AOoO$dN{mj;y@0(gE0c20}b?Fm5zsPj-D_%^L^i<#UD1!OG(ZsILSahK72zIDXmr'
    '5bzwXC_wk#gaH*LFo~@w;&@Q)dr;>q$8TOpORWRqk$An{W86;_?R1_9^#`?A$)D5ILIb&`b1TxXkg3NH1>jYAoc8'
    'U2u=Tbnc>uT!iYSS4~!Sr|Er(qEpsoiz8HFfLYk<TuS`a>O+84RSMiEw<}N~e&+>YV$i<!Hh=C~}(4I1bz|;(8h)'
    'Fh_c&dlQ1YTu93<?6V$P6WbbL5O+LJO8w-;M!n-A0T;G-Bc2yuNI0uaEbjez7-Ph%Z%rKS3U;)D_~F*MV@WcbM;v'
    'OJf=C}ma<P{gr)~AbKK7>&P6ZnnHi?Ha=^;a{j<bF&lXS6p+akGcV)-C#^08QOK%Zibwt{xxFymOfwEf;Y9{MVf$'
    '!5k$@8<Z>NLc>2r69Qq1cCknK9`2uu5oaCD4fU{vNhP3C8uv-cJ1eqv6-JT0Oi~GjP+$|z-$A02G1u2gEbOd5#eM'
    'LA=V7v1yQXdkU3(l#qLlDD?b?`080#5f@)9JTuS=*B+VhsuQEN}e2BtE$?xkB2`+gXg@Xg3ya8r!u0O|7(SM9K5z'
    '+JFe3Capnj6tK_*;~$D;e?1OclsjH8M`W6G&eqp1f@T5YuK%e==Eb5WnkKWD25ZIJhH>-%1o<V^|P09Ali`akYq^'
    'GnyF4;$ldGUF<hDH=sG&<KT8uI4J|%dqKIOT_^d)lP^_QRafs8$%1lR&>h0(qhxTDPtxb|lB-H+($I7ia*0+S*9P'
    '@K!<?%unYYi11Tzz5E2^sa_S+4hQu<j5hh)D42ROLVOu~7RP%P#JIIh|x4oZ%AG5TAsA|VcZNH`Yr0q!Bc9=^gfJ'
    '9_rtlxqBiuhD)f4=YuG1K%+{m($)9GMmGi;zH&i%VBsHKpEE|EOVk%h3Hc7fP#}eQ};!32`ULnWK<6ikaL26Z$=P'
    'LUN;RqY@uBhQr@a%dIw6`ewn6I2g$<N-YK%MWXLdEi^2V#w;24Rep^}jYbUtCQa17^T@{vZkzbjc{n#<Nm2?=wS;'
    '~&d=IGr~NPFfAjpA5KWG$z=706GTVRA`^E|exFP4GphO(&c!L3JRmf9)DXf$6$M6I;*HB)wgpG{c}(T=QVouv}cv'
    '+EMKJz{EY%p-40zapHQLaYVx6{e2=a2MW5xo$vYLxu-}(AP(3Aeg1fRBd;8w^aSPOi`3J!7WWvdDGkCxKjra;^T8'
    'SH#m4ffV~T&`G|zb*&qblN^VH9s<s{CaeC&eMw+49euM-;~p*<GD)U5pV#f7UDq`>%(1gg+E>x<Xksm6AWm5&0No'
    '1Rx#n4g}gdU8da@i)(L)W2TZ@QF*jV2ScUx=xsA=emc{p_}h$b^Yvr=fd*Q#m*EPs7d|6q4IH-b#ZW#Kaj>>P%0m'
    '!pXb57DI6Dy<aRH;$#`7Y!!!@g`2XYo4=>TW*#'
)


def asset():
    """Return empty→four-filled frames with no host font/library dependency."""
    base = [0] * (WIDTH * HEIGHT)
    logo_width = FP_WIDTH + SUP_WIDTH
    box_size, gap, logo_gap = 24, 10, 10
    total = logo_width + logo_gap + 4 * box_size + 3 * gap
    left = (SCREEN_WIDTH - total) // 2
    assert left + total <= WIDTH

    def logo(encoded, width, x, color):
        alpha = zlib.decompress(base64.b85decode(encoded))
        assert len(alpha) == width * MASK_HEIGHT
        rgb = [(color >> shift) & 255 for shift in (16, 8, 0)]
        for y in range(min(MASK_HEIGHT, HEIGHT - 10)):
            for dx in range(width):
                a = alpha[y * width + dx]
                alpha4 = (a + 8) // 17
                r, g, b = [(c + 8) // 17 for c in rgb]
                base[(y + 10) * WIDTH + x + dx] = ((alpha4 << 12) | (r << 8) |
                                                              (g << 4) | b) if alpha4 else 0

    logo(FP_MASK, FP_WIDTH, left, WHITE)
    logo(SUP_MASK, SUP_WIDTH, left + FP_WIDTH, PINK)
    # Align the square outlines with the visible logo, not its padded mask.
    # Integer placement of an even-sized square is within half a pixel of the
    # odd-height glyph bounds; this avoids the former 3.5px downward offset.
    ink_rows = [i // WIDTH for i, pixel in enumerate(base) if pixel >> 12]
    boxes_y = (min(ink_rows) + max(ink_rows) + 1 - box_size) // 2
    boxes_x = left + logo_width + logo_gap
    frames = []
    for filled in range(5):
        pixels = base.copy()
        for box in range(4):
            x0, y0 = boxes_x + box * (box_size + gap), boxes_y
            # Crisp small squares: 2px outline, a 3px breathing space before fill.
            for y in range(box_size):
                for x in range(box_size):
                    border = x < 2 or x >= box_size-2 or y < 2 or y >= box_size-2
                    inside = 5 <= x < box_size-5 and 5 <= y < box_size-5
                    if border or (box < filled and inside):
                        pixels[(y0+y)*WIDTH+x0+x] = 0xF666 if border else 0xFEEE
        frames.append(struct.pack('<' + 'H' * len(pixels), *pixels))
    result = b''.join(frames)
    assert len(result) == 5 * FRAME_BYTES
    return result


def publish(out):
    # No freshly injected helper may bootstrap its own instruction cache.
    for address in (DCACHE, ICACHE):
        out.extend((f'mem set 0x{ECHO_SLOT:08X} 0x{address:08X}', 'echo'))


def restore_echo(out):
    out.extend([f'mem set 0x{ECHO_SLOT:08X} 0x{ECHO_ORIGINAL:08X}'] * 3)


class FourBoxBar:
    def __init__(self):
        self.frame = -1

    def start(self, out):
        out.append('# --- four-box UI: pause native redraw, publish the code patch ---')
        out.append(f'mem set 0x{DRAW:08X} 0x{DRAW_PAUSED:08X}')
        publish(out)
        # Pausing stops future redraws, but leaves the old native UI visible.
        # Clear both OSD layers; zero alpha lets the live image show through.
        for layer in (0, 1):
            out.append(f'display monitor 0 {layer}')
            out.extend(['display osd 1 0x00000000'] * 3)
        self.progress(out, 0)

    def progress(self, out, filled):
        # Fast miss falls through to the slow loader. Keep the visible state
        # monotonic; never announce completion before stage2 has returned.
        filled = min(3, filled)
        if filled <= self.frame:
            return
        for value in range(self.frame + 1, filled + 1):
            out.append(f'# four-box frame {value}/4')
            out.extend([f'display osdfile \\{ASSET_NAME}\\{value}.BIN 0 0 {WIDTH} {HEIGHT} 0'] * 3)
        self.frame = filled

    def fallback(self, out):
        # Reached on plain success and on any BIN-read failure. Fast success
        # restores natively in splash_finish.S before its existing abort.
        out.append('# --- four-box UI fallback: restore even if BIN did not load ---')
        out.extend([f'mem set 0x{DRAW:08X} 0x{DRAW_ORIGINAL:08X}'] * 3)
        publish(out)
        restore_echo(out)
