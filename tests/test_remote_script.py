"""The part Live loads, run against a stand-in for Live: both installed scripts start, map their
controls, take MIDI, refresh and stop without an error."""
import importlib
import os
import sys
import tempfile
import types
import unittest

import tests.test_lcxl as xl
from bbb import install_remote


class Instance:
    """What Live hands a script."""
    def __init__(self, sent):
        self.sent = sent

    def send_midi(self, data):
        self.sent.append(tuple(data))

    def handle(self):
        return 1


def stand_in_for_live(song, forwarded, logged):
    live = types.ModuleType('Live')
    class Timer:
        """Live.Base.Timer: calls back on its own, here when the test says so."""
        made = []

        def __init__(self, callback, interval, repeat):
            self.callback, self.running = callback, False
            Timer.made.append(self)

        def start(self):
            self.running = True

        def stop(self):
            self.running = False

    live.Base = types.SimpleNamespace(Timer=Timer)
    live.MidiMap = types.SimpleNamespace(
        forward_midi_cc=lambda script, handle, channel, cc: forwarded.append(('cc', channel, cc)),
        forward_midi_note=lambda script, handle, channel, note: forwarded.append(('note', channel, note)))
    framework = types.ModuleType('_Framework')
    control_surface = types.ModuleType('_Framework.ControlSurface')

    class ControlSurface:
        def __init__(self, c_instance):
            self._c_instance = c_instance

        def song(self):
            return song

        def log_message(self, text):
            logged.append(text)

        def show_message(self, text):
            pass

        def build_midi_map(self, handle):
            pass

        def refresh_state(self):
            pass

        def update_display(self):
            pass

        def disconnect(self):
            pass

    control_surface.ControlSurface = ControlSurface
    return {'Live': live, '_Framework': framework, '_Framework.ControlSurface': control_surface}


class Track(xl.Track):
    """With the listeners Live's tracks have."""
    def __init__(self, name):
        super().__init__(name)
        self.listeners = []

    def output_meter_level_has_listener(self, f):
        return f in self.listeners

    def add_output_meter_level_listener(self, f):
        self.listeners.append(f)

    def remove_output_meter_level_listener(self, f):
        self.listeners.remove(f)


class RemoteScript(unittest.TestCase):
    def test_both_scripts_run(self):
        for package, press in [('BBB_Groups', (0x97, 41, 127)), ('BBB_Launchpad', (0x90, 21, 127))]:
            drums = Track('DRUMS')
            song = xl.Song([drums, Track('Parts')], [Track('A-amb')])
            sent, forwarded, logged = [], [], []
            fakes = stand_in_for_live(song, forwarded, logged)
            with tempfile.TemporaryDirectory() as d:
                install_remote.install(d)
                sys.modules.update(fakes)
                sys.path.insert(0, d)
                try:
                    script = importlib.import_module(package).create_instance(Instance(sent))
                    script.build_midi_map(None)
                    script.refresh_state()
                    script.receive_midi(press)                      # solo, first column
                    script.receive_midi_chunk([press[:2] + (0,)])
                    for _ in range(12):
                        script.update_display()
                    self.assertEqual(len(drums.listeners), 1)
                    drums.output_meter_level = 0.5
                    drums.listeners[0]()                            # Live: the level moved
                    (timer,) = fakes['Live'].Base.Timer.made
                    self.assertTrue(timer.running)
                    timer.callback()                                # and the timer for the bar line
                    script.disconnect()
                finally:
                    sys.path.remove(d)
                    for name in [m for m in sys.modules if m.split('.')[0] == package] + list(fakes):
                        del sys.modules[name]
            self.assertEqual(logged, [logged[0]], package)          # its name, and no errors
            self.assertTrue(drums.solo, package)
            self.assertEqual(drums.listeners, [], package)
            self.assertFalse(timer.running, package)
            self.assertTrue(sent and forwarded, package)
            self.assertIn(('note', press[0] & 15, press[1]), forwarded, package)


if __name__ == '__main__':
    unittest.main()
