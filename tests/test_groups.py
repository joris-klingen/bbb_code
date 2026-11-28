"""What groups.py does for the controller, run through the Launchpad: which tracks are the
groups, solo and mute, going to a part on the bar line, disarm and arm again, and the install."""
import importlib
import os
import sys
import tempfile
import unittest

from bbb import groups, install_remote, launchpad as lp
from tests import fakes
from tests.fakes import Track
from tests.test_launchpad import leds, press


def rig(*names):
    tracks = {n: Track(n) for n in names}
    song = fakes.Song(list(tracks.values()), [Track('A-verb'), Track('B-amb')])
    sent, said = [], []
    s = lp.Surface(lambda: song, sent.append, said.append, clock=lambda: s.now)
    s.now = 0.0
    return s, tracks, song, sent, said


def parts_rig(names=fakes.PARTS, bars=4):
    """A set with a Parts track: every part `bars` bars of 4/4, so part i starts at beat 16 i."""
    s, t, song, sent, _ = rig('Parts', 'DRUMS', 'BASS')
    t['Parts'].arrangement_clips = [fakes.Clip(n, i * bars * 4.0) for i, n in enumerate(names)][::-1]
    return s, t, song, sent


class Columns(unittest.TestCase):
    def test_columns_follow_the_solo_keys(self):
        self.assertEqual(groups.COLUMNS, [['DRUMS', 'PERC'], ['BASS'], ['KEYS', 'PIANO'],
                                          ['SYNTHS'], ['GUIT'], ['GUIT ACC', 'STRINGS'],
                                          ['VOX LEAD'], ['BACKINGS']])

    def test_column_six_is_all_the_rest(self):
        s, t, song, _, _ = rig('length', 'Parts', 'FX', 'DRUMS', 'strings', 'bass synth', 'acc guitar',
                               'ARCHIVE', 'old', 'live rig', 'rec')
        for name in t:
            t[name].is_foldable = name not in ('length', 'Parts', 'strings', 'rec')    # groups
        song.tracks.append(Track('vox fx', group_track=t['DRUMS']))     # inside a group: not top level
        cols = s.columns()
        self.assertEqual([x.name for x in cols[5]], ['acc guitar', 'strings', 'FX', 'bass synth'])
        self.assertEqual([[x.name for x in c] for c in cols[:5] + cols[6:]],
                         [['DRUMS'], [], [], [], [], [], []])
        press(s, lp.SOLO_PADS[5])
        self.assertTrue(all(t[n].solo for n in ['acc guitar', 'strings', 'FX', 'bass synth']))
        self.assertFalse(t['ARCHIVE'].solo or t['Parts'].solo or t['live rig'].solo or t['old'].solo)
        self.assertFalse(t['rec'].solo)                     # a loose track is not 'the rest'

    def test_groups_by_name_and_alias_top_level_only(self):
        s, t, song, _, _ = rig('drums live', 'PERC', 'Vocals', 'length')
        song.tracks.append(Track('bass', group_track=t['drums live']))   # a bass inside DRUMS
        cols = s.columns()
        self.assertEqual([x.name for x in cols[0]], ['drums live', 'PERC'])
        self.assertEqual(cols[1], [])
        self.assertEqual([x.name for x in cols[6]], ['Vocals'])


class Names(unittest.TestCase):
    def test_groups_by_their_words(self):
        for name, group in [
            ('Vocals', 'VOX LEAD'), ('vocs', 'VOX LEAD'), ('Lead Vox', 'VOX LEAD'), ('VOX 2', 'VOX LEAD'),
            ('zang', 'VOX LEAD'), ('Vocals group', 'VOX LEAD'),
            ('BVs', 'BACKINGS'), ('backing vocals', 'BACKINGS'), ('Vox - Back', 'BACKINGS'), ('koor', 'BACKINGS'),
            ('Drum Kit', 'DRUMS'), ('DRUMS BUS', 'DRUMS'), ('drums live', 'DRUMS'), ('Percussion', 'PERC'),
            ('Bas', 'BASS'), ('Keyboards', 'KEYS'), ('Pno', 'PIANO'), ('Synth', 'SYNTHS'), ('juno', 'SYNTHS'),
            ('Gtr', 'GUIT'), ('Electric Guitars', 'GUIT'), ('guitar rythm', 'GUIT'),
            ('Acoustic Gtr', 'GUIT ACC'), ('gitaar akoestisch', 'GUIT ACC'),
        ]:
            self.assertEqual(groups.group_name(name), group, name)

    def test_not_a_group(self):
        for name in ['bass synth', 'vox fx', 'lead', 'acoustic', 'Parts', 'length', 'live rig',
                     'drums room', 'group', '', '12', 'guitar solo']:
            self.assertIsNone(groups.group_name(name), name)

    def test_kinds_of_parts(self):
        from bbb import spec
        for name, kind in [
            ('verse', 'verse'), ('Verse2', 'verse'), ('VERSE 1a', 'verse'), ('v3', 'verse'), ('couplet 2', 'verse'),
            ('chorus', 'chorus'), ('last chorus', 'chorus'), ('Chorus (double)', 'chorus'), ('refrein', 'chorus'),
            ('hook', 'chorus'), ('C2', 'chorus'),
            ('intro', 'intro'), ('Intro 2', 'intro'), ('outro', 'outro'), ('ending', 'outro'),
            ('pre', None), ('pre-chorus', None), ('Pre Chorus 2', None), ('post chorus', None),
            ('bridge', None), ('solo', None), ('break', None), ('', None),
        ]:
            self.assertEqual(spec.part_kind(name), kind, name)

    def test_restyle_still_only_knows_the_exact_names(self):
        from bbb import restyle
        self.assertIsNone(restyle._group('vocs'))
        self.assertEqual(restyle._group('vocals').name, 'VOX LEAD')


class Buttons(unittest.TestCase):
    def test_solo_takes_the_family_and_adds_up(self):
        s, t, _, _, _ = rig('DRUMS', 'PERC', 'BASS')
        press(s, lp.SOLO_PADS[0])
        press(s, lp.SOLO_PADS[1])
        self.assertTrue(t['DRUMS'].solo and t['PERC'].solo and t['BASS'].solo)
        press(s, lp.SOLO_PADS[0])
        self.assertEqual((t['DRUMS'].solo, t['PERC'].solo, t['BASS'].solo), (False, False, True))

    def test_mute(self):
        s, t, _, _, _ = rig('DRUMS', 'PERC')
        t['PERC'].mute = True
        press(s, lp.MUTE_PADS[0])               # one was still on: all off
        self.assertTrue(t['DRUMS'].mute and t['PERC'].mute)
        press(s, lp.MUTE_PADS[0])
        self.assertFalse(t['DRUMS'].mute or t['PERC'].mute)

    def test_unsolo_all_also_tracks_inside_groups_and_returns(self):
        s, t, song, _, _ = rig('DRUMS', 'BASS')
        kick = Track('kick', group_track=t['DRUMS'])
        song.tracks.append(kick)
        kick.solo = t['BASS'].solo = song.return_tracks[0].solo = True
        press(s, lp.UNSOLO)
        self.assertFalse(any(x.solo for x in song.tracks + song.return_tracks))

    def test_a_missing_group_and_other_channels_do_nothing(self):
        s, t, _, _, _ = rig('DRUMS')
        press(s, lp.SOLO_PADS[5])
        s.receive((0x91, lp.SOLO_PADS[0], 127))             # channel 2
        self.assertFalse(t['DRUMS'].solo)


class Parts(unittest.TestCase):
    def play_to(self, s, song, beat):
        """The song plays on to `beat` (at 120: 2 beats a second), Live calling 20 times a second."""
        while song.current_song_time < beat - 1e-9:
            song.current_song_time = min(beat, song.current_song_time + 0.1)
            s.now += 0.05
            s.tick()
            s.refresh()

    def test_while_playing_the_part_waits_for_the_bar_line(self):
        s, _, song, sent = parts_rig()
        song.is_playing, song.current_song_time = True, 21.5    # beat 2.5 of a bar in verse 1
        press(s, lp.PART_PADS[3])                       # chorus, at 48
        self.assertEqual(song.current_song_time, 21.5)  # not yet
        self.play_to(s, song, 23.8)
        self.assertEqual(round(song.current_song_time, 6), 23.8)
        seen = set()
        for _ in range(8):                              # the pad of the chorus blinks meanwhile
            s.now += 0.05
            s.leds = {}
            s.refresh()
            seen.add(leds(sent)[lp.PART_PADS[3]])
        self.assertEqual(seen, {lp.part_color(0x808080, 'chorus', True), lp.OFF})
        self.play_to(s, song, 23.9)                     # the last call before the line at 24
        self.assertEqual(round(song.current_song_time, 6), 47.9)        # as far before the chorus
        self.play_to(s, song, 52.0)
        self.assertEqual(round(song.current_song_time, 6), 52.0)        # and it goes only once

    def test_pressing_again_keeps_it_waiting_and_another_part_takes_over(self):
        s, _, song, _ = parts_rig()
        song.is_playing, song.current_song_time = True, 21.5
        press(s, lp.PART_PADS[3])
        press(s, lp.PART_PADS[3])                       # an impatient second press changes nothing
        press(s, lp.PART_PADS[0])                       # the intro instead, at 0: nothing before it
        self.play_to(s, song, 23.8)
        song.current_song_time = 23.9                   # the last call before the line at 24
        s.now += 0.05
        s.tick()
        self.assertEqual(round(song.current_song_time, 6), 0.0)

    def test_a_missed_bar_line_still_goes_and_stays_in_time(self):
        s, _, song, _ = parts_rig()
        song.is_playing, song.current_song_time = True, 21.5
        press(s, lp.PART_PADS[3])                       # chorus at 48, to go at the line at 24
        self.play_to(s, song, 23.7)
        song.current_song_time = 24.2                   # Live was busy: the next call is past the line
        s.now += 0.25
        s.tick()
        self.assertEqual(round(song.current_song_time, 6), 48.2)        # as far into the chorus

    def test_a_refused_jump_is_tried_again(self):
        s, _, song, _ = parts_rig()
        song.is_playing, song.current_song_time = True, 23.95
        jump, song.jump_by = song.jump_by, lambda beats: (_ for _ in ()).throw(RuntimeError('not from here'))
        with self.assertRaises(RuntimeError):
            press(s, lp.PART_PADS[3])                   # Live refuses the change
        song.jump_by = jump
        s.now += 0.01
        s.tick()
        self.assertEqual(round(song.current_song_time, 6), 47.95)

    def test_stopping_while_it_waits_goes_there_at_once(self):
        s, _, song, _ = parts_rig()
        song.is_playing, song.current_song_time = True, 21.5
        press(s, lp.PART_PADS[3])
        song.is_playing = False
        s.tick()
        self.assertEqual(song.current_song_time, 48.0)

    def test_three_four_time(self):
        s, _, song, _ = parts_rig(bars=3)               # parts start every 12 beats
        song.signature_numerator = 3
        song.is_playing, song.current_song_time = True, 14.0    # beat 3 of a 3/4 bar
        press(s, lp.PART_PADS[2])                       # 'pre' at 24
        self.play_to(s, song, 14.9)                     # the line is at 15
        self.assertEqual(round(song.current_song_time, 6), 23.9)

    def test_left_and_right_step_through_the_parts(self):
        s, _, song, _ = parts_rig()
        song.current_song_time = 20.0                   # in verse 1
        press(s, lp.RIGHT)
        self.assertEqual(song.current_song_time, 32.0)
        press(s, lp.LEFT)
        press(s, lp.LEFT)
        self.assertEqual(song.current_song_time, 0.0)

    def test_locators_when_there_is_no_parts_track(self):
        s, _, song, _, _ = rig('DRUMS')
        song.cue_points = [fakes.Locator('chorus', 32.0), fakes.Locator('verse', 0.0)]
        press(s, lp.PART_PADS[1])
        self.assertEqual(song.current_song_time, 32.0)


class Arm(unittest.TestCase):
    def test_disarm_all_and_arm_them_again(self):
        s, t, song, sent, _ = rig('DRUMS', 'BASS', 'KEYS')
        vox = Track('vox', group_track=t['KEYS'])
        song.tracks.append(vox)
        t['DRUMS'].can_be_armed = False                 # a group
        light = lambda: leds(sent)[lp.ARM]
        press(s, lp.ARM)                                # nothing armed, nothing to bring back
        self.assertEqual(light(), lp.OFF)
        t['BASS'].arm = vox.arm = True                  # armed in Live
        s.refresh()
        self.assertEqual(light(), lp.RED)
        press(s, lp.ARM)
        self.assertEqual((t['BASS'].arm, vox.arm, light()), (False, False, lp.OFF))
        press(s, lp.ARM)
        self.assertEqual((t['BASS'].arm, vox.arm, t['KEYS'].arm, light()), (True, True, False, lp.RED))
        press(s, lp.ARM)
        song.tracks.remove(vox)                         # deleted in the meantime
        press(s, lp.ARM)
        self.assertEqual((t['BASS'].arm, vox.arm), (True, False))

    def test_a_greyed_out_arm_button_that_is_on_counts_too(self):
        class Input:
            def __init__(self, display_name):
                self.display_name = display_name

        class NoArm(Track):                             # a group: Live raises when asked
            arm = property(lambda self: (_ for _ in ()).throw(RuntimeError('no arm state')),
                           lambda self, on: None)

        class Greyed(Track):                            # no input: Live will not change its arm
            def __init__(self, name, inputs):
                super().__init__(name)
                self.available_input_routing_types = [Input(n) for n in inputs]
                self.input_routing_type = self.available_input_routing_types[-1]
                self.routed = []

            def __setattr__(self, name, value):
                if name == 'input_routing_type' and 'routed' in self.__dict__:
                    self.routed.append(value.display_name)
                if name == 'arm' and 'routed' in self.__dict__ and self.input_routing_type.display_name == 'No Input':
                    raise RuntimeError('Track cannot be armed')
                super().__setattr__(name, value)

        s, t, song, sent, said = rig('KEYS')
        logged = []
        s.log = logged.append
        group = NoArm('GUIT')
        bass, stuck = Greyed('bass', ['Ext. In', 'Resampling', 'No Input']), Greyed('stuck', ['No Input'])
        song.tracks[:0] = [group, bass, stuck]
        bass.__dict__['arm'] = stuck.__dict__['arm'] = True
        t['KEYS'].arm = True
        s.refresh()
        self.assertEqual(leds(sent)[lp.ARM], lp.RED)
        press(s, lp.ARM)
        self.assertEqual((bass.arm, t['KEYS'].arm, stuck.arm), (False, False, True))
        self.assertEqual(bass.routed, ['Ext. In', 'No Input'])          # another input, and back
        self.assertEqual(said, ['Live will not disarm: stuck'])
        self.assertEqual(len(logged), 2)                                # what Live said, for both
        self.assertIn("disarm 'bass': done", logged[0])
        self.assertIn("disarm 'stuck': NOT done", logged[1])
        stuck.__dict__['arm'] = False
        press(s, lp.ARM)                                                # and armed again, the same way
        self.assertEqual((bass.arm, t['KEYS'].arm, bass.input_routing_type.display_name), (True, True, 'No Input'))

    def test_only_the_last_ones_come_back(self):
        s, t, _, _, _ = rig('DRUMS', 'BASS')
        t['DRUMS'].arm = True
        press(s, lp.ARM)
        t['BASS'].arm = True                            # armed by hand after that
        press(s, lp.ARM)
        press(s, lp.ARM)
        self.assertEqual((t['DRUMS'].arm, t['BASS'].arm), (False, True))


class Install(unittest.TestCase):
    def test_install_copies_a_loadable_package(self):
        with tempfile.TemporaryDirectory() as d:
            (pad,) = install_remote.install(d)
            self.assertEqual(os.listdir(d), ['BBB_Launchpad'])
            self.assertEqual(sorted(os.listdir(pad)),
                             ['__init__.py', 'device.py', 'groups.py', 'launchpad.py', 'spec.py'])
            for name in os.listdir(pad):            # Live cannot load a script with a syntax error
                with open(os.path.join(pad, name)) as f:
                    compile(f.read(), name, 'exec')
            with open(os.path.join(pad, '__init__.py')) as f:
                self.assertIn('def create_instance', f.read())

    def test_the_installed_package_loads_without_live(self):
        """All but __init__.py, which needs Live: device.py and what it imports."""
        with tempfile.TemporaryDirectory() as d:
            for folder in install_remote.install(d):
                os.remove(os.path.join(folder, '__init__.py'))
                open(os.path.join(folder, '__init__.py'), 'w').close()
            sys.path.insert(0, d)
            try:
                device = importlib.import_module('BBB_Launchpad.device')
                self.assertTrue(device.NAME and device.FORWARD_NOTES and device.FORWARD_CCS)
                self.assertTrue(callable(device.Surface))
            finally:
                sys.path.remove(d)
                for name in [m for m in sys.modules if m.split('.')[0] == 'BBB_Launchpad']:
                    del sys.modules[name]


if __name__ == '__main__':
    unittest.main()
