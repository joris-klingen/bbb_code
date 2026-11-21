import unittest

import tests.test_lcxl as xl                    # the fake song, tracks and clips
from bbb import launchpad as lp

PARTS = xl.PARTS


def rig(*names):
    tracks = {n: xl.Track(n) for n in names}
    song = xl.Song(list(tracks.values()), [xl.Track('A-verb'), xl.Track('B-amb')])
    sent = []
    s = lp.Surface(lambda: song, sent.append, clock=lambda: s.now)
    s.now = 0.0
    return s, tracks, song, sent


def parts_rig(names=PARTS, colors=None):
    """A set with a Parts track: every part 4 bars of 4/4, so part i starts at beat 16 i."""
    s, t, song, sent = rig('Parts', 'DRUMS', 'BASS')
    clips = [xl.Clip(n, i * 16.0) for i, n in enumerate(names)]
    for clip, color in zip(clips, colors or [0x00FF00] * len(clips)):
        clip.color = color
    t['Parts'].arrangement_clips = clips[::-1]
    return s, t, song, sent


def press(s, number):
    """A pad (a note) or a round button (a controller), by its number."""
    kind = 0xB0 if number % 10 == 9 or number > 90 else 0x90
    s.receive((kind, number, 127))
    s.receive((kind, number, 0))


def leds(sent):
    """The lights as the device shows them after all messages."""
    state = {}
    for m in sent:
        if m[:7] == lp.SYSEX + (lp.SET_LEDS,):
            body = m[7:-1]
            for i in range(0, len(body), 5):
                state[body[i + 1]] = tuple(body[i + 2:i + 5])
    return state


class Device(unittest.TestCase):
    def test_pad_numbers(self):
        self.assertEqual((lp.pad(1, 1), lp.pad(1, 8), lp.pad(8, 1), lp.pad(8, 8)), (81, 88, 11, 18))
        self.assertEqual((lp.CLICK, lp.ARM, lp.UNSOLO, lp.UNMUTE), (59, 39, 29, 19))
        self.assertEqual((lp.PLAY, lp.STOP, lp.RECORD), (51, 52, 54))
        self.assertEqual(lp.SONG_PADS, {56: 'punch_in', 57: 'loop', 58: 'punch_out'})

    def test_start_takes_the_device_and_stop_gives_it_back(self):
        s, _, _, sent = rig('DRUMS')
        s.start()
        self.assertEqual(sent[0], (0xF0, 0x00, 0x20, 0x29, 0x02, 0x0D, 0x0E, 0x01, 0xF7))
        self.assertEqual(sent[1][:8], (0xF0, 0x00, 0x20, 0x29, 0x02, 0x0D, 0x03, 0x03))
        self.assertEqual(len(leds(sent)), 80)               # 64 pads and 16 round buttons
        s.start()                                           # plugged in again: everything once more
        self.assertEqual(sent[3], sent[1])
        s.stop()
        self.assertTrue(all(c == lp.OFF for c in leds(sent).values()))
        self.assertEqual(sent[-1], (0xF0, 0x00, 0x20, 0x29, 0x02, 0x0D, 0x0E, 0x00, 0xF7))

    def test_only_changes_are_sent_and_no_color_is_out_of_range(self):
        s, t, song, sent = parts_rig(colors=[0xFFFFFF, 0x000000, 0x123456, 0xFF0000] * 3)
        t['DRUMS'].arm = t['BASS'].solo = song.is_playing = True
        t['DRUMS'].output_meter_level = 1.0
        s.refresh()
        s.refresh()
        self.assertEqual(len(sent), 1)
        self.assertTrue(all(0 <= b <= 127 for b in sent[0][1:-1]))  # between the sysex start and end
        song.loop = True
        s.refresh()
        self.assertEqual(sent[1][7:-1], (3, 57) + lp.AMBER)

    def test_releases_and_other_channels_do_nothing(self):
        s, t, _, _ = rig('DRUMS')
        s.receive((0x90, lp.SOLO_PADS[0], 0))
        s.receive((0x80, lp.SOLO_PADS[0], 0))
        s.receive((0x91, lp.SOLO_PADS[0], 127))
        self.assertFalse(t['DRUMS'].solo)


class Parts(unittest.TestCase):
    def test_parts_in_clip_colors_bright_where_the_song_is(self):
        s, _, song, sent = parts_rig(PARTS, [0xFF0000, 0x00FF00, 0x804000, 0x000000] + [0x0000FF] * 6)
        song.current_song_time = 20.0                       # in 'verse 1'
        s.refresh()
        now = leds(sent)
        self.assertEqual([now[p] for p in lp.PART_PADS[:4]],
                         [(26, 0, 0), (0, 127, 0), (26, 13, 0), (26, 26, 26)])     # hue kept, black = grey
        self.assertEqual(now[lp.PART_PADS[9]], (0, 0, 26))
        self.assertEqual([now[p] for p in lp.PART_PADS[10:]], [lp.OFF] * 14)
        self.assertEqual((now[lp.LEFT], now[lp.RIGHT], now[lp.UP], now[lp.DOWN]),
                         (lp.WHITE_DIM, lp.WHITE_DIM, lp.OFF, lp.OFF))

    def test_a_press_goes_to_the_part(self):
        s, _, song, _ = parts_rig()
        press(s, lp.PART_PADS[1])
        self.assertEqual(song.current_song_time, 16.0)
        press(s, lp.PART_PADS[9])                           # second row: the outro
        self.assertEqual(song.current_song_time, 144.0)
        press(s, lp.PART_PADS[10])                          # no part there
        self.assertEqual(song.current_song_time, 144.0)
        song.is_playing, song.current_song_time = True, 21.5
        press(s, lp.PART_PADS[3])                           # chorus at 48: the bar before, same beat
        self.assertEqual(song.current_song_time, 45.5)

    def test_previous_and_next_part(self):
        s, _, song, _ = parts_rig()
        song.current_song_time = 20.0                       # in part 2
        press(s, lp.RIGHT)
        self.assertEqual(song.current_song_time, 32.0)
        press(s, lp.LEFT)
        press(s, lp.LEFT)
        press(s, lp.LEFT)                                   # there is nothing before the first
        self.assertEqual(song.current_song_time, 0.0)
        song.current_song_time = 150.0                      # in the last part
        press(s, lp.RIGHT)
        self.assertEqual(song.current_song_time, 150.0)

    def test_more_than_24_parts(self):
        s, _, song, sent = parts_rig(PARTS * 3)             # 30
        s.refresh()
        self.assertEqual((leds(sent)[lp.UP], leds(sent)[lp.DOWN]), (lp.OFF, lp.WHITE_DIM))
        press(s, lp.DOWN)
        press(s, lp.DOWN)
        now = leds(sent)
        self.assertEqual((now[lp.UP], now[lp.DOWN]), (lp.WHITE_DIM, lp.OFF))
        self.assertEqual([now[p] != lp.OFF for p in lp.PART_PADS[:8]], [True] * 6 + [False] * 2)
        press(s, lp.PART_PADS[5])                           # part 30
        self.assertEqual(song.current_song_time, 29 * 16.0)
        press(s, lp.UP)
        song.current_song_time = 28 * 16.0                  # the song plays on the other page
        s.refresh()
        self.assertEqual(leds(sent)[lp.PART_PADS[4]], (0, 127, 0))

    def test_locators_get_the_color_of_their_kind(self):
        s, _, song, sent = rig('DRUMS')
        song.cue_points = [xl.Locator('chorus', 32.0), xl.Locator('Verse1', 0.0), xl.Locator('bridge', 64.0)]
        s.refresh()
        now = leds(sent)
        self.assertEqual([now[p] for p in lp.PART_PADS[:3]], [(0, 127, 0), (26, 6, 0), (16, 9, 26)])


class Transport(unittest.TestCase):
    def test_play_stop_record(self):
        s, _, song, sent = rig('DRUMS')
        s.refresh()
        self.assertEqual((leds(sent)[lp.PLAY], leds(sent)[lp.STOP], leds(sent)[lp.RECORD]),
                         (lp.GREEN_DIM, lp.WHITE_DIM, lp.RED_DIM))
        press(s, lp.PLAY)
        press(s, lp.PLAY)                                   # already playing: nothing
        self.assertEqual((song.is_playing, song.started, leds(sent)[lp.PLAY]), (True, 1, lp.GREEN))
        press(s, lp.RECORD)
        self.assertEqual((song.record_mode, leds(sent)[lp.RECORD]), (True, lp.RED))
        press(s, lp.STOP)
        press(s, lp.RECORD)
        self.assertEqual((song.is_playing, song.record_mode), (False, False))

    def test_punch_loop_and_click(self):
        s, _, song, sent = rig('DRUMS')
        for number, what in [(56, 'punch_in'), (57, 'loop'), (58, 'punch_out'), (lp.CLICK, 'metronome')]:
            press(s, number)
            self.assertTrue(getattr(song, what), what)
            self.assertEqual(leds(sent)[number], lp.AMBER)
            press(s, number)
            self.assertEqual((getattr(song, what), leds(sent)[number]), (False, lp.AMBER_DIM))


class GroupRows(unittest.TestCase):
    def test_solo_and_mute_with_their_clear_buttons(self):
        s, t, song, sent = rig('DRUMS', 'PERC', 'BASS', 'fx')
        s.refresh()
        now = leds(sent)
        self.assertEqual(([now[p] for p in lp.SOLO_PADS[:3]], [now[p] for p in lp.MUTE_PADS[:3]]),
                         ([lp.BLUE_DIM, lp.BLUE_DIM, lp.OFF], [lp.MUTE_ON, lp.MUTE_ON, lp.OFF]))
        self.assertEqual((now[lp.UNSOLO], now[lp.UNMUTE], now[lp.ARM]), (lp.OFF, lp.OFF, lp.OFF))
        press(s, lp.SOLO_PADS[0])
        press(s, lp.MUTE_PADS[5])                           # column 6: the rest, here 'fx'
        now = leds(sent)
        self.assertTrue(t['DRUMS'].solo and t['PERC'].solo and t['fx'].mute)
        self.assertEqual((now[lp.SOLO_PADS[0]], now[lp.MUTE_PADS[0]], now[lp.MUTE_PADS[1]], now[lp.MUTE_PADS[5]]),
                         (lp.BLUE, lp.MUTE_ON, lp.MUTE_SILENCED, lp.OFF))
        self.assertEqual((now[lp.UNSOLO], now[lp.UNMUTE]), (lp.BLUE, lp.AMBER))
        song.return_tracks[0].mute = True
        press(s, lp.UNSOLO)
        press(s, lp.UNMUTE)
        self.assertFalse(any(x.solo or x.mute for x in song.tracks + song.return_tracks))
        self.assertEqual((leds(sent)[lp.UNSOLO], leds(sent)[lp.UNMUTE]), (lp.OFF, lp.OFF))

    def test_activity_green_with_the_signal_red_when_armed(self):
        s, t, song, sent = rig('DRUMS', 'BASS', 'KEYS')
        vox = xl.Track('rec', group_track=t['KEYS'])
        song.tracks.append(vox)
        song.is_playing = True
        pads = lambda: [leds(sent)[p] for p in lp.ACTIVITY_PADS[:4]]

        def play(track, *levels):
            for level in levels:
                s.now += 0.05
                t[track].output_meter_level = level
                s.refresh()

        s.refresh()
        self.assertEqual(pads(), [lp.OFF] * 4)              # silent, nothing armed
        play('DRUMS', 0.70, 0.74)                           # a hit: the top of the swing
        self.assertEqual(pads()[0], (0, 127, 0))
        play('DRUMS', 0.70)                                 # and it dies away
        self.assertEqual(pads()[0], (0, lp.ACTIVITY_LOW, 0))
        vox.arm = True                                      # a track inside KEYS
        s.refresh()
        self.assertEqual(pads()[2], (lp.ARMED_LOW, 0, 0))   # armed, silent: steady dim red
        self.assertEqual(leds(sent)[lp.ARM], lp.RED)
        play('KEYS', 0.50, 0.56)
        self.assertEqual(pads()[2], (127, 0, 0))
        play('KEYS', 0.52)
        self.assertEqual(pads()[2], (lp.ARMED_LOW, 0, 0))
        press(s, lp.ARM)                                    # disarm all
        self.assertEqual((vox.arm, pads()[2], leds(sent)[lp.ARM]), (False, (0, lp.ACTIVITY_LOW, 0), lp.OFF))
        press(s, lp.ARM)                                    # and arm again
        self.assertEqual((vox.arm, pads()[2][1]), (True, 0))


if __name__ == '__main__':
    unittest.main()
