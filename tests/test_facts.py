import unittest

from bbb import facts
from tests.fixture import SetBuilder, messy_set


class Facts(unittest.TestCase):
    def test_messy_set(self):
        f = facts.facts(messy_set().root)
        self.assertEqual((f['tempo'], f['time_signature'], f['length']), (120.0, '4/4', 48.0))
        self.assertEqual([(s['name'], s['bar'], s['bars'], s['color']) for s in f['sections']],
                         [('intro', 1, 4, 17), ('verse', 5, 4, 23), ('chorus', 9, 4, 14)])
        self.assertEqual(f['locators'], [{'time': 16.0, 'name': 'verse 1'}])
        self.assertEqual(f['samples'], ['Samples/vox 1.wav'])
        rec = next(t for t in f['tracks'] if t['name'] == 'rec')
        self.assertEqual((rec['depth'], rec['clips'], rec['take_lanes']), (2, 1, 4))
        kit = next(t for t in f['tracks'] if t['name'] == '17-Kontakt 7')
        self.assertEqual(kit['devices'], ['Kontakt 7'])

    def test_time_signatures(self):
        for value, sig in [(201, (4, 4)), (200, (3, 4)), (302, (6, 8)), (202, (5, 4)), (204, (7, 4))]:
            self.assertEqual(facts.time_signature(SetBuilder(signature=value).root), sig)

    def test_bars_follow_the_time_signature(self):
        b = SetBuilder(signature=302)   # 6/8: a bar is 3 quarter notes
        parts = b.track('Midi', 'PARTS')
        b.midi_clip(b.arrangement(parts), 6, 12, name='verse')
        (s,) = facts.sections(b.root)
        self.assertEqual((s['bar'], s['bars']), (3, 4))

    def test_no_parts_track(self):
        f = facts.facts(SetBuilder().root)
        self.assertEqual((f['sections'], f['parts_track'], f['length']), ([], False, None))


if __name__ == '__main__':
    unittest.main()
