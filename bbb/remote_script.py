"""The part Live loads: installed as `Remote Scripts/BBB_Groups/__init__.py` by
`python3 -m bbb.install_remote`, next to copies of `lcxl.py` and `spec.py`.

Everything the controls do is in `lcxl.py`; this only passes MIDI in and out.
"""
import time

import Live
from _Framework.ControlSurface import ControlSurface

from . import lcxl


class BBBGroups(ControlSurface):

    def __init__(self, c_instance):
        super().__init__(c_instance)
        self._surface = lcxl.Surface(self.song, self._to_device, self.show_message)
        self.log_message('BBB Groups: %s' % ' | '.join('+'.join(c) for c in lcxl.COLUMNS))
        self._ticks, self._lit = 0, 0.0
        self.show_message('BBB Groups: Launch Control XL on %s' % lcxl.TEMPLATE_NAME)
        self._safely(self._surface.refresh)

    def _to_device(self, data):
        self._c_instance.send_midi(tuple(data))

    def _safely(self, do, *args):
        try:
            do(*args)
        except Exception as e:      # a set in an odd state must not take the script down
            self.log_message('BBB Groups: %r' % (e,))

    def build_midi_map(self, midi_map_handle):
        super().build_midi_map(midi_map_handle)
        script = self._c_instance.handle()
        for cc in lcxl.FADER_CCS + lcxl.AMB_CCS:
            Live.MidiMap.forward_midi_cc(script, midi_map_handle, lcxl.CHANNEL, cc)
        buttons = [lcxl.UNSOLO_NOTE, lcxl.PARTS_NOTE, lcxl.UP_NOTE, lcxl.ARM_NOTE] + list(lcxl.SONG_NOTES)
        for note in lcxl.SOLO_NOTES + lcxl.MUTE_NOTES + buttons:
            Live.MidiMap.forward_midi_note(script, midi_map_handle, lcxl.CHANNEL, note)

    def receive_midi(self, midi_bytes):
        self._safely(self._surface.receive, midi_bytes)

    def receive_midi_chunk(self, midi_chunk):
        for midi_bytes in midi_chunk:
            self.receive_midi(midi_bytes)

    def update_display(self):
        super().update_display()
        self._safely(self._surface.refresh)     # ten times a second: solo / mute done in Live
        self._ticks += 1
        if self._ticks % 10 == 1:
            self._safely(self._watch_meters)

    def _watch_meters(self):
        """Have Live tell when the level of a group changes, so the meter lights can move faster
        than ten times a second."""
        for column in self._surface.columns():
            for t in column:
                if not t.output_meter_level_has_listener(self._meter_moved):
                    t.add_output_meter_level_listener(self._meter_moved)

    def _meter_moved(self):
        now = time.monotonic()
        if now - self._lit >= 0.03:             # at most some thirty times a second
            self._lit = now
            self._safely(self._surface.refresh)

    def _unwatch_meters(self):
        for t in self.song().tracks:
            if t.output_meter_level_has_listener(self._meter_moved):
                t.remove_output_meter_level_listener(self._meter_moved)

    def disconnect(self):
        self._safely(self._unwatch_meters)
        self._safely(self._surface.lights_off)
        super().disconnect()


def create_instance(c_instance):
    return BBBGroups(c_instance)
