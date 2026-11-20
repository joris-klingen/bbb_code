"""Launch Control XL on the common groups: what every control does, without Live.

Eight columns, one per solo key in spec.GROUPS (1 DRUMS + PERC ... 8 BACKINGS). Per column:
fader = volume, top knob = send to the amb return, top button = solo, bottom button = mute, the
three knob lights = level meter. On the right: Solo clears every solo in the set, Device = loop,
Mute = click, Left / Right = punch in / out, Record Arm = disarm every track (again: arm them
again). Down switches both button rows to the parts of the song (the clips on the Parts track;
top row 1-8, bottom row 9-16): a press goes to that part, Up shows the next sixteen. Colors: yellow = solo, green = you hear it
(dim: silenced by a solo elsewhere), red = muted, dark = the set has no such group. Groups are found by name (the same names and aliases restyle knows), among the
top-level tracks, so this works in any Bovenburen set.

The device has to be on User template 8 (hold User, press 8), loaded with
`templates/Novation LCXL/bbb_groups_for_user_8.syx`: the device's standard layout on channel 8,
every control with a number of its own. Factory template 1 is the lights (hitlaunchdmx).

This module only needs objects that look like Live's song and tracks, so the tests run it on
fakes; `remote_script.py` is the part that Live loads.
"""
import time

try:
    from . import spec
except ImportError:      # pragma: no cover - only when loaded outside a package
    import spec

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

# Parts on the bottom row: (playing, not playing) by the first word of the part's name.
PART_COLORS = {'verse': (GREEN, GREEN_DIM), 'chorus': (RED, RED_DIM),
               'intro': (YELLOW, LIME_DIM), 'outro': (YELLOW, LIME_DIM)}
PART_OTHER = (AMBER, AMBER_DIM)                   # pre, post, bridge and anything else

# Meter on the three knob lights, to see what is playing rather than how loud. Live's meter
# (0-1) moves only a little between the hits of a group, so the lights show where the level is
# between the lowest and the highest of the last moments: three at the top of that swing, one
# at the bottom. They dance to the music whatever the level of the group.
METER_FLOOR = 0.02       # below this: silence, no lights
METER_STEPS = (0.35, 0.7)    # part of the swing from which the middle / the top light is on
METER_FALL = 0.2         # how fast the remembered high comes down, per second
METER_RISE = 0.4         # how fast the remembered low comes up, per second
METER_STEADY = 0.02      # a swing smaller than this is a steady sound: two lights
METER_LOUD = 0.9         # from here the top light is amber
# Live's meter takes seconds to come down after the sound has gone. With the song stopped that
# is all there is to see, so then the lights only stay on while the level still goes up now and
# then (someone playing along), and go out at once otherwise.
METER_RISE_STEP = 0.005  # the level going up by this much counts as sound coming in
METER_HOLD = 0.25        # seconds the lights stay on after that, with the song stopped
HINT_SECONDS = 2.0       # how long 'move the fader up / down' stays on the knob lights

SYSEX = (0xF0, 0x00, 0x20, 0x29, 0x02, 0x11)
SET_LEDS, TEMPLATE_CHANGED = 0x78, 0x77

NEAR = 2 / 127.0         # a fader this close to the volume takes it over
JUMP = 6                 # a fader sends every step (measured: 1 at a time); more in one message is
                         # not the fader (another template with the same numbers) and is ignored


def columns_spec():
    """Group names per column, the family's core group first: [['DRUMS', 'PERC'], ['BASS'], ...]"""
    cols = [[] for _ in FADER_CCS]
    for g in spec.GROUPS:
        if g.solo and g.solo.isdigit() and 1 <= int(g.solo) <= len(cols):
            cols[int(g.solo) - 1].append(g)
    return [[g.name for g in sorted(c, key=lambda g: g.optional)] for c in cols]


COLUMNS = columns_spec()


def group_name(track_name):
    """The spec group a track name stands for, or None."""
    n = track_name.strip().lower()
    for g in spec.GROUPS:
        if n == g.name.lower() or n in g.aliases:
            return g.name
    return None


def db(param):
    try:
        return param.str_for_value(param.value)
    except Exception:
        return ''


class Surface:
    """`song` is called for the current song; `send` takes a tuple of MIDI bytes."""

    def __init__(self, song, send, message=lambda text: None, clock=time.monotonic):
        self.song, self.send, self.message, self.clock = song, send, message, clock
        self.leds = {}                       # led number -> color last sent
        new = lambda: dict(hw=None, set=None, told=False, hint=None, until=0)
        self.faders = [new() for _ in FADER_CCS]
        self.knobs = [new() for _ in AMB_CCS]
        self.parts_mode, self.page, self.playing_part = False, 0, None
        self.disarmed = []                   # the tracks Record Arm switched off last
        self.swing, self.swing_at = [None] * len(FADER_CCS), None      # (low, high) per column
        self.levels = [dict(last=0.0, rose=None) for _ in FADER_CCS]

    # --- finding the groups ---

    def columns(self):
        """Per column the top-level tracks of its groups, the core group first."""
        found = {}
        for t in self.song().tracks:
            if t.group_track is None:
                name = group_name(t.name)
                if name:
                    found.setdefault(name, []).append(t)
        return [[t for name in names for t in found.get(name, [])] for names in COLUMNS]

    def everything(self):
        song = self.song()
        return list(song.tracks) + list(song.return_tracks)

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

    def toggle(self, col, what):
        """Solo: on unless one of the family already is. Mute: on unless all of them already are."""
        tracks = self.columns()[col]
        if not tracks:
            return
        if what == 'solo':
            new = not any(t.solo for t in tracks)
        else:
            new = not all(t.mute for t in tracks)
        for t in tracks:
            setattr(t, what, new)

    def unsolo_all(self):
        for t in self.everything():
            if t.solo:
                t.solo = False

    def armed(self):
        return [t for t in self.song().tracks if getattr(t, 'can_be_armed', False) and t.arm]

    def arm_button(self):
        """Tracks armed: disarm them all. None armed: arm the ones this button disarmed last."""
        armed = self.armed()
        if armed:
            self.disarmed = armed
            for t in armed:
                t.arm = False
            return
        still_there = list(self.song().tracks)
        for t in self.disarmed:
            if t in still_there and t.can_be_armed:
                t.arm = True

    # --- parts of the song ---

    def parts(self):
        """(name, start in beats) of every part, in song order: the arrangement clips of the
        top-level track called Parts, or the locators when there is no such track."""
        song = self.song()
        for t in song.tracks:
            if t.group_track is None and t.name.strip().lower() == 'parts':
                found = [(c.name, c.start_time) for c in getattr(t, 'arrangement_clips', [])]
                break
        else:
            found = [(c.name, c.time) for c in getattr(song, 'cue_points', [])]
        return sorted(found, key=lambda part: part[1])

    def part_now(self, parts):
        """Index of the part the playhead is in, or None before the first one."""
        now = self.song().current_song_time
        inside = [i for i, (_, start) in enumerate(parts) if start <= now]
        return inside[-1] if inside else None

    def go_to_part(self, index):
        """Stopped: put the playhead on the start of the part. Playing: go to the same place in
        the bar before the part, so the beat goes on and the part starts on the next bar line."""
        parts, song = self.parts(), self.song()
        if index >= len(parts):
            return
        start = parts[index][1]
        if not song.is_playing:
            song.current_song_time = start
            return
        bar = song.signature_numerator * 4.0 / song.signature_denominator
        this_bar = int(song.current_song_time // bar) * bar
        song.jump_by(max(start - bar, start % bar) - this_bar)

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

    def heard(self):
        """The top-level tracks a solo lets through (themselves or something inside them soloed),
        or None when nothing is soloed."""
        soloed = [t for t in self.everything() if t.solo]
        if not soloed:
            return None
        tops = []
        for t in soloed:
            while getattr(t, 'group_track', None) is not None:
                t = t.group_track
            tops.append(t)
        return tops

    def colors(self):
        leds, heard, now = {}, self.heard(), self.clock()
        passed = 0.0 if self.swing_at is None else max(0.0, now - self.swing_at)
        self.swing_at = now
        stopped = not getattr(self.song(), 'is_playing', True)
        for i, tracks in enumerate(self.columns()):
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
            level = max(getattr(t, 'output_meter_level', 0) for t in tracks)
            seen = self.levels[i]
            if level > seen['last'] + METER_RISE_STEP:
                seen['rose'] = now
            seen['last'] = level
            fading = stopped and (seen['rose'] is None or now - seen['rose'] > METER_HOLD)
            if level < METER_FLOOR or fading:
                self.swing[i] = None
                continue
            low, high = self.swing[i] or (level, level)
            low, high = min(level, low + METER_RISE * passed), max(level, high - METER_FALL * passed)
            self.swing[i] = (low, high)
            where = 0.5 if high - low < METER_STEADY else (level - low) / (high - low)
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
            words = parts[index][0].lower().split()
            on, dim = PART_COLORS.get(words[0] if words else '', PART_OTHER)
            leds[led] = on if index == playing else dim
        return leds

    def refresh(self):
        """Send the lights that changed. Called after every press and ten times a second."""
        changed = [(k, v) for k, v in sorted(self.colors().items()) if self.leds.get(k) != v]
        if changed:
            self.leds.update(changed)
            self.send(SYSEX + (SET_LEDS, TEMPLATE) + tuple(b for kv in changed for b in kv) + (0xF7,))

    def lights_off(self):
        self.send(SYSEX + (SET_LEDS, TEMPLATE)
                  + tuple(b for k in sum(KNOB_LEDS, []) + SOLO_LEDS + MUTE_LEDS + [UNSOLO_LED] + sorted(SONG_LEDS.values()) + [PARTS_LED, UP_LED, ARM_LED]
                        for b in (k, OFF)) + (0xF7,))
        self.leds = {}
