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
# Rounded to the native 4-bit channels; original Sup palette B2 is ~#FF6668.
YELLOW, CORAL, OUTLINE, FILL = 0xFFDD44, 0xFF6666, 0x666666, 0xEEEEEE
MASK_HEIGHT = 48
FP_WIDTH = 34
FP_MASK = (
    'c-rlhKWG#|6vp4o>?INv5|CKi1Z=EAz#@gDh=p25Fu}sg#z3MV1QIJP6hu)BQHbO&Q6nlEG{Ui+XkjHH0Tl_NoW+'
    'TX<nDH7=JU<&<t}%-mnJEFTkOp4Z@>3%-VzZh>b?899R3;RRjNrET?0(nj*yoMC>jE^1#mcBLx^2pt+wX=<n8?|m'
    'nv}#+TbL$G><OY3f_~-C_yd4xQ8;bLbcRT^qh%XjcEv_YKk%=mzkKBZIT~JHbFAhlQr2TCayQAQdjSxzHVlmj_><'
    'L7<}{d{wUFezw8fFU#`H_`T1;+-4UT~cZi<wZS1(_3I-uBr!zt{5jkDbuLB$JLybjFaibSO3*b*J@}~xdW({nBvr'
    '!{zkt&*JBE)zU@W3yl&F}7pY$HPBDk)E?HX4BmaoT<OV!dLH2vF>jGAf$<fQo&bAj)`DJp&$HLj~_tGf~1N;Z=z-'
    'Ccf-U5|`Hrah{1!JDQ0KURJ#*%JS|_B973m?TZj8cmF_OXOe`*Q}*C_g04Vo98D5@W%sZ~`y`CUO1nrBY=zkiH&<'
    'Yp7$leNQusH#QLotB?{VW?cgI~wieB+{u3oX310So+F2qA9>BQ8;)Dbr-G4X&p&*WE&tNyvYi3y8|1=p31&W`vz#'
    'xFQGwSnMV9V9)GG8i$T+^mZ9(WwzFhif~CoGF?4O^HRW)5A>&K|TEk`+G>xR!s6=LDGNQn*9U4`H8^'
)
SUP_WIDTH = 64
SUP_MASK = (
    'c-rliU1(HC6vxlZ+}*^OgiWJ`R!fmc^dYpiqM{-s*oPMT<U^r?Ac*=PQG*tQq8Q^Bh`v;9X_fd;E!kqRV1)V|5!)'
    'ysM*POw6|MQuUB8pvyLaYz&fI%9v2?MkP+y#f-MKU8ckY=p|8p(?2!MC%TN7#huxrOB_OYNLAhN0l5w%A@c(M*;V'
    'YnziikNj7_V~9RR3W?+`!S;tdr!CBM0CxaiK37I6wF3fWAD7T0ET~d67PRpSo{hOn5^!fOb20Z+vngEmcHl>bnzf'
    'WDD8p|E`zMl$Ym&)28%*Dj-$fe^1H-0OaHAx%Ks2?@b7yVb{n&J5g_s$SymCN80JqMn#Szra9)&9RJ(L_!>2JnR0'
    '*ezr*V6frcN$mIGpN9ea)#*FgcY>-5m>3!4IkKR0Gss<EzHojV0{Bfv+fjja`e!a7@AJ;VgQ%!RM#5^*H8RXmRBh'
    'M1wk=MeKN=9FTmjTL<{`(4x`7=>+_4227LBPcxoztC`<pT=O^4CY82YyHp_sxtP$6I-4bjcz<_|bs*pmOyjzMC+A'
    'tq??pCBudS)9ntub0i@VrbLe;M<f9s-u2`}a6jrXX|9`T(^=y~3F@NazTjs(l!kcSn7<mWwH1W_qu6sBsO#npZZk'
    'cZM)yLxRA>JRy5^YAYI74h#~!70q(p|FVf)FYcbLlJxrPF_BZy950=Vk7aFBe^nGWIR`E&vXi^ggpEJt{1*i9cZ9'
    'v5~V@-HV6mWDZ`0k@cH%s#(xv?Vhz3jYSgALaNx)m@_9WP@LSkaiCLtYkk8<mz*s>mJ)Pi5)g&S*DKY{b)Id&gCA'
    'ZP$K7M}`wo**F{A)9VmN@(|{iLSN<ZW!?QLXJm0ACoolTF|#_>ng6#mFy=zGw7M{$i!I6$g>ZW(tUj)U~|rA5kLT'
    'UN&H~=Z@n<EFe?dKN4WlIoA82{xn{gNnw4^N`j;7lSQ34K;p+M$J>*1{Vq1Le#D3*sUG`|cW8Y4#5|{8#LLGzHRB'
    'Jfg%mYi)P2+J0yETpn{5+PFqc*{)_UQeT4!?kYi&dB^O}eUGr9htwDAsxqk9R6Kwb+T*p=iQ#Z7&DsGsJtcwqaRU'
    'u$$7m0#{Wb1T_%zGeOh2)mwy_g2J@#FvkPq8W8{wI$pfnU7OS*8Fm0U(@ukli7fwBvvMdG`AsbZg7G5pF}9x!Ow('
    'HK}|SAzkSkCQqcv1qA|!*kFp!;pPw-yUetF39$s#|etr)%)xEF4$4R|EzXJbl-_5@7UYZ9eE-x)FhSxX5i$(Hgyc'
    'z%Ncm}+Cef<'
)


def asset():
    """Return empty→four-filled frames with no host font/library dependency."""
    base = [0] * (WIDTH * HEIGHT)
    logo_width = FP_WIDTH + SUP_WIDTH
    box_size, gap = 24, 10
    total = logo_width + 30 + 4 * box_size + 3 * gap
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

    logo(FP_MASK, FP_WIDTH, left, YELLOW)
    logo(SUP_MASK, SUP_WIDTH, left + FP_WIDTH, CORAL)
    boxes_x = left + logo_width + 30
    frames = []
    for filled in range(5):
        pixels = base.copy()
        for box in range(4):
            x0, y0 = boxes_x + box * (box_size + gap), 20
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
