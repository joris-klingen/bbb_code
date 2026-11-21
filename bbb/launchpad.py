"""Launchpad Mini MK3 for moving around a set while mixing: what every pad does, without Live.

Rows from top to bottom, columns 1-8 = the groups (groups.py), the round buttons at the right
next to their row:

    top buttons   up / down = other parts (more than 24), left / right = previous / next part
    row 1-2       the parts of the song, in the color of their clip; a press goes to the part
    row 3         empty (parts 17-24 in a long song)
    row 4         play, stop, -, record, -, punch in, loop, punch out          | click
    row 5         empty
    row 6         activity: green with the signal; red when a track in it is armed | disarm all / arm again
    row 7         solo (blue)                                                  | unsolo all
    row 8         mute (amber = on, dark = muted)                              | unmute all

The device is put in Programmer mode (and given back when Live closes); it has to be connected
through its MIDI port ("LPMiniMK3 MIDI"), not the DAW port. See PLAN-launchpad.md.

This module only needs objects that look like Live's song and tracks, so the tests run it on
fakes; `remote_script.py` is the part that Live loads.
"""
import time

try:
    from . import groups, spec
except ImportError:      # pragma: no cover - only when loaded outside a package
    import groups
    import spec

NAME = 'BBB Groups: Launchpad Mini'

SYSEX = (0xF0, 0x00, 0x20, 0x29, 0x02, 0x0D)
PROGRAMMER_MODE, LIVE_MODE = SYSEX + (0x0E, 0x01, 0xF7), SYSEX + (0x0E, 0x00, 0xF7)
SET_LEDS, RGB = 0x03, 0x03       # one message for many lights: (RGB, light, r, g, b) each, 0-127


def pad(row, col):
    """The number of a pad (a note) or, with col 9, of the round button at the right of that
    row (a controller); row 1 is the top row. It is also the number of its light."""
    return 10 * (9 - row) + col


COLS = range(1, 9)
PART_PADS = [pad(row, col) for row in (1, 2, 3) for col in COLS]
PLAY, STOP, RECORD = pad(4, 1), pad(4, 2), pad(4, 4)
SONG_PADS = {pad(4, 6): 'punch_in', pad(4, 7): 'loop', pad(4, 8): 'punch_out'}
ACTIVITY_PADS = [pad(6, col) for col in COLS]
SOLO_PADS = [pad(7, col) for col in COLS]
MUTE_PADS = [pad(8, col) for col in COLS]
CLICK, ARM, UNSOLO, UNMUTE = pad(4, 9), pad(6, 9), pad(7, 9), pad(8, 9)
UP, DOWN, LEFT, RIGHT = 91, 92, 93, 94          # the round buttons above the pads
LIGHTS = ([pad(row, col) for row in range(1, 9) for col in range(1, 10)] + list(range(91, 99)))

OFF = (0, 0, 0)
GREEN, GREEN_DIM = (0, 127, 0), (0, 14, 0)
RED, RED_DIM = (127, 0, 0), (18, 0, 0)
AMBER, AMBER_DIM = (127, 70, 0), (18, 10, 0)
BLUE, BLUE_DIM = (10, 40, 127), (0, 5, 22)
WHITE_DIM = (16, 16, 16)
MUTE_ON, MUTE_SILENCED = (90, 50, 0), (16, 9, 0)    # heard / silenced by a solo elsewhere
# Parts: the color of the clip, as bright as it goes where the song is, dimmed elsewhere.
PART_BRIGHT, PART_DIM = 127, 26
# A locator has no color: by the kind of part (spec.part_kind), None = everything else.
KIND_COLORS = {'verse': (0, 255, 0), 'chorus': (255, 60, 0), 'intro': (120, 150, 190),
               'outro': (120, 150, 190), None: (160, 90, 255)}
# Activity: from this brightness (silent but armed, or the bottom of the swing) to full.
ACTIVITY_LOW, ARMED_LOW = 6, 18


def part_color(color, name, playing):
    """(r, g, b) for a part: its clip color (0xRRGGBB) or, without one, the color of its kind,
    brought to the brightness for playing or not playing while keeping the hue."""
    if color is None:
        r, g, b = KIND_COLORS[spec.part_kind(name)]
    else:
        r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    top = max(r, g, b)
    if top == 0:
        r = g = b = top = 1         # a black clip: grey, so the pad is still there
    full = PART_BRIGHT if playing else PART_DIM
    return tuple(max(1 if x else 0, int(round(x * full / float(top)))) for x in (r, g, b))


class Surface(groups.Groups):

    def __init__(self, song, send, message=lambda text: None, clock=time.monotonic):
        super().__init__(song, send, message, clock)
        self.leds = {}                       # light -> (r, g, b) last sent
        self.page, self.playing_part = 0, None

    # --- from the device ---

    def receive(self, data):
        data = tuple(data)
        if len(data) != 3 or data[0] & 0x0F or not data[2]:    # presses only, on channel 1
            return
        kind, number = data[0] & 0xF0, data[1]
        if kind == 0x90:
            self.pad(number)
        elif kind == 0xB0:
            self.button(number)
        else:
            return
        self.refresh()

    def pad(self, number):
        song = self.song()
        if number in PART_PADS:
            self.go_to_part(self.page * len(PART_PADS) + PART_PADS.index(number))
        elif number in SOLO_PADS:
            self.toggle(SOLO_PADS.index(number), 'solo')
        elif number in MUTE_PADS:
            self.toggle(MUTE_PADS.index(number), 'mute')
        elif number == PLAY:
            if not song.is_playing:
                song.start_playing()
        elif number == STOP:
            song.stop_playing()
        elif number == RECORD:
            song.record_mode = not song.record_mode
        elif number in SONG_PADS:
            what = SONG_PADS[number]
            setattr(song, what, not getattr(song, what))

    def button(self, number):
        song = self.song()
        if number == CLICK:
            song.metronome = not song.metronome
        elif number == ARM:
            self.arm_button()
        elif number == UNSOLO:
            self.unsolo_all()
        elif number == UNMUTE:
            self.unmute_all()
        elif number in (LEFT, RIGHT):
            self.step_part(1 if number == RIGHT else -1)
        elif number in (UP, DOWN):
            self.page = min(self.pages() - 1, max(0, self.page + (1 if number == DOWN else -1)))

    def pages(self):
        return max(1, -(-len(self.parts()) // len(PART_PADS)))

    # --- to the device ---

    def colors(self):
        leds, song = dict.fromkeys(LIGHTS, OFF), self.song()
        # parts
        parts, size = self.parts(), len(PART_PADS)
        playing = self.part_now(parts)
        if playing != self.playing_part:         # the song moved on: show the page it is on
            self.playing_part = playing
            if playing is not None:
                self.page = playing // size
        self.page = min(self.page, self.pages() - 1)
        for i, led in enumerate(PART_PADS):
            index = self.page * size + i
            if index < len(parts):
                name, _, color = parts[index]
                leds[led] = part_color(color, name, index == playing)
        if parts:
            leds[LEFT] = leds[RIGHT] = WHITE_DIM
        leds[UP] = WHITE_DIM if self.page else OFF
        leds[DOWN] = WHITE_DIM if self.page + 1 < self.pages() else OFF
        # transport
        leds[PLAY] = GREEN if song.is_playing else GREEN_DIM
        leds[STOP] = WHITE_DIM
        leds[RECORD] = RED if song.record_mode else RED_DIM
        for led, what in SONG_PADS.items():
            leds[led] = AMBER if getattr(song, what) else AMBER_DIM
        leds[CLICK] = AMBER if song.metronome else AMBER_DIM
        # groups
        everything, heard, armed = self.everything(), self.heard(), self.armed()
        armed_in = [self.top(t) for t in armed]
        columns = self.columns()
        for i, (tracks, activity) in enumerate(zip(columns, self.activity(columns))):
            if not tracks:
                continue
            leds[SOLO_PADS[i]] = BLUE if any(t.solo for t in tracks) else BLUE_DIM
            if all(t.mute for t in tracks):
                leds[MUTE_PADS[i]] = OFF
            elif heard is not None and not any(t in heard for t in tracks):
                leds[MUTE_PADS[i]] = MUTE_SILENCED
            else:
                leds[MUTE_PADS[i]] = MUTE_ON
            if any(t in armed_in for t in tracks):       # red, also when silent
                level = ARMED_LOW if activity is None else ARMED_LOW + (127 - ARMED_LOW) * activity[0]
                leds[ACTIVITY_PADS[i]] = (int(round(level)), 0, 0)
            elif activity is not None:
                leds[ACTIVITY_PADS[i]] = (0, int(round(ACTIVITY_LOW + (127 - ACTIVITY_LOW) * activity[0])), 0)
        leds[ARM] = RED if armed else OFF
        leds[UNSOLO] = BLUE if heard is not None else OFF
        leds[UNMUTE] = AMBER if any(t.mute for t in everything) else OFF
        return leds

    def refresh(self):
        """Send the lights that changed. Called after every press and when levels move."""
        changed = [(k, v) for k, v in sorted(self.colors().items()) if self.leds.get(k) != v]
        if changed:
            self.leds.update(changed)
            self.send(SYSEX + (SET_LEDS,) + tuple(b for k, v in changed for b in (RGB, k) + v) + (0xF7,))

    def start(self):
        """Take the device: Programmer mode, and light everything."""
        self.send(PROGRAMMER_MODE)
        self.leds = {}
        self.refresh()

    def stop(self):
        """Lights off and give the device back."""
        self.send(SYSEX + (SET_LEDS,) + tuple(b for k in LIGHTS for b in (RGB, k) + OFF) + (0xF7,))
        self.leds = {}
        self.send(LIVE_MODE)


# What Live has to pass on to the script: (channel, number).
FORWARD_NOTES = [(0, pad(row, col)) for row in range(1, 9) for col in COLS]
FORWARD_CCS = [(0, pad(row, 9)) for row in range(1, 9)] + [(0, cc) for cc in range(91, 99)]
