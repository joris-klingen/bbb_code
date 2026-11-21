"""The part Live loads, the same for every controller: `python3 -m bbb.install_remote` installs it
as `Remote Scripts/<name>/__init__.py`, next to `device.py` (which controller this is: `lcxl.py`
or `launchpad.py`), `groups.py` and `spec.py`.

Everything the controls do is in those; this only passes MIDI in and out.
"""
import time

import Live
from _Framework.ControlSurface import ControlSurface

from . import device


class BBBGroups(ControlSurface):

    def __init__(self, c_instance):
        super().__init__(c_instance)
        self._surface = device.Surface(self.song, self._to_device, self.show_message)
        self._surface.log = lambda text: self.log_message('%s: %s' % (device.NAME, text))
        self._ticks, self._lit, self._timer = 0, 0.0, None
        self.log_message(device.NAME)
        self.show_message(device.NAME)
        self._safely(self._surface.start)
        self._safely(self._start_timer)

    def _start_timer(self):
        """Live calls a script ten times a second, and its listeners may not change the song.
        Going to a part on the bar line needs to act within a few hundredths of a second, so
        that gets a timer of its own."""
        self._timer = Live.Base.Timer(callback=self._timer_tick, interval=10, repeat=True)
        self._timer.start()

    def _timer_tick(self):
        try:
            self._surface.tick()
        except Exception as e:      # not a hundred lines a second in the log: leave it to
            self.log_message('%s: timer stopped: %r' % (device.NAME, e))    # update_display
            self._timer.stop()

    def _tick(self):
        self._safely(self._surface.tick)

    def _to_device(self, data):
        self._c_instance.send_midi(tuple(data))

    def _safely(self, do, *args):
        try:
            do(*args)
        except Exception as e:      # a set in an odd state must not take the script down
            self.log_message('%s: %r' % (device.NAME, e))

    def build_midi_map(self, midi_map_handle):
        super().build_midi_map(midi_map_handle)
        script = self._c_instance.handle()
        for channel, cc in device.FORWARD_CCS:
            Live.MidiMap.forward_midi_cc(script, midi_map_handle, channel, cc)
        for channel, note in device.FORWARD_NOTES:
            Live.MidiMap.forward_midi_note(script, midi_map_handle, channel, note)

    def receive_midi(self, midi_bytes):
        self._safely(self._surface.receive, midi_bytes)

    def receive_midi_chunk(self, midi_chunk):
        for midi_bytes in midi_chunk:
            self.receive_midi(midi_bytes)

    def refresh_state(self):
        """Live calls this when the device may have been away (ports changed, plugged in)."""
        super().refresh_state()
        self._safely(self._surface.start)

    def update_display(self):
        super().update_display()
        self._tick()                            # also here, should the timer not run
        self._safely(self._surface.refresh)     # ten times a second: what was done in Live
        self._ticks += 1
        if self._ticks % 10 == 1:
            self._safely(self._watch_meters)

    def _watch_meters(self):
        """Have Live tell when the level of a group changes, so the activity lights can move
        faster than ten times a second."""
        for column in self._surface.columns():
            for t in column:
                if not t.output_meter_level_has_listener(self._meter_moved):
                    t.add_output_meter_level_listener(self._meter_moved)

    def _meter_moved(self):
        now = time.monotonic()
        if now - self._lit >= 0.015:            # at most some sixty times a second
            self._lit = now
            self._safely(self._surface.refresh)

    def _unwatch_meters(self):
        for t in self.song().tracks:
            if t.output_meter_level_has_listener(self._meter_moved):
                t.remove_output_meter_level_listener(self._meter_moved)

    def disconnect(self):
        if self._timer is not None:
            self._safely(self._timer.stop)
        self._safely(self._unwatch_meters)
        self._safely(self._surface.stop)
        super().disconnect()


def create_instance(c_instance):
    return BBBGroups(c_instance)
