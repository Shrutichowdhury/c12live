---
name: Skydroid C12 real control protocol
description: The actual wire protocol used by the SkyDroid C12 camera — confirmed from decompiled APK source
---

## Rule
The SkyDroid C12 uses a **plain ASCII text protocol over UDP port 37260**, NOT any binary/SIYI format.

## How it works
- Command string: `#TPUG2wPTZ01`
- CRC: sum of all bytes mod 256, formatted as 2-char UPPERCASE hex
- Wire bytes: UTF-8(command_string + crc_hex)
- Example: `#TPUG2wPTZ01` → sum = 875 → 875 & 0xFF = 0x6B → wire = `#TPUG2wPTZ016B`

## Key command families
- PTZ: `#TPUG2wPTZ<code>` — 00=STOP 01=UP 02=DOWN 03=LEFT 04=RIGHT 05=CENTER 06=FOLLOW 07=LOCK 08=FOLLOW_SW 09=CAL 0A=HOIST 0B=INVERT 0C=H_CAL 0D=V_CAL 0E=X+ 0F=X- 10=Y+ 11=Y- 12=Z+ 13=Z- 14=CLEAR
- Zoom: `#TPUM2wZMC<code>` — 00=STOP 01=IN 02=OUT
- Focus: `#TPUM2wFCC<code>` — 00=STOP 01=ADD 02=REDUCE
- Photo: `#TPUD2wCAP01`
- Record: `#TPUD2wREC01` start / `#TPUD2wREC00` stop
- Queries: `#TPUD2rVER00` version / `#TPUD2rREC00` rec state / `#TPUD2rVOM00` video config
- Speed control: `#TPUG2wGSY<hex>` yaw / `#TPUG2wGSP<hex>` pitch (signed int hex -99..99)
- Angle control: `#TPUG6wGAY<short_hex>10` yaw / `#TPUG6wGAP<short_hex>10` pitch

## Source files (in this repo)
- `skydroid-live-dashboard/services/command_protocol.py` — CRC + all commands
- `skydroid-live-dashboard/services/c12_controller.py` — UDP transport
- APK source truth: `/tmp/apk_src/sources/com/skydroid/camerafpv/SkydroidControl.java` and `UdpConnect.java`

## Why
Previous implementation used SIYI binary protocol which got no replies. Multi-protocol scan showed UDP packets reach port 37260 but camera replied to nothing binary. APK decompile revealed the real ASCII protocol.

## How to apply
Any future camera command must use `proto.build(cmd_string)` from `command_protocol.py`. Never use binary framing.

## Dashboard has
- `/api/raw_command` endpoint — send any ASCII command, get reply
- Raw Command Terminal in Connection Settings UI with quick-fill buttons
- Multi-Protocol Scan now sends real ASCII probes and shows ASCII replies
