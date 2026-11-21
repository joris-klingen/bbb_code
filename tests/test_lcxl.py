import os
import tempfile
import unittest

from bbb import install_remote, lcxl

CH = lcxl.CHANNEL


class Param:
    min, max = 0.0, 1.0

    def __init__(self, value=0.85):
        self.value = value

    def str_for_value(self, v):
        return '%.2f' % v


class Mixer:
    def __init__(self):
        self.volume = Param()
        self.sends = [Param(0.0), Param(0.0)]       # to A-verb and B-amb


class Track:
    def __init__(self, name, group_track=None):
        self.name, self.group_track = name, group_track
        self.solo = self.mute = self.arm = False
        self.can_be_armed = True
        self.output_meter_level = 0.0
        self.mixer_device = Mixer()


class Song:
    def __init__(self, tracks, returns=()):
        self.tracks, self.return_tracks = tracks, list(returns)
        self.loop = self.metronome = self.punch_in = self.punch_out = False
        self.is_playing, self.current_song_time, self.cue_points = False, 0.0, []
        self.signature_numerator, self.signature_denominator = 4, 4

    def jump_by(self, beats):
        self.current_song_time += beats


def rig(*names):
    tracks = {n: Track(n) for n in names}
    song = Song(list(tracks.values()), [Track('A-verb'), Track('B-amb')])
    sent, said = [], []
    s = lcxl.Surface(lambda: song, sent.append, said.append, clock=lambda: s.now)
    s.now = 0.0
    return s, tracks, song, sent, said


def press(s, note):
    s.receive((0x90 | CH, note, 127))
    s.receive((0x80 | CH, note, 0))


def leds(sent):
    """The lights as the device shows them after all messages."""
    state = {}
    for m in sent:
        body = m[8:-1]
        state.update(zip(body[0::2], body[1::2]))
    return state


class Columns(unittest.TestCase):
    def test_columns_follow_the_solo_keys(self):
        self.assertEqual(lcxl.COLUMNS, [['DRUMS', 'PERC'], ['BASS'], ['KEYS', 'PIANO'],
                                        ['SYNTHS', 'STRINGS'], ['GUIT'], ['GUIT ACC'],
                                        ['VOX LEAD'], ['BACKINGS']])

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
            self.assertEqual(lcxl.group_name(name), group, name)

    def test_not_a_group(self):
        for name in ['bass synth', 'vox fx', 'lead', 'acoustic', 'Parts', 'length', 'live rig',
                     'drums room', 'group', '', '12', 'guitar solo']:
            self.assertIsNone(lcxl.group_name(name), name)

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
        press(s, lcxl.SOLO_NOTES[0])
        press(s, lcxl.SOLO_NOTES[1])
        self.assertTrue(t['DRUMS'].solo and t['PERC'].solo and t['BASS'].solo)
        press(s, lcxl.SOLO_NOTES[0])
        self.assertEqual((t['DRUMS'].solo, t['PERC'].solo, t['BASS'].solo), (False, False, True))

    def test_mute(self):
        s, t, _, _, _ = rig('DRUMS', 'PERC')
        t['PERC'].mute = True
        press(s, lcxl.MUTE_NOTES[0])            # one was still on: all off
        self.assertTrue(t['DRUMS'].mute and t['PERC'].mute)
        press(s, lcxl.MUTE_NOTES[0])
        self.assertFalse(t['DRUMS'].mute or t['PERC'].mute)

    def test_unsolo_all_also_tracks_inside_groups_and_returns(self):
        s, t, song, _, _ = rig('DRUMS', 'BASS')
        kick = Track('kick', group_track=t['DRUMS'])
        song.tracks.append(kick)
        kick.solo = t['BASS'].solo = song.return_tracks[0].solo = True
        press(s, lcxl.UNSOLO_NOTE)
        self.assertFalse(any(x.solo for x in song.tracks + song.return_tracks))

    def test_a_missing_group_and_other_channels_do_nothing(self):
        s, t, _, _, _ = rig('DRUMS')
        press(s, lcxl.SOLO_NOTES[5])
        s.receive((0x90 | 8, lcxl.SOLO_NOTES[0], 127))      # Factory template 1: the lights
        s.receive((0xB0 | 8, lcxl.FADER_CCS[0], 0))
        self.assertFalse(t['DRUMS'].solo)
        self.assertEqual(t['DRUMS'].mixer_device.volume.value, 0.85)


class Faders(unittest.TestCase):
    def jump(self, s, col, *values):
        for v in values:
            s.receive((0xB0 | CH, lcxl.FADER_CCS[col], v))

    def move(self, s, col, *values):
        """As a hand does it: the fader passes the values in between."""
        for v in values:
            last = s.faders[col]['hw']
            steps = [] if last is None else list(range(last, v, 4 if v > last else -4))[1:]
            self.jump(s, col, *(steps + [v]))

    def test_no_jump_until_the_fader_reaches_the_volume(self):
        s, t, _, _, said = rig('DRUMS', 'PERC')
        vol = t['DRUMS'].mixer_device.volume
        self.move(s, 0, 10, 40, 80)
        self.assertEqual(vol.value, 0.85)
        self.assertEqual(said, ['DRUMS is at 0.85: move the fader up to take over'])
        self.move(s, 0, 110)                    # past 0.85 (108): taken over
        self.assertAlmostEqual(vol.value, 110 / 127)
        self.move(s, 0, 64)
        self.assertAlmostEqual(vol.value, 64 / 127)
        self.assertEqual(t['PERC'].mixer_device.volume.value, 0.85)     # only the core group

    def test_a_jump_is_not_the_fader_and_moves_nothing(self):
        s, t, _, _, _ = rig('DRUMS')
        vol = t['DRUMS'].mixer_device.volume
        self.move(s, 0, 108, 100)               # following the fader
        self.jump(s, 0, 127, 0)                 # a button with the fader's number: 127, then 0
        self.assertAlmostEqual(vol.value, 100 / 127)
        self.jump(s, 0, 127, 0, 127, 0)
        self.assertAlmostEqual(vol.value, 100 / 127)

    def test_a_fader_close_to_the_volume_takes_over_at_once(self):
        s, t, _, _, said = rig('BASS')
        self.move(s, 1, 107)
        self.assertAlmostEqual(t['BASS'].mixer_device.volume.value, 107 / 127)
        self.assertEqual(said, [])

    def test_volume_changed_in_live_has_to_be_reached_again(self):
        s, t, _, _, _ = rig('BASS')
        vol = t['BASS'].mixer_device.volume
        self.move(s, 1, 108, 100)
        vol.value = 0.3                         # moved with the mouse
        self.move(s, 1, 90)
        self.assertEqual(vol.value, 0.3)
        self.move(s, 1, 30)
        self.assertAlmostEqual(vol.value, 30 / 127)


class Amb(unittest.TestCase):
    def turn(self, s, col, *values):
        for v in values:
            s.receive((0xB0 | CH, lcxl.AMB_CCS[col], v))

    def test_top_knob_sets_the_send_to_the_amb_return(self):
        s, t, _, _, _ = rig('DRUMS', 'PERC')
        self.turn(s, 0, 0, 1, 2, 40)            # the knob starts where the send is: it follows
        verb, amb = t['DRUMS'].mixer_device.sends
        self.assertEqual((verb.value, round(amb.value * 127)), (0.0, 40))
        self.assertEqual(t['PERC'].mixer_device.sends[1].value, 0.0)    # only the core group
        self.assertEqual(t['DRUMS'].mixer_device.volume.value, 0.85)

    def test_the_knob_has_to_reach_the_send_first(self):
        s, t, _, sent, said = rig('BASS')
        amb = t['BASS'].mixer_device.sends[1]
        amb.value = 0.5
        self.turn(s, 1, 100, 90)
        self.assertEqual(amb.value, 0.5)
        self.assertEqual(said, ['BASS amb is at 0.50: turn the knob down to take over'])
        self.assertEqual(leds(sent)[lcxl.KNOB_LEDS[2][1]], lcxl.RED)    # low light: down
        self.turn(s, 1, 70, 60)
        self.assertAlmostEqual(amb.value, 60 / 127)

    def test_no_amb_return_or_no_group_does_nothing(self):
        s, t, song, _, _ = rig('BASS')
        song.return_tracks = [Track('A-verb')]
        self.turn(s, 1, 0, 30)
        self.turn(s, 5, 0, 30)
        self.assertEqual([p.value for p in t['BASS'].mixer_device.sends], [0.0, 0.0])


class SongButtons(unittest.TestCase):
    def test_loop_click_and_punch(self):
        s, _, song, sent, _ = rig('DRUMS')
        for note, what in [(101, 'loop'), (102, 'metronome'), (107, 'punch_in'), (108, 'punch_out')]:
            press(s, note)
            self.assertTrue(getattr(song, what), what)
            self.assertEqual(leds(sent)[lcxl.SONG_LEDS[what]], lcxl.YELLOW)
            press(s, note)
            self.assertFalse(getattr(song, what), what)
            self.assertEqual(leds(sent)[lcxl.SONG_LEDS[what]], lcxl.OFF)

    def test_lights_follow_live(self):
        s, _, song, sent, _ = rig('DRUMS')
        s.refresh()
        song.metronome = True                   # switched on in Live
        s.refresh()
        self.assertEqual(sent[1][8:-1], (41, lcxl.YELLOW))


class Clip:
    def __init__(self, name, start_time):
        self.name, self.start_time = name, start_time


class Locator:
    def __init__(self, name, time):
        self.name, self.time = name, time


PARTS = ['intro', 'verse 1', 'pre', 'chorus', 'verse 2', 'pre', 'chorus', 'bridge', 'chorus', 'outro']


def parts_rig(names=PARTS, bars=4):
    """A set with a Parts track: every part `bars` bars of 4/4, so part i starts at beat 16 i."""
    s, t, song, sent, said = rig('Parts', 'DRUMS', 'BASS')
    t['Parts'].arrangement_clips = [Clip(n, i * bars * 4.0) for i, n in enumerate(names)][::-1]
    return s, t, song, sent


class Parts(unittest.TestCase):
    top = staticmethod(lambda sent: [leds(sent)[k] for k in lcxl.SOLO_LEDS])
    bottom = staticmethod(lambda sent: [leds(sent)[k] for k in lcxl.MUTE_LEDS])

    def test_mute_button_switches_both_rows(self):
        s, t, song, sent = parts_rig()
        press(s, lcxl.MUTE_NOTES[1])
        self.assertTrue(t['BASS'].mute)
        press(s, lcxl.PARTS_NOTE)
        self.assertEqual(leds(sent)[lcxl.PARTS_LED], lcxl.YELLOW)
        press(s, lcxl.SOLO_NOTES[1])                    # now: go to 'verse 1', part 2
        self.assertEqual(song.current_song_time, 16.0)
        press(s, lcxl.MUTE_NOTES[1])                    # the outro, part 10
        self.assertEqual(song.current_song_time, 144.0)
        self.assertEqual((t['BASS'].solo, t['BASS'].mute), (False, True))   # left alone
        press(s, lcxl.PARTS_NOTE)
        self.assertEqual(self.top(sent)[:3], [lcxl.YELLOW_DIM, lcxl.YELLOW_DIM, lcxl.OFF])
        self.assertEqual(self.bottom(sent)[:3], [lcxl.GREEN, lcxl.RED, lcxl.OFF])
        self.assertEqual(leds(sent)[lcxl.PARTS_LED], lcxl.OFF)

    def test_colors_by_kind_of_part_and_bright_where_the_song_is(self):
        s, _, song, sent = parts_rig()
        song.current_song_time = 50.0                   # in the first chorus (48-64)
        press(s, lcxl.PARTS_NOTE)
        self.assertEqual(self.top(sent), [lcxl.LIME_DIM, lcxl.GREEN_DIM, lcxl.AMBER_DIM, lcxl.RED,
                                          lcxl.GREEN_DIM, lcxl.AMBER_DIM, lcxl.RED_DIM, lcxl.AMBER_DIM])
        self.assertEqual(self.bottom(sent), [lcxl.RED_DIM, lcxl.LIME_DIM] + [lcxl.OFF] * 6)

    def test_up_shows_the_other_parts_and_the_rows_follow_the_song(self):
        s, _, song, sent = parts_rig(PARTS * 2)         # 20 parts: 16 and 4
        press(s, lcxl.UP_NOTE)                          # the rows show solo and mute: nothing
        press(s, lcxl.PARTS_NOTE)
        self.assertEqual(self.top(sent)[0], lcxl.YELLOW)                # the intro, where the song is
        self.assertEqual(leds(sent)[lcxl.UP_LED], lcxl.YELLOW)          # there are more parts
        press(s, lcxl.UP_NOTE)
        self.assertEqual(self.top(sent)[:5], [lcxl.RED_DIM, lcxl.AMBER_DIM, lcxl.RED_DIM, lcxl.LIME_DIM, lcxl.OFF])
        self.assertEqual(self.bottom(sent), [lcxl.OFF] * 8)
        press(s, lcxl.SOLO_NOTES[3])                    # the last outro, part 20
        self.assertEqual(song.current_song_time, 304.0)
        press(s, lcxl.SOLO_NOTES[4])                    # no part there
        self.assertEqual(song.current_song_time, 304.0)
        press(s, lcxl.UP_NOTE)
        self.assertEqual(self.top(sent)[0], lcxl.LIME_DIM)
        song.current_song_time = 290.0                  # playback is in part 19, a chorus
        s.refresh()
        self.assertEqual(self.top(sent)[:4], [lcxl.RED_DIM, lcxl.AMBER_DIM, lcxl.RED, lcxl.LIME_DIM])

    def test_while_playing_the_part_starts_on_the_next_bar_line(self):
        s, _, song, _ = parts_rig()
        song.is_playing, song.current_song_time = True, 21.5    # beat 2.5 of a bar in verse 1
        press(s, lcxl.PARTS_NOTE)
        press(s, lcxl.SOLO_NOTES[3])                    # chorus at 48: the bar before it, same beat
        self.assertEqual(song.current_song_time, 45.5)
        press(s, lcxl.SOLO_NOTES[0])                    # intro at 0: no bar before it
        self.assertEqual(song.current_song_time, 1.5)

    def test_three_four_time(self):
        s, _, song, _ = parts_rig(bars=3)               # parts start every 12 beats
        song.signature_numerator = 3
        song.is_playing, song.current_song_time = True, 14.0    # beat 3 of a 3/4 bar
        press(s, lcxl.PARTS_NOTE)
        press(s, lcxl.SOLO_NOTES[2])                    # 'pre' at 24
        self.assertEqual(song.current_song_time, 23.0)

    def test_locators_when_there_is_no_parts_track(self):
        s, _, song, sent, _ = rig('DRUMS')
        song.cue_points = [Locator('chorus', 32.0), Locator('verse', 0.0)]
        press(s, lcxl.PARTS_NOTE)
        self.assertEqual(self.top(sent)[:3], [lcxl.GREEN, lcxl.RED_DIM, lcxl.OFF])
        press(s, lcxl.SOLO_NOTES[1])
        self.assertEqual(song.current_song_time, 32.0)


class Arm(unittest.TestCase):
    def test_disarm_all_and_arm_them_again(self):
        s, t, song, sent, _ = rig('DRUMS', 'BASS', 'KEYS')
        vox = Track('vox', group_track=t['KEYS'])
        song.tracks.append(vox)
        t['DRUMS'].can_be_armed = False                 # a group
        light = lambda: leds(sent)[lcxl.ARM_LED]
        press(s, lcxl.ARM_NOTE)                         # nothing armed, nothing to bring back
        self.assertEqual(light(), lcxl.OFF)
        t['BASS'].arm = vox.arm = True                  # armed in Live
        s.refresh()
        self.assertEqual(light(), lcxl.YELLOW)
        press(s, lcxl.ARM_NOTE)
        self.assertEqual((t['BASS'].arm, vox.arm, light()), (False, False, lcxl.OFF))
        press(s, lcxl.ARM_NOTE)
        self.assertEqual((t['BASS'].arm, vox.arm, t['KEYS'].arm, light()), (True, True, False, lcxl.YELLOW))
        press(s, lcxl.ARM_NOTE)
        song.tracks.remove(vox)                         # deleted in the meantime
        press(s, lcxl.ARM_NOTE)
        self.assertEqual((t['BASS'].arm, vox.arm), (True, False))

    def test_only_the_last_ones_come_back(self):
        s, t, _, _, _ = rig('DRUMS', 'BASS')
        t['DRUMS'].arm = True
        press(s, lcxl.ARM_NOTE)
        t['BASS'].arm = True                            # armed by hand after that
        press(s, lcxl.ARM_NOTE)
        press(s, lcxl.ARM_NOTE)
        self.assertEqual((t['DRUMS'].arm, t['BASS'].arm), (False, True))


class Lights(unittest.TestCase):
    def test_lights_follow_the_set_and_only_changes_are_sent(self):
        s, t, _, sent, _ = rig('DRUMS', 'BASS')
        s.refresh()
        self.assertEqual(sent[0][:8], lcxl.SYSEX + (lcxl.SET_LEDS, lcxl.TEMPLATE))
        self.assertEqual(sent[0][-1], 0xF7)
        now = leds(sent)
        self.assertEqual((now[24], now[32], now[25], now[26], now[34], now[42]),
                         (lcxl.YELLOW_DIM, lcxl.GREEN, lcxl.YELLOW_DIM, lcxl.OFF, lcxl.OFF, lcxl.OFF))
        s.refresh()
        self.assertEqual(len(sent), 1)
        t['BASS'].solo = t['DRUMS'].mute = True         # done in Live
        s.refresh()
        self.assertEqual(sent[1][8:-1], (25, lcxl.YELLOW, 32, lcxl.RED, 42, lcxl.YELLOW))

    def test_dim_green_where_a_solo_silences_the_group(self):
        s, t, song, sent, _ = rig('DRUMS', 'BASS', 'KEYS')
        kick = Track('kick', group_track=t['DRUMS'])
        song.tracks.append(kick)
        kick.solo = True                                # inside DRUMS: DRUMS is still heard
        s.refresh()
        now = leds(sent)
        self.assertEqual((now[32], now[33], now[34]), (lcxl.GREEN, lcxl.GREEN_DIM, lcxl.GREEN_DIM))
        self.assertEqual((now[24], now[42]), (lcxl.YELLOW_DIM, lcxl.YELLOW))

    def test_meter_dances_between_the_low_and_high_of_the_last_moments(self):
        s, t, song, sent, _ = rig('DRUMS', 'PERC', 'BASS')
        song.is_playing = True
        column = lambda i: tuple(leds(sent)[row[i]] for row in lcxl.KNOB_LEDS)     # top, mid, low
        G, A, O = lcxl.GREEN, lcxl.AMBER, lcxl.OFF

        def play(track, *levels):
            seen = []
            for level in levels:
                s.now += 0.05
                t[track].output_meter_level = level
                s.refresh()
                seen.append(column(1 if track == 'BASS' else 0))
            return seen

        # a small swing high in Live's meter uses all the lights: hit, die away, hit
        self.assertEqual(play('BASS', 0.70, 0.74, 0.72, 0.70, 0.74, 0.71),
                         [(O, G, G), (G, G, G), (O, G, G), (O, O, G), (G, G, G), (O, O, G)])
        self.assertEqual(play('BASS', 0.0, 0.0), [(O, O, O), (O, O, O)])        # silence
        self.assertEqual(play('BASS', 0.3, 0.3, 0.3)[-1], (O, G, G))            # a steady sound
        self.assertEqual(play('PERC', 0.90, 0.96)[-1], (A, G, G))               # loud: amber on top
        self.assertEqual(column(2), (O, O, O))                                  # no KEYS in the set

    def test_song_stopped_the_lights_go_out_while_lives_meter_still_comes_down(self):
        s, t, song, sent, _ = rig('BASS')
        column = lambda: tuple(leds(sent)[row[1]] for row in lcxl.KNOB_LEDS)
        dark = (lcxl.OFF, lcxl.OFF, lcxl.OFF)

        def play(*levels):
            for level in levels:
                s.now += 0.05
                t['BASS'].output_meter_level = level
                s.refresh()
            return column()

        song.is_playing = True
        self.assertNotEqual(play(0.70, 0.74, 0.72, 0.70, 0.68, 0.66, 0.64, 0.62, 0.60), dark)
        song.is_playing = False                         # stop: the meter is still on its way down
        self.assertEqual(play(0.58), dark)
        self.assertEqual(play(0.50, 0.40, 0.30), dark)
        self.assertNotEqual(play(0.45), dark)           # someone plays a note with the song stopped
        self.assertNotEqual(play(0.44, 0.43, 0.42), dark)
        self.assertEqual(play(0.41, 0.40, 0.39, 0.38), dark)    # and lets it ring out

    def test_fader_hint_replaces_the_meter_for_a_moment(self):
        s, t, song, sent, _ = rig('DRUMS', 'BASS')
        song.is_playing = True
        t['DRUMS'].output_meter_level = 0.6
        column = lambda i: tuple(leds(sent)[row[i]] for row in lcxl.KNOB_LEDS)
        s.receive((0xB0 | CH, lcxl.FADER_CCS[0], 20))   # below the volume: move up
        self.assertEqual(column(0), (lcxl.RED, lcxl.OFF, lcxl.OFF))
        t['BASS'].mixer_device.volume.value = 0.2
        s.receive((0xB0 | CH, lcxl.FADER_CCS[1], 100))  # above: move down
        self.assertEqual(column(1), (lcxl.OFF, lcxl.OFF, lcxl.RED))
        s.now = lcxl.HINT_SECONDS + 0.1
        s.refresh()
        self.assertEqual(column(0), (lcxl.OFF, lcxl.GREEN, lcxl.GREEN))
        s.now = 0.0
        s.receive((0xB0 | CH, lcxl.FADER_CCS[0], 20))
        s.receive((0xB0 | CH, lcxl.FADER_CCS[0], 109))  # reached: the meter is back at once
        self.assertEqual(column(0), (lcxl.OFF, lcxl.GREEN, lcxl.GREEN))

    def test_coming_back_to_the_template_lights_everything_again(self):
        s, _, _, sent, _ = rig('DRUMS')
        s.refresh()
        s.receive(lcxl.SYSEX + (lcxl.TEMPLATE_CHANGED, 8, 0xF7))
        self.assertEqual(len(sent), 1)
        s.receive(lcxl.SYSEX + (lcxl.TEMPLATE_CHANGED, lcxl.TEMPLATE, 0xF7))
        self.assertEqual(sent[1], sent[0])


class Template(unittest.TestCase):
    FILE = os.path.join(os.path.dirname(__file__), '..', 'templates', 'Novation LCXL',
                        'bbb_groups_for_user_8.syx')

    @unittest.skipUnless(os.path.exists(FILE), 'the template file is not here')
    def test_the_template_file_sends_what_the_script_listens_for(self):
        with open(self.FILE, 'rb') as f:
            data = f.read()
        rec = [data[8 + 6 * i: 14 + 6 * i] for i in range(56)]      # knobs, faders, buttons
        self.assertEqual([(r[0], r[4]) for r in rec[24:32]], [(cc, CH) for cc in lcxl.FADER_CCS])
        notes = lcxl.SOLO_NOTES + lcxl.MUTE_NOTES
        self.assertEqual([(r[0], r[1], r[4], r[5]) for r in rec[32:48]], [(0, n, 0, CH) for n in notes])
        self.assertEqual(tuple(rec[50]), (0, lcxl.UNSOLO_NOTE, 0, 127, 0, CH))  # Solo: third on the right


class Install(unittest.TestCase):
    def test_install_copies_a_loadable_package(self):
        with tempfile.TemporaryDirectory() as d:
            target = install_remote.install(os.path.join(d, 'BBB_Groups'))
            self.assertEqual(sorted(os.listdir(target)), ['__init__.py', 'lcxl.py', 'spec.py'])
            with open(os.path.join(target, '__init__.py')) as f:
                source = f.read()
            self.assertIn('def create_instance', source)
            compile(source, '__init__.py', 'exec')      # Live cannot load a script with a syntax error


if __name__ == '__main__':
    unittest.main()
