"""Launch Control XL on the common groups: what every control does, without Live.

Eight columns, the groups of groups.py (1 DRUMS + PERC ... 6 all the rest ... 8 BACKINGS). Per
column: fader = volume, top knob = send to the amb return, top button = solo, bottom button =
mute, the three knob lights = activity. On the right: Solo clears every solo in the set,
Device = loop, Mute = click, Left / Right = punch in / out, Record Arm = disarm every track
(again: arm them again). Down switches both button rows to the parts of the song (top row 1-8,
bottom row 9-16): a press goes to that part, Up shows the next sixteen.

Colors: yellow = solo, green = you hear it (dim: silenced by a solo elsewhere), red = muted,
dark = the set has no such group.

The device has to be on User template 8 (hold User, press 8), loaded with
`templates/Novation LCXL/bbb_groups_for_user_8.syx`: the device's standard layout on channel 8,
every control with a number of its own. Factory template 1 is the lights (hitlaunchdmx).

This module only needs objects that look like Live's song and tracks, so the tests run it on
fakes; `remote_script.py` is the part that Live loads.
"""
import time

try:
    from . import groups, spec
except ImportError:      # pragma: no cover - only when loaded outside a package
    import groups
    import spec
COLUMNS, group_name = groups.COLUMNS, groups.group_name
NAME = 'BBB Groups: Launch Control XL'

TEMPLATE = 7             # sysex template number: user 0-7, factory 8-15
TEMPLATE_NAME = '%s template %d' % (('User', TEMPLATE + 1) if TEMPLATE < 8 else ('Factory', TEMPLATE - 7))
CHANNEL = TEMPLATE       # counted from 0: channel 8

FADER_CCS = [77, 78, 79, 80, 81, 82, 83, 84]
SOLO_NOTES = [41, 42, 43, 44, 57, 58, 59, 60]     # top button row
MUTE_NOTES = [73, 74, 75, 76, 89, 90, 91, 92]     # bottom button row
AMB_CCS = [13, 14, 15, 16, 17, 18, 19, 20]        # top knob row ("Send A")
AMB_RETURN = ['amb', 'ambience']                  # names of the return, without Live's 'A-'
# The buttons on the right. The template numbers them 101-108 in the order the device numbers
# their lights: Device, Mute, Solo, Record Arm, Up, Down, Left, Right.
UNSOLO_NOTE = 103                                 # Solo
SONG_NOTES = {101: 'loop', 102: 'metronome', 107: 'punch_in', 108: 'punch_out'}
SONG_LEDS = {'loop': 40, 'metronome': 41, 'punch_in': 46, 'punch_out': 47}
ARM_NOTE, ARM_LED = 104, 43                       # Record Arm
PARTS_NOTE, PARTS_LED = 106, 45                   # Down: the rows show the parts
UP_NOTE, UP_LED = 105, 44                         # Up: the next sixteen parts
PART_NOTES = SOLO_NOTES + MUTE_NOTES              # while the rows show the parts

# LED numbers in the sysex message, and the colors (red + green brightness in one byte)
KNOB_LEDS = [list(range(0, 8)), list(range(8, 16)), list(range(16, 24))]    # top, mid, low row
SOLO_LEDS = list(range(24, 32))
MUTE_LEDS = list(range(32, 40))
UNSOLO_LED = 42
OFF, GREEN_DIM, GREEN, YELLOW_DIM, YELLOW, AMBER, RED = 12, 28, 60, 29, 62, 63, 15
AMBER_DIM, RED_DIM, LIME_DIM = 29, 13, 45

# Parts on the button rows: (playing, not playing) by the kind of part (spec.part_kind).
PART_COLORS = {'verse': (GREEN, GREEN_DIM), 'chorus': (RED, RED_DIM),
               'intro': (YELLOW, LIME_DIM), 'outro': (YELLOW, LIME_DIM)}
PART_OTHER = (AMBER, AMBER_DIM)                   # pre, post, bridge and anything else

# Activity on the three knob lights (groups.Groups.activity): three at the top of the swing.
METER_STEPS = (0.35, 0.7)    # part of the swing from which the middle / the top light is on
METER_LOUD = 0.9         # from this level the top light is amber
HINT_SECONDS = 2.0       # how long 'move the fader up / down' stays on the knob lights

SYSEX = (0xF0, 0x00, 0x20, 0x29, 0x02, 0x11)
SET_LEDS, TEMPLATE_CHANGED = 0x78, 0x77

NEAR = 2 / 127.0         # a fader this close to the volume takes it over
JUMP = 6                 # a fader sends every step (measured: 1 at a time); more in one message is
                         # not the fader (another template with the same numbers) and is ignored


def db(param):
    try:
        return param.str_for_value(param.value)
    except Exception:
        return ''


class Surface(groups.Groups):

    def __init__(self, song, send, message=lambda text: None, clock=time.monotonic):
        super().__init__(song, send, message, clock)
        self.leds = {}                       # led number -> color last sent
        new = lambda: dict(hw=None, set=None, told=False, hint=None, until=0)
        self.faders = [new() for _ in FADER_CCS]
        self.knobs = [new() for _ in AMB_CCS]
        self.parts_mode, self.page, self.playing_part = False, 0, None

    # --- from the device ---

    def receive(self, data):
        data = tuple(data)
        if data[:len(SYSEX)] == SYSEX:
            if len(data) > 7 and data[6] == TEMPLATE_CHANGED and data[7] == TEMPLATE:
                self.leds = {}               # the device shows this template again: light it
                self.refresh()
            return
        if len(data) != 3 or data[0] & 0x0F != CHANNEL:
            return
        kind, number, value = data[0] & 0xF0, data[1], data[2]
        if kind == 0xB0 and number in FADER_CCS:
            self.fader(FADER_CCS.index(number), value)
        elif kind == 0xB0 and number in AMB_CCS:
            self.amb(AMB_CCS.index(number), value)
        elif kind == 0x90 and value:         # presses only; releases are note on 0 / note off
            if number in PART_NOTES and self.parts_mode:
                self.go_to_part(self.page * len(PART_NOTES) + PART_NOTES.index(number))
            elif number in SOLO_NOTES:
                self.toggle(SOLO_NOTES.index(number), 'solo')
            elif number in MUTE_NOTES:
                self.toggle(MUTE_NOTES.index(number), 'mute')
            elif number == PARTS_NOTE:
                self.parts_mode, self.playing_part = not self.parts_mode, None
            elif number == UP_NOTE and self.parts_mode:
                pages = max(1, -(-len(self.parts()) // len(PART_NOTES)))
                self.page = (self.page + 1) % pages
            elif number == ARM_NOTE:
                self.arm_button()
            elif number == UNSOLO_NOTE:
                self.unsolo_all()
            elif number in SONG_NOTES:
                song, what = self.song(), SONG_NOTES[number]
                setattr(song, what, not getattr(song, what))
        else:
            return
        self.refresh()

    def fader(self, col, value):
        """Volume of the column's first group."""
        f = self.faders[col]
        if f['hw'] is not None and abs(value - f['hw']) > JUMP:
            f['hw'] = f['set'] = None        # not the fader: start over from here
        tracks = self.columns()[col]
        if tracks:
            self.take_over(f, value, tracks[0].mixer_device.volume, tracks[0].name, 'move the fader')
        f['hw'] = value

    def amb(self, col, value):
        """Send of the column's first group to the amb return."""
        f = self.knobs[col]
        tracks = self.columns()[col]
        names = [r.name.split('-', 1)[-1].strip().lower() for r in self.song().return_tracks]
        index = next((i for i, n in enumerate(names) if n in AMB_RETURN), None)
        if tracks and index is not None:
            self.take_over(f, value, tracks[0].mixer_device.sends[index],
                           tracks[0].name + ' amb', 'turn the knob')
        f['hw'] = value

    def take_over(self, f, value, p, name, how):
        """Set parameter p from a fader or knob at `value` (0-127). A control that is somewhere
        else than the parameter does nothing until it reaches it, so touching one never makes
        the mix jump."""
        before = f['hw']
        span = (p.max - p.min) or 1.0
        pos = lambda v: p.min + span * v / 127.0
        target, now = pos(value), p.value
        following = f['set'] is not None and abs(now - f['set']) < 1e-4
        reached = abs(target - now) <= NEAR * span
        crossed = before is not None and (pos(before) - now) * (target - now) <= 0
        if following or reached or crossed:
            p.value = f['set'] = target
            f['told'], f['hint'] = False, None
        else:
            f['set'] = None
            f['hint'], f['until'] = ('down' if target > now else 'up'), self.clock() + HINT_SECONDS
            if not f['told']:
                f['told'] = True
                self.message('%s is at %s: %s %s to take over'
                             % (name, db(p), how, 'up' if target < now else 'down'))

    # --- to the device ---

    def colors(self):
        leds, heard, now = {}, self.heard(), self.clock()
        columns = self.columns()
        activity = self.activity(columns)
        for i, tracks in enumerate(columns):
            knobs = [row[i] for row in KNOB_LEDS]
            for k in knobs:
                leds[k] = OFF
            if not tracks:
                leds[SOLO_LEDS[i]] = leds[MUTE_LEDS[i]] = OFF
                continue
            leds[SOLO_LEDS[i]] = YELLOW if any(t.solo for t in tracks) else YELLOW_DIM
            if all(t.mute for t in tracks):
                leds[MUTE_LEDS[i]] = RED
            elif heard is not None and not any(t in heard for t in tracks):
                leds[MUTE_LEDS[i]] = GREEN_DIM
            else:
                leds[MUTE_LEDS[i]] = GREEN
            f = next((f for f in (self.faders[i], self.knobs[i]) if f['hint'] and now < f['until']), None)
            if f:                                    # top light: move up, low light: move down
                leds[knobs[0] if f['hint'] == 'up' else knobs[2]] = RED
                continue
            if activity[i] is None:
                continue
            where, level = activity[i]
            leds[knobs[2]] = GREEN
            if where >= METER_STEPS[0]:
                leds[knobs[1]] = GREEN
            if where >= METER_STEPS[1]:
                leds[knobs[0]] = AMBER if level >= METER_LOUD else GREEN
        leds[UNSOLO_LED] = YELLOW if heard is not None else OFF
        leds.update(self.part_colors())
        leds[ARM_LED] = YELLOW if self.armed() else OFF
        song = self.song()
        for what, led in SONG_LEDS.items():
            leds[led] = YELLOW if getattr(song, what, False) else OFF
        return leds

    def part_colors(self):
        """Down and Up, and both button rows while they show the parts."""
        if not self.parts_mode:
            return {PARTS_LED: OFF, UP_LED: OFF}
        rows = SOLO_LEDS + MUTE_LEDS
        parts, size = self.parts(), len(rows)
        playing = self.part_now(parts)
        if playing != self.playing_part:         # the song moved on: show the page it is on
            self.playing_part = playing
            if playing is not None:
                self.page = playing // size
        self.page = min(self.page, max(0, (len(parts) - 1) // size))
        leds = {PARTS_LED: YELLOW, UP_LED: YELLOW if len(parts) > size else OFF}
        for i, led in enumerate(rows):
            index = self.page * size + i
            if index >= len(parts):
                leds[led] = OFF
                continue
            on, dim = PART_COLORS.get(spec.part_kind(parts[index][0]), PART_OTHER)
            leds[led] = on if index == playing else dim
        return leds

    def refresh(self):
        """Send the lights that changed. Called after every press and ten times a second."""
        changed = [(k, v) for k, v in sorted(self.colors().items()) if self.leds.get(k) != v]
        if changed:
            self.leds.update(changed)
            self.send(SYSEX + (SET_LEDS, TEMPLATE) + tuple(b for kv in changed for b in kv) + (0xF7,))

    def start(self):
        """Nothing to set up on the device: light it."""
        self.leds = {}
        self.refresh()

    def stop(self):
        self.lights_off()

    def lights_off(self):
        self.send(SYSEX + (SET_LEDS, TEMPLATE)
                  + tuple(b for k in sum(KNOB_LEDS, []) + SOLO_LEDS + MUTE_LEDS + [UNSOLO_LED] + sorted(SONG_LEDS.values()) + [PARTS_LED, UP_LED, ARM_LED]
                        for b in (k, OFF)) + (0xF7,))
        self.leds = {}


# What Live has to pass on to the script: (channel, number).
FORWARD_CCS = [(CHANNEL, cc) for cc in FADER_CCS + AMB_CCS]
FORWARD_NOTES = [(CHANNEL, note) for note in SOLO_NOTES + MUTE_NOTES
                 + [UNSOLO_NOTE, PARTS_NOTE, UP_NOTE, ARM_NOTE] + list(SONG_NOTES)]
