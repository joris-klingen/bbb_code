# bbb_code

Tools to keep the BBB Ableton projects consistent: track/group naming, order, colors,
solo hotkeys and (later) take-lane cleanup. Python 3.9+, standard library only.

- `bbb/spec.py` — the conventions (group names, order, colors, solo keys, returns). Edit here.
- `bbb/als.py` — read/write `.als` files (gzipped XML) and track helpers.
- `bbb/restyle.py` — restyle of an existing project, per category: names, order, colors, group
  solo keys, returns, and optional take-lane cleanup (empty / duplicate, unreferenced lanes).
- `bbb/app.py` + `bbb/app.html` — local web app around restyle: load an `.als`, see the
  differences with the template, pick categories, write a new version.
- `bbb/facts.py` — read only: what a set is, as JSON (tempo, time signature, song parts from the
  `parts` track, locators, tracks with their plugins, audio files). `python3 -m bbb.facts song.als`
- `bbb/lcxl.py`, `bbb/launchpad.py` — two controllers on the common groups in Live: a Launch
  Control XL and a Launchpad Mini (see below). `bbb/groups.py` is what they share,
  `bbb/remote_script.py` the part Live loads; `python3 -m bbb.install_remote` puts both in
  Live's User Library.
- `tests/` — `python3 -m unittest discover -s tests -t .` Runs on small synthetic sets built in
  `tests/fixture.py`; real sets stay out of the repo.
- `bbb/build_template.py` — one-off generator of the first template (now maintained by hand in
  `../bbb_ableton_template/BBB template Project`).

Run the app: double-click `BBB Restyle.command` (or run `python3 -m bbb.app` from this folder);
it opens http://localhost:8765 in the browser. Close the Terminal window to stop it.

The app has two views: **Project** (one `.als`, with differences per category and the track
structure) and **All projects** (scan a whole folder, see per project how far its latest version
is from the template, and restyle a selection in one go). Every write is verified to sound the
same as the original; if anything that affects playback differs, nothing is written.

Or restyle from the command line. Without `--write` it only reports; with `--write` it saves
a new version after the newest one in the folder, e.g. `song 2.5.als` with `song 2.6.als`
present -> `song 2.7 (restyle).als`.
`--only` picks categories (default: the ones that are on by default in the app):

    python3 -m bbb.restyle "../../c_opzetjes/my song Project/my song 2.5 (harmonics).als" --write
    python3 -m bbb.restyle song.als --write --only group_names,solo_keys,track_colors

Never write over a source `.als`; output always goes to a new file.

## Controllers in Live

Both controllers work on the same eight columns, one per solo key in `spec.py`: 1 DRUMS
(+ PERC), 2 BASS, 3 KEYS (+ PIANO), 4 SYNTHS, 5 GUIT, 6 all the rest, 7 VOX LEAD, 8 BACKINGS.
Column 6 is GUIT ACC, STRINGS and every other top-level group that is none of the groups (an
FX group, say), but not the archive or `live rig`, and no single tracks (a loose `rec`). Groups are found by name
among the top-level tracks, so it works in any set, restyled or not: the names and aliases
restyle knows, and beyond those by the words in a name (`Vocals`, `vocs lead`, `BVs`,
`Gtr acoustic`). The words are in `spec.py` (`WORDS`, and `PART_WORDS` for song parts).

Set up once: `python3 -m bbb.install_remote`, restart Live, and pick the controller in
*Settings › Link, Tempo & MIDI* (below, per controller). Run the install again after changing
groups in `spec.py`.

### Launch Control XL


- **Fader**: volume of the column's first group. It does nothing until it reaches the volume in
  the set, so the mix never jumps; Live's status bar says which way to move.
  The top knob light turns red for a moment when the fader has to go up, the low one when down.
- **Top knob**: the send of the column's first group to the `amb` return, taken over the same
  way as the fader. The other two knob rows do nothing.
- **Top button**: solo the family (bright yellow; solos add up). **Bottom button**: mute
  (green = you hear it, dim green = silenced by a solo elsewhere, red = muted). A dark column:
  the set has no such group.
- **Knob lights**: what is playing. They show where a group's level is between its own low
  and high of the last moments (three lights on a hit, one as it dies away), so they dance to
  the music whatever the level; two lights for a steady sound, none in silence, amber on top
  when it is loud. With the song stopped they go out at once, and only light while someone
  plays. The `METER_` numbers in `bbb/groups.py` and `bbb/lcxl.py` set how lively it is (on the Launchpad also
  `ACTIVITY_CURVE` in `bbb/launchpad.py`).
- **Solo** (right side): unsolo everything, tracks inside groups and returns too. Lit while
  anything is soloed.
- **Down** (right side): both button rows show the parts of the song instead of solo and mute
  (lit while they do), top row parts 1-8, bottom row 9-16. Parts are the clips on the `Parts`
  track, or the locators when there is none: verse green, chorus red, intro / outro yellow,
  the rest amber, bright where the song is (`Verse2`, `last chorus`, `refrein` count too; a
  `pre-chorus` is not a chorus). A press goes to that part. While playing it waits for
  the next bar line, as launching a clip does: the pad blinks until then (another part while
  one waits takes its place). **Up** shows the next sixteen parts (lit when there are more);
  the rows follow the song.
- **Device**: loop on / off. **Mute**: click on / off. **Left / Right**: punch in / out.
  Each is lit while on.
- **Record Arm**: lit while any track is armed. A press disarms them all; another press arms
  the same tracks again.

In *Settings › Link, Tempo & MIDI*: Control Surface **BBB Groups**, Input and Output **Launch Control XL**. On the device hold
*User* and press *8*. That slot has to hold `templates/Novation LCXL/bbb_groups_for_user_8.syx`
(load it with Novation Components; `user_8.syx` is what was there before): the standard layout
on channel 8, every control with its own number. Factory template 1 stays with the lights
(hitlaunchdmx).

### Launchpad Mini MK3

For moving around a set while mixing; volumes and sends stay on the Mac. Rows from top to
bottom, the round buttons at the right next to their row:

| Row | Pads | Button at the right |
|---|---|---|
| 1-2 | the parts of the song in the color of their clip, bright where the song is; a press goes to the part (while playing: at the next bar line, the pad blinks until then) | |
| 3 | empty; parts 17-24 of a long song | |
| 4 | play / pause (goes on where it was), stop (the next play starts over, as the space bar), –, record, –, punch in, loop, punch out | click |
| 5 | empty | |
| 6 | activity per group: green with the signal; red when a track in it is armed (dim red when silent) | disarm all / arm again |
| 7 | solo (blue) | unsolo all |
| 8 | mute (amber = on, dim = silenced by a solo, dark = muted) | unmute all groups (tracks muted inside a group stay muted) |

The arrows above the pads: left / right = previous / next part, up / down = the other parts
when there are more than 24. A column whose group is not in the set stays dark.

In *Settings › Link, Tempo & MIDI*: Control Surface **BBB Launchpad**, Input and Output the
Launchpad's MIDI port (**LPMiniMK3 MIDI**, not the DAW port), and no other control surface on
this device. The script puts it in Programmer mode and gives it back when Live closes.

To try it: `python3 -m bbb.build_testset "<BBB template.als>"` writes
`testsets/BBB LCXL test Project/BBB LCXL test.als` (not in git): the template without plugins,
plus the cases the script has to cope with. What to look for is at the top of
`bbb/build_testset.py`.

The app looks for projects three folders above `bbb/` (the Bovenburen folder); set `BBB_ROOT` to
point it somewhere else. It only answers its own page on localhost, not other websites.
