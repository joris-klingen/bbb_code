# The Launchpad in Live

A Launchpad Mini MK3 on eight columns, one per solo key in `spec.py`: 1 DRUMS
(+ PERC), 2 BASS, 3 KEYS (+ PIANO), 4 SYNTHS, 5 GUIT, 6 all the rest, 7 VOX LEAD, 8 BACKINGS.
Column 6 is GUIT ACC, STRINGS and every other top-level group that is none of the groups (an
FX group, say), but not the archive or `live rig`, and no single tracks (a loose `rec`). Groups are found by name
among the top-level tracks, so it works in any set, restyled or not: the names and aliases
restyle knows, and beyond those by the words in a name (`Vocals`, `vocs lead`, `BVs`,
`Gtr acoustic`). The words are in `spec.py` (`WORDS`, and `PART_WORDS` for song parts).

Set up once: `python3 -m bbb.install_remote`, restart Live, and pick the controller in
*Settings › Link, Tempo & MIDI* (below). Run the install again after changing groups in
`spec.py`.

## Layout

For moving around a set while mixing; volumes and sends stay on the Mac. Rows from top to
bottom, the round buttons at the right next to their row:

| Row | Pads | Button at the right |
|---|---|---|
| 1-2 | the parts of the song in the color of their clip, bright where the song is; a press goes to the part (while playing: at the next bar line, the pad blinks until then) | |
| 3 | empty; parts 17-24 of a long song | |
| 4 | play (from where it last started, as the space bar; after choosing a part: from the part), play from the cursor (as shift + space); both stop while playing; –, record, –, punch in, loop, punch out | click |
| 5 | only below loop: the MIDI note editor's preview switch (bright blue = on), once mapped in Live (below) | |
| 6 | activity per group: green with the signal; red when a track in it is armed (dim red when silent) | disarm all / arm again |
| 7 | solo (blue) | unsolo all / solo again |
| 8 | mute (amber = on, dim = silenced by a solo, dark = muted) | unmute all groups (tracks muted inside a group stay muted) / mute again |

The arrows above the pads: left / right = previous / next part, up / down = the other parts
when there are more than 24. A column whose group is not in the set stays dark.
How lively the activity pads are: the `METER_` numbers in `bbb/groups.py` and `ACTIVITY_CURVE`
in `bbb/launchpad.py`.

In *Settings › Link, Tempo & MIDI*: Control Surface **BBB Launchpad**, Input and Output the
Launchpad's DAW port (**LPMiniMK3 DAW**), and no other control surface on
this device. The script puts it in Programmer mode and gives it back when Live closes.

The preview switch of the MIDI note editor is not in Live's API, so its pad (below loop) is left
to Live: turn on **Remote** for the Launchpad's input, then in MIDI Map mode (cmd-M) click the
Preview switch in the MIDI editor and press the pad; then, still in MIDI Map mode, click the
Activator (the on/off button) of the `length` track and press the pad again. One press now flips
both, and since the script cannot see the switch (and Live sends no feedback for it), it lights
the pad by the `length` track: bright blue while that track is off, i.e. preview on. The track
is silent, so switching it does nothing to the sound. Should they get out of step, click the
Preview switch once with the mouse. The mappings are saved with the set.

Leave **Remote** off on every MIDI output (the Launchpad's and the others'): Live sends the note
of a mapped control to each output that has it on, whenever the control changes. With Remote on
the output of a synth, every switch of `length` plays a B on it (the pad is note 47).

## A set to try it on

To try it: `python3 -m bbb.build_testset "<BBB template.als>"` writes
`testsets/BBB controller test Project/BBB controller test.als` (not in git): the template without plugins,
plus the cases the script has to cope with. What to look for is at the top of
`bbb/build_testset.py`.
