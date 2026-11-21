# Launchpad Mini for mixing: plan

A second controller script next to the Launch Control XL one (see README), for moving around a
set while mixing: go to song parts, solo and mute groups, see what plays and what is armed,
transport. Volumes and sends stay on the Mac. Agreed with Joris on 20-21 Nov 2026.

**Status (21 Nov 2026):** built as `bbb/launchpad.py` on the shared `bbb/groups.py`, with tests
on fakes, and installed with the XL script. Not yet tried on the device: see "To check on the
way" below, all still open.

The Launchpad Mini MK3 is used for this only (the lights have their own).

## Layout

Rows from top to bottom, columns 1-8 = the groups of `spec.py` by solo key (DRUMS + PERC, BASS,
KEYS + PIANO, SYNTHS + STRINGS, GUIT, GUIT ACC, VOX LEAD, BACKINGS), as on the XL.

```
top buttons    .    .   [<]  [>]   .    .    .    .          previous / next part
row 1  parts   1    2    3    4    5    6    7    8      .
row 2  parts   9   10   11   12   13   14   15   16      .
row 3          (empty; parts 17-24 in a long song)       .
row 4         play stop  .   rec   .   in  loop out      click
row 5          (empty)                                   .
row 6  activity per group                                disarm all / arm again
row 7  solo per group                                    unsolo all
row 8  mute per group                                    unmute all
```

- **Parts** (rows 1-2): one pad per part in the color of its clip on the Parts track (locators
  when there is no such track: by kind of part, `spec.part_kind`). The part that plays at full
  brightness, the rest dimmed. A press goes to the part; while playing at the next bar line, the pad
  blinking until then. More than 16 parts go on into row 3; more than 24: the top buttons page.
- **Row 3 and row 5** stay empty, to keep parts, transport and groups apart for the eye.
- **Transport** (row 4): play / pause (green while playing; goes on where it was) and stop (the next play starts
  over, as the space bar) at the left; a gap;
  record (Live's arrangement record: dim red, bright while recording); a gap; punch in, loop,
  punch out in the order of Live's control bar, amber, dim when off.
- **Activity** (row 6): one pad per group, its brightness following the signal within the
  group's own recent swing (as the knob lights of the XL do in three steps).

  | Group | Pad |
  |---|---|
  | not armed, silent | dark |
  | not armed, sounding | pulses green |
  | armed, silent | steady dim red |
  | armed, sounding | pulses red, from the dim red up |

  Armed = any track inside the group is armed, recording or not, so it shows before the take
  what will record, and a red pulse shows the input arrives. The pads do nothing when pressed.
- **Solo** (row 7): blue as in Live, dim = can be soloed, bright = soloed. Solos add up.
- **Mute** (row 8): amber = on, dark = muted, as Live's track activator.
- A group the set does not have: its column is dark in rows 6-8.
- **Side buttons**: next to row 4 click; next to row 6 disarm all tracks / arm them again (red
  while anything is armed); next to row 7 unsolo all (lit while anything is soloed); next to
  row 8 unmute all groups (lit while a group is muted; tracks inside groups are left alone). The other four stay dark.
- **Top buttons**: the arrows left / right = previous / next part. The others are free.

## How

1. **Shared logic.** Move what is not about the XL out of `bbb/lcxl.py` into a module both
   scripts use: finding groups and parts, solo / mute, unsolo all, the jump to a part, disarm
   and re-arm, the swing of the level. New here: unmute all, play / stop / record, armed per
   group, clip colors. The XL keeps working as it does; its tests stay green.
2. **The device.** A minimal script that puts the Launchpad in Programmer mode (as
   `hitlaunchdmx` does: pads are notes 10 x row + column, edge buttons controllers, lights by
   RGB sysex), lights some pads and logs presses, and gives the device back when Live closes.
   This is also where to measure how often Live reports level changes, for the pulsing.
3. **Parts rows**, with clip colors and the jump.
4. **Transport row, solo, mute, side buttons.**
5. **Activity row**, green and red.
6. **Install both scripts** with `python3 -m bbb.install_remote`, README, tests, commit.

Each step ends with something to try in Live.

## To check on the way

- Live's own Launchpad script must be off for this device (it is selected without ports now).
- Pad numbers and colors come from `hitlaunchdmx` and from memory, not yet from this unit.
- How fast the activity pads can follow: the XL script refreshes at most some 30 times a
  second, which was not measured.
- Clip colors that are dark or grey may need a floor to stay visible when dimmed.
