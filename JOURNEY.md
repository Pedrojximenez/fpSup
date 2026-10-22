# The Journey

**English** · [简体中文](JOURNEY.zh-CN.md) · [繁體中文](JOURNEY.zh-TW.md)

> The README covers how I found the way in to modify the camera. This is the full story: starting from a dead end and walking all the way to where we are now,
> the wrong turns along the way, the things I learned, and the doors beyond fpSup that are still open.
>
> All dates are in 2026.

---

## 1. Where it started: shooting alone, needing focus

I often shoot alone, as both the camera operator and the subject.
Hyperfocal, PDMOVIE Live Air, DJI Focus Pro — I tried them all, and none of them satisfied me.
Sometimes a camera operator uses my gear too, and with all of that mounted plus a 3-axis gimbal, the weight gets ridiculous. 😅

I always knew that maybe switching cameras, or even just using a phone, would solve it.
But I really love the fp's design, so I stubbornly stuck with it.

## 2. The first road: PTP

In June I started [sigma-fp-bridge](https://github.com/ijigen/sigma-fp-bridge), and in August I began developing it intensively.

The fp can be controlled over USB with the PTP protocol. I didn't just follow sigma-ptpy; I spent a lot of time on trial and error,
probing PTP opcodes and parameters one by one, and eventually I really did find a way to control focus over PTP.

Then I built a pipeline that, looking back, is a little absurd: grab the live view, run face detection, and use image analysis to predict the focus distance.
I tried every trick I could think of, all just to make autofocus work from live view alone.
For that stretch I was up late testing almost every night, with the AI even giving me voice directions on where to stand so it could use me as the test subject.

Just when I thought I was almost there, I took it out for a real shoot for the first time, pressed record —
**and during recording, PTP focus stopped completely.**

After all that testing, it had never once occurred to me to test whether it worked while recording. I felt like the biggest idiot in the world. 😱

## 3. Opening the firmware

I wouldn't let it go. Since I'd been able to find a way to control focus in the first place, I was convinced SIGMA's engineers must have left hidden commands somewhere.

On August 12, I had the AI unpack and decompile the firmware `FP__V502.bin`. The firmware file has no password and no permission checks of any kind.

It found all of the PTP-related code, and it also found hard proof: **focus commands during recording are deliberately blocked by the firmware.**
The PTP road was a dead end.

But once the firmware was open, what I saw was an entire map:
the PTP protocol for the gimbal interface (which later became [sigma-fp-gimbal-ai](https://github.com/ijigen/sigma-fp-gimbal-ai)),
factory test points, all kinds of engineering interfaces, and something called `AutoRun.txt`.

## 4. The way in: `AutoRun.txt` and `mem set`

The AI kept thinking `AutoRun.txt` was nothing special. It looked like just a simple scripting language, and it really had no commands related to focus.

Until I noticed that among the shell commands there was **`mem set`**, which can write to any memory address.
From what I knew of reverse engineering, my gut told me I'd stumbled on something extremely valuable.

At 2 a.m. on August 14, AutoRun ran on the camera for the first time.
Two days later, by modifying memory, I put an overexposure warning curve on the LCD.
That was the first time I actually changed how the camera behaves.

The firmware is decompressed into RAM at boot and runs from there; `AutoRun.txt` patches the code in RAM at boot,
and the new features live in unused memory. **It's all in RAM — take out the card, reboot, and the camera is back to stock.**
That is the foundation of everything that came after.

## 5. Talking to the camera: USB Shell

Pulling the card, writing it, reinserting it and booting for every single change was way too slow. I needed the computer to talk to the camera directly.

- **August 17–18**: the first USB shell. v27 froze the camera.
- **August 19**: figured out how the camera's operating system (TK-OS) creates tasks, and the first task we created ourselves ran inside the camera;
  `mem set` was sent from the computer over USB into the camera and executed for the first time.
- **August 21**: the full shell running over USB, with color bars on the camera's screen. The cause of the v27 freeze was found too:
  we had grabbed a USB endpoint the firmware didn't recognize.
- **August 26**: USB Shell v2. Switched to piggybacking on the camera's own PTP endpoints, letting the firmware keep managing its own stuff.

This step completely changed the pace of development from then on: reading and writing memory, calling firmware functions, pressing buttons, taking screenshots, transferring files — all from the computer.

## 6. Nobody cared, and then GYRO

I made a few little toys and posted them in the SIGMA fp groups. Almost nobody paid attention.
I felt people hadn't yet realized that this discovery had already proven everything could be changed.

**I needed something big enough.**

Gyro logging is a feature fp users had been asking SIGMA for for a long time. The fp clearly has a gyroscope inside, yet the data never gets written into the footage.
I spent over a month on it, almost without stopping, burning through countless nights.

The hardest hurdle along the way: after a recording ended, roughly one in four times the camera would freeze.
In the end, using "is the metadata file 0 bytes?" as the clue and bisecting step by step, I found it was **priority inversion**:
our low-priority file-writing task was holding the file system lock, and the camera's own recording task couldn't get it.

**On August 30, fpGyroSup v1 was released.** The same day I opened a Discord and a Ko-fi,
and also made public the development tools built along the way. That's where the attention started.

## 7. Open Gate: beaten to it

After GYRO was released, I started on Open Gate, letting the fp record the sensor's full 3:2 frame.
After a day and a half without sleep, just as I was ready to release, I suddenly realized someone had beaten me to it. LOL.

**On September 10, Vitaly Li released the world's first fp Open Gate.**

I didn't expect things to move that fast. From "nobody cares" to "someone got there before me" took only a few weeks.

His approach was different from mine: he does the 2:1 downscale in the image processor, while I downscale at sensor readout. Both roads work.
When I released OG3K on September 14, the first thing I did was credit him. Every Open Gate-related release since then says he was first.

## 8. Lossless: its own hardware encoder

The fp has a hardware lossless compression engine it uses for stills, but video never used it, so CinemaDNG was always uncompressed, and card write speed was always the bottleneck.

On August 30, I measured that this engine can process 170 million pixels per second, which makes compressed FHD recording feasible.
On September 21, I made the research and development direction public: the engine's cost model, where it sits in the pipeline, plus an explainer page and a budget simulator.
On October 3, the first Lossless was released.

## 9. Pulling releases

On September 24, I pulled four releases because of a serious bug.

The next day I found the cause: when gyro v1.13 powered off, a hook was still pointing at a piece of memory that no longer existed. Once that was fixed, the other three versions were restored too.

Pulling releases hurts, but I think it's taking responsibility toward the people using them.
Your camera is yours. I'd rather pull something than leave an uncertain thing out there.

## 10. A brave warrior

On October 2, Andy_hal9000 bricked his fp.

He had modified a function in the firmware himself, repacked it and flashed it, and the camera wouldn't start.
What followed was him fumbling his way through in a panic: power off, pull the battery, hold DISPLAY + Up, then put the battery back in —
the camera ran a piece of boot code, and the screen even showed live view. Ten minutes later he connected USB, and the computer saw the camera.
In the end he used an AutoRun containing `fwup FIRMWARE` to write the firmware back and brought the camera back to life.

He can't even remember all the details himself; he had Claude help him write it down afterward.

I haven't verified this method, so it can't be treated as a recovery guide. But it tells us:
**the fp may have an engineering boot mode when USB is connected while powered off.** If it really does get bricked, maybe that's not the end of the road.

> He said afterward: be very careful writing firmware — he only changed one function, and it didn't end well.

## 11. People started joining

**Making their own work**

- **Vitaly Li**: the world's first fp Open Gate (FP3K).
- **Jose Hurtado**: made all kinds of different resolutions (S16, OG3.5K, OG4K…), and has consistently worked to keep his work compatible with the Merge format.
  Res-Custom includes his formats; Desqueeze and Tap to Zoom are his work too, and he also made his own unofficial card-merging page.
- **Julien Acquaviva**: sigma-fp-supmod, his own set of fp modifications, including in-camera lossless CinemaDNG and multiple resolutions.
- **Ruari**: STOPFX, which makes the camera clean up leftover frames after an abnormal recording stop.
- **lachgil**: [sigma-fp-lab](https://github.com/lachgil/sigma-fp-lab), reverse engineering of the display and overlays;
  made False Color / EL Zone scale bars that can be assigned to a button.
- **willygooddeals** (GitHub: [wjhrdy](https://github.com/wjhrdy/fpSup)): Focus Inset (Merge-compatible);
  a mod that forces 60 Hz anti-flicker in the C1 custom mode, so shooting indoors you don't have to worry about picking the wrong shutter in P mode; and a mod that brightens the live view when shooting at -1 to -3 EV.
- **unremarkablegarden**: Gyro Base + HDMI — when using an external recorder like an Atomos, the camera still logs gyro data and writes timecode into the lens file;
  plus Gyroflow Batch Resolve, which uses timecode to automatically match gyro logs to externally recorded clips, so stabilization is done in one click.
- **Andy_hal9000**: a live view log curve built from the ARRI LogC3 paper; and the rear dial fix (Dial Fix), which makes a not-so-responsive rear dial much nicer to use.

**Making my work better**

- **Andy_hal9000** (our Flash ⚡, and also a brave warrior who went through hell and came back: after bricking his camera he found his own way to bring it back): pointed out AutoRun's per-character delay, bringing boot time down from 11.5 seconds to 3 seconds; every card uses it.
- **Ole Berek**: *SIGMA fp Rec709 LUT & Operations Guide*. RAW-View's display curve and dynamic range data draw heavily on his research.
- **Luka**: used his own fp to prove frame by frame that RAW-View doesn't alter the RAW;
  also found that the CinemaDNG color tags make white balance about 1100 K too cool at saturation +0.2, derived a fix, and attached tests.
- **CorNy**: discovered that DaVinci Resolve needs the first frame to be uncompressed to play mixed-compression clips properly. Because of that, Lossless leaves the first frame of every clip uncompressed.
- **CC FRANK FPV**: one of the first users to shoot real-world tests with an OG2K + Gyro merged card.

**Standing on the shoulders of giants**

- **Gyroflow**: without it, gyro data is just a pile of numbers.
- **sigma-ptpy**: the starting point of my early PTP research.

And everyone on Discord who reported problems, shared footage, and helped test.


I made **fpSup-Merge** early on (mid-September): pick the tools you want on a web page and it combines them into one card, so other people's work can sit alongside mine.
October's Loader v3 is just an update to it: one file per sup, which makes merging easier.
I don't need to bring everyone's work under my name; I just want them to coexist and to be seen by more people.

---

## 12. Building it with AI

Almost every step of this whole project was done together with AI: **Claude** (Anthropic, in Claude Code) and **Codex** (OpenAI).
Decompiling, reading disassembly, finding free memory, writing patches, testing on the camera, writing notes — they did most of the hands-on work; I handled direction, judgment, and the "wait, something's off here."

A lot of the time I used both together: let each look at the same problem separately and check each other.

| Period | Main model | What was being worked on |
|---|---|---|
| Early August ~ late August | Claude Opus 5 | sigma-fp-bridge, focus-ai, gimbal-ai: PTP focus, decompiling the firmware |
| Mid-August ~ late September | Codex (GPT-5.6 Sol) | Early versions of the USB shell, chasing freezes, in parallel with Claude |
| Late August ~ September | Claude Opus 5 (occasionally Opus 4.8, Fable 5.1) | USB Shell v2, GYRO, Open Gate |
| Mid-September ~ October | Codex (GPT-6 Astra; from October, GPT-6 / 6.1 Sol) | Card-building pipeline, Merge, reviews |
| Late September ~ now | Claude Opus 5.5 | Lossless, Loader v3, Res-Custom, Gyro2, and most of the current work |

<!-- Sources: git commit co-author lines, local Claude Code and Codex logs. Claude's local logs before 9/20 have been cleared, so the August part can only be inferred from commits. -->

The models went through several generations, each stronger than the last, but every one of them made mistakes. Many of the entries under "Wrong turns" below are conclusions they were very confident about that were eventually overturned.

## 13. What I learned

**1. Test in the real situation first.**
I tested PTP focus for months, but never once during recording. Before the most expensive step, ask: what state will it actually be in when it's really used?

**2. AI underestimates things; your intuition matters.**
The AI treated `AutoRun.txt` as a boring script. The turning point wasn't found by the AI — it was a human feeling "wait, something's off here."

**3. Dead ends lead somewhere else.**
PTP was a dead end, but to prove it was a dead end, I opened the firmware. Without that dead end, there would be no fpSup.

**4. Conclusions must be able to be overturned.**
My AI gave me many very confident but completely wrong conclusions (see the next section).
The methods that catch mistakes are all plain: measure the same thing with two independent rulers, bisect step by step, and read back after writing to confirm.

**5. When it hangs, preserve the evidence first.**
When the camera freezes, the card often still holds the last clues. Read the card first, then reboot.

**6. Credit others, and let work coexist.**
Being beaten to it isn't a bad thing. Write it down, make clear who got there first, and then go your own way.

## 14. Wrong turns

These are all conclusions I (and my AI) were once very sure of, and that were later overturned.

| What we believed | How we found it was wrong | The truth |
|---|---|---|
| Focus can be controlled externally over PTP | Commands silently ignored during recording | The firmware deliberately restricts it to the "shooting idle" state |
| `AutoRun.txt` is nothing special | Noticed `mem set` | The front door to all of fpSup |
| The fp has usable PDAF | Read the firmware: the relevant functions unconditionally return 0 | The fp is pure contrast-detect AF; both PDAF gates are closed |
| A certain USB endpoint gets stuck and you have to unplug | Sent 100 times, failed immediately 100 times | That endpoint doesn't exist at all |
| Recording freezes because the computer keeps polling the camera → because the cable is connected → … | The conclusion was overturned five times | Being connected is fine; only sending commands during recording hangs it |
| The post-recording freeze is a bug in a particular version | Bisection | Priority inversion |
| "Bayer raw data isn't in memory" | The registers used as proof read back 0 across the whole range | The proof was invalid; during HDMI RAW output, Bayer is in memory |
| The RWZM scaler doesn't matter | Open Gate was always just a bit off | It's the last piece of Open Gate |
| Gyro at 2501.85 Hz | Two independent rulers | 2499.48 Hz |
| "Compression isn't feasible" | Found the judgment was built on a timeout error | Feasible — it later became Lossless |
| Booting is slow because there are too many commands | Measured the cost of each command | Most of the time went to the per-character delay |

## 15. Doors still open

fpSup is only one part of this camera. Below are things I've touched but not finished. If you're interested, the door is open.

| Direction | Status | Where to start reading |
|---|---|---|
| **Focus (where it all began)** | Both PDAF gates are closed; in-camera continuous focus still lacks a usable data stream | `projects/fp-af-assist/` |
| Gimbal interface | The PTP gimbal protocol is written up as a manual; gimbal-ai is paused | `research/interfaces/notes/GIMBAL_MANUAL.md` |
| Hot shoe | It's a bidirectional SPI channel; static analysis only, never tested on the camera | `research/interfaces/notes/HOT_SHOE.md` |
| Factory test points / UART | Requires opening the camera and wiring; pinout unconfirmed | `research/firmware/notes/HIDDEN_FEATURES.md` |
| HDMI RAW recorder | The HDMI signal is 12-bit Bayer; the spec is written, nobody has built it yet | `projects/hdmi-recorder/` |
| Other cameras with the same IMX410 | Z CAM E2-F6 fully opened; Sony A7 III decompiled; Nikon looked at; Panasonic encrypted | Still on my computer, not yet in the repo |

The focus problem that started all of this is still unsolved.

Maybe the next person to crack it is you.

**— bei**
