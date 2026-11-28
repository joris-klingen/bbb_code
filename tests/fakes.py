"""Stand-ins for Live's song, tracks, clips and locators, for the controller tests."""


class Track:
    def __init__(self, name, group_track=None):
        self.name, self.group_track = name, group_track
        self.solo = self.mute = self.arm = False
        self.can_be_armed = True
        self.is_foldable = False                # True for a group track
        self.output_meter_level = 0.0


class Song:
    def __init__(self, tracks, returns=()):
        self.tracks, self.return_tracks = tracks, list(returns)
        self.loop = self.metronome = self.punch_in = self.punch_out = False
        self.is_playing, self.current_song_time, self.cue_points = False, 0.0, []
        self.signature_numerator, self.signature_denominator = 4, 4
        self.record_mode, self.started = False, 0
        self.tempo, self.time_listeners = 120.0, []

    def current_song_time_has_listener(self, f):
        return f in self.time_listeners

    def add_current_song_time_listener(self, f):
        self.time_listeners.append(f)

    def remove_current_song_time_listener(self, f):
        self.time_listeners.remove(f)

    def jump_by(self, beats):
        self.current_song_time += beats

    def start_playing(self):
        self.is_playing, self.started = True, self.started + 1

    def continue_playing(self):
        self.is_playing, self.continued = True, getattr(self, 'continued', 0) + 1

    def stop_playing(self):
        self.is_playing = False


class Clip:
    def __init__(self, name, start_time):
        self.name, self.start_time, self.color = name, start_time, 0x808080


class Locator:
    def __init__(self, name, time):
        self.name, self.time = name, time


PARTS = ['intro', 'verse 1', 'pre', 'chorus', 'verse 2', 'pre', 'chorus', 'bridge', 'chorus', 'outro']
