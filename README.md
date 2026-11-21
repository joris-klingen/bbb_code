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
- `bbb/lcxl.py` + `bbb/remote_script.py` — the Launch Control XL on the common groups in Live
  (see below). `python3 -m bbb.install_remote` puts it in Live's User Library.
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

## Launch Control XL

Eight columns, one per solo key in `spec.py`: 1 DRUMS (+ PERC), 2 BASS, 3 KEYS (+ PIANO),
4 SYNTHS (+ STRINGS), 5 GUIT, 6 GUIT ACC, 7 VOX LEAD, 8 BACKINGS. Groups are found by name
among the top-level tracks, so it works in any set, restyled or not: the names and aliases
restyle knows, and beyond those by the words in a name (`Vocals`, `vocs lead`, `BVs`,
`Gtr acoustic`). The words are in `spec.py` (`WORDS`, and `PART_WORDS` for song parts).

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
  plays. The `METER_` numbers in `bbb/lcxl.py` set how lively it is.
- **Solo** (right side): unsolo everything, tracks inside groups and returns too. Lit while
  anything is soloed.
- **Down** (right side): both button rows show the parts of the song instead of solo and mute
  (lit while they do), top row parts 1-8, bottom row 9-16. Parts are the clips on the `Parts`
  track, or the locators when there is none: verse green, chorus red, intro / outro yellow,
  the rest amber, bright where the song is (`Verse2`, `last chorus`, `refrein` count too; a
  `pre-chorus` is not a chorus). A press goes to that part. While playing, the
  playhead goes to the same beat in the bar before the part, so the beat goes on and the part
  starts on the next bar line. **Up** shows the next sixteen parts (lit when there are more);
  the rows follow the song.
- **Device**: loop on / off. **Mute**: click on / off. **Left / Right**: punch in / out.
  Each is lit while on.
- **Record Arm**: lit while any track is armed. A press disarms them all; another press arms
  the same tracks again.

Set up once: `python3 -m bbb.install_remote`, restart Live, *Settings › Link, Tempo & MIDI*:
Control Surface **BBB Groups**, Input and Output **Launch Control XL**. On the device hold
*User* and press *8*. That slot has to hold `templates/Novation LCXL/bbb_groups_for_user_8.syx`
(load it with Novation Components; `user_8.syx` is what was there before): the standard layout
on channel 8, every control with its own number. Factory template 1 stays with the lights
(hitlaunchdmx). Run the install again after changing groups in `spec.py`.

To try it: `python3 -m bbb.build_testset "<BBB template.als>"` writes
`testsets/BBB LCXL test Project/BBB LCXL test.als` (not in git): the template without plugins,
plus the cases the script has to cope with. What to look for is at the top of
`bbb/build_testset.py`.

The app looks for projects three folders above `bbb/` (the Bovenburen folder); set `BBB_ROOT` to
point it somewhere else. It only answers its own page on localhost, not other websites.
