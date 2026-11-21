"""What the controller scripts share: the groups and song parts of a set, and what can be done
with them. Without Live and without a device: `lcxl.py` and `launchpad.py` put this on their
controls and lights, the tests run it on fakes.

Groups are the top-level tracks whose name stands for a group of spec.GROUPS (spec.group_named),
in eight columns by solo key: 1 DRUMS + PERC ... 8 BACKINGS. Column 6 is all the rest: GUIT ACC,
STRINGS and every other top-level track that is none of the groups (an FX track, say), but not
the helper tracks, the archive or an ignored group. Song parts are the arrangement clips
of the top-level track called Parts, or the locators when there is no such track.
"""
import time

try:
    from . import spec
except ImportError:      # pragma: no cover - only when loaded outside a package
    import spec

# Activity of a group, to see what is playing rather than how loud. Live's meter (0-1) moves
# only a little between the hits of a group, so activity is where the level is between the
# lowest and the highest of the last moments: 1 at the top of that swing, 0 at the bottom.
METER_FLOOR = 0.02       # below this: silence
METER_FALL = 0.2         # how fast the remembered high comes down, per second
METER_RISE = 0.4         # how fast the remembered low comes up, per second
METER_STEADY = 0.02      # a swing smaller than this is a steady sound: halfway
# Live's meter takes seconds to come down after the sound has gone. With the song stopped that
# is all there is to see, so then there is only activity while the level still goes up now and
# then (someone playing along).
METER_RISE_STEP = 0.005  # the level going up by this much counts as sound coming in
METER_HOLD = 0.25        # seconds of activity after that, with the song stopped


def columns_spec():
    """Group names per column, the family's core group first: [['DRUMS', 'PERC'], ['BASS'], ...]"""
    cols = [[] for _ in range(8)]
    for g in spec.GROUPS:
        if g.solo and g.solo.isdigit() and 1 <= int(g.solo) <= len(cols):
            cols[int(g.solo) - 1].append(g)
    return [[g.name for g in sorted(c, key=lambda g: g.optional)] for c in cols]


REST = 5                 # the column (counted from 0) for everything that is no group of another
REST_GROUPS = ['STRINGS']    # groups that spec gives another solo key, but belong with the rest
NOT_REST = ([name for name, _ in spec.HELPERS] + ['Parts'] + spec.LAST_GROUPS + spec.KEEP_NAMES_IN
            + spec.IGNORE_GROUPS)


def columns_rest(cols):
    cols = [[name for name in names if name not in REST_GROUPS] for names in cols]
    cols[REST] += REST_GROUPS
    return cols


COLUMNS = columns_rest(columns_spec())


def group_name(track_name):
    """The spec group a track name stands for, or None."""
    return spec.group_named(track_name)


class Groups:
    """`song` is called for the current song; `send` takes a tuple of MIDI bytes."""

    def __init__(self, song, send, message=lambda text: None, clock=time.monotonic):
        self.song, self.send, self.message, self.clock = song, send, message, clock
        self.disarmed = []                   # the tracks arm_button switched off last
        self.swing, self.swing_at = [None] * len(COLUMNS), None        # (low, high) per column
        self.levels = [dict(last=0.0, rose=None) for _ in COLUMNS]

    # --- the groups ---

    def columns(self):
        """Per column the top-level tracks of its groups, the core group first. Column REST
        ends with the top-level tracks that are no group at all."""
        found, rest = {}, []
        known = [name for names in COLUMNS for name in names]
        skip = [name.lower() for name in NOT_REST]
        for t in self.song().tracks:
            if t.group_track is None:
                name = group_name(t.name)
                if name in known:
                    found.setdefault(name, []).append(t)
                elif name is None and t.name.strip().lower() not in skip:
                    rest.append(t)
        cols = [[t for name in names for t in found.get(name, [])] for names in COLUMNS]
        cols[REST] += rest
        return cols

    def everything(self):
        song = self.song()
        return list(song.tracks) + list(song.return_tracks)

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

    def unmute_all(self):
        for t in self.everything():
            if t.mute:
                t.mute = False

    def heard(self):
        """The top-level tracks a solo lets through (themselves or something inside them soloed),
        or None when nothing is soloed."""
        soloed = [t for t in self.everything() if t.solo]
        return [self.top(t) for t in soloed] if soloed else None

    @staticmethod
    def top(t):
        """The top-level track t is in (t itself when it is in no group)."""
        while getattr(t, 'group_track', None) is not None:
            t = t.group_track
        return t

    # --- record arm ---

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
        """(name, start in beats, color) of every part, in song order. The color is the clip's,
        as Live gives it (0xRRGGBB), or None for a locator."""
        song = self.song()
        for t in song.tracks:
            if t.group_track is None and t.name.strip().lower() == 'parts':
                found = [(c.name, c.start_time, getattr(c, 'color', None))
                         for c in getattr(t, 'arrangement_clips', [])]
                break
        else:
            found = [(c.name, c.time, None) for c in getattr(song, 'cue_points', [])]
        return sorted(found, key=lambda part: part[1])

    def part_now(self, parts):
        """Index of the part the playhead is in, or None before the first one."""
        now = self.song().current_song_time
        inside = [i for i, part in enumerate(parts) if part[1] <= now]
        return inside[-1] if inside else None

    def go_to_part(self, index):
        """Stopped: put the playhead on the start of the part. Playing: go to the same place in
        the bar before the part, so the beat goes on and the part starts on the next bar line."""
        parts, song = self.parts(), self.song()
        if not 0 <= index < len(parts):
            return
        start = parts[index][1]
        if not song.is_playing:
            song.current_song_time = start
            return
        bar = song.signature_numerator * 4.0 / song.signature_denominator
        this_bar = int(song.current_song_time // bar) * bar
        song.jump_by(max(start - bar, start % bar) - this_bar)

    def step_part(self, step):
        """To the part after (1) or before (-1) the one the playhead is in."""
        now = self.part_now(self.parts())
        self.go_to_part(max(0, (-1 if now is None else now) + step))

    # --- activity ---

    def activity(self, columns):
        """Per column None (no group, or silent) or (where, level): where the level is in the
        swing of the last moments, 0-1, and the level itself. Call it at every refresh."""
        now = self.clock()
        passed = 0.0 if self.swing_at is None else max(0.0, now - self.swing_at)
        self.swing_at = now
        stopped = not getattr(self.song(), 'is_playing', True)
        out = []
        for i, tracks in enumerate(columns):
            if not tracks:
                out.append(None)
                continue
            level = max(getattr(t, 'output_meter_level', 0) for t in tracks)
            seen = self.levels[i]
            if level > seen['last'] + METER_RISE_STEP:
                seen['rose'] = now
            seen['last'] = level
            fading = stopped and (seen['rose'] is None or now - seen['rose'] > METER_HOLD)
            if level < METER_FLOOR or fading:
                self.swing[i] = None
                out.append(None)
                continue
            low, high = self.swing[i] or (level, level)
            low, high = min(level, low + METER_RISE * passed), max(level, high - METER_FALL * passed)
            self.swing[i] = (low, high)
            out.append((0.5 if high - low < METER_STEADY else (level - low) / (high - low), level))
        return out
