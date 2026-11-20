import os
import pathlib
import tempfile
import time
import unittest

from bbb import als, restyle
from tests.fixture import SetBuilder, messy_set


def by_cat(plan, cat):
    return [c for c in plan.changes if c.category == cat]


class Analyze(unittest.TestCase):
    def setUp(self):
        self.root = messy_set().root
        self.plan = restyle.analyze(self.root)

    def test_groups_map_onto_the_template(self):
        details = {(c.track.split(' ', 1)[1], c.detail) for c in by_cat(self.plan, 'group_names')}
        self.assertIn(('vocals', '→ VOX LEAD'), details)
        self.assertIn(('drums live', '→ DRUMS'), details)
        self.assertIn(('parts', '→ Parts'), details)

    def test_order_helpers_then_template_groups_then_the_rest(self):
        (order,) = by_cat(self.plan, 'order')
        self.assertEqual(order.detail, 'parts | drums live | vocals | something else')

    def test_names(self):
        self.assertEqual([c.detail for c in by_cat(self.plan, 'auto_names')], ['→ kontakt 7'])
        self.assertEqual([c.detail for c in by_cat(self.plan, 'rec_names')], ['→ vox chorus'])
        self.assertEqual([c.detail for c in by_cat(self.plan, 'returns')][0], '→ A-amb')

    def test_unknown_top_level_track_is_noted_not_changed(self):
        self.assertTrue(any('something else' in n for n in self.plan.notes))

    def test_empty_lane(self):
        (c,) = by_cat(self.plan, 'empty_lanes')
        self.assertEqual(c.detail, '1 of 4 lanes')

    def test_duplicate_lane_is_only_the_identical_one(self):
        # lane 3 repeats lane 1; lane 4 plays another part of the same file and is a take of its own
        (c,) = by_cat(self.plan, 'dup_lanes')
        self.assertTrue(c.detail.startswith('1 of 4 lanes'), c.detail)

    def test_a_referenced_lane_is_never_removed(self):
        b = SetBuilder()
        g = b.track('Group', 'VOX LEAD', color=7, solo='7')
        t = b.track('Audio', 'vox', group=g, color=7)
        b.audio_clip(b.arrangement(t), 0, 4, 'a.wav', color=7, take=2)
        b.audio_clip(b.lane(t, 1), 0, 4, 'a.wav', color=7)
        b.audio_clip(b.lane(t, 2), 0, 4, 'a.wav', color=7)   # a duplicate, but the comp uses it
        b.lane(t, 3)
        plan = restyle.analyze(b.root)
        self.assertEqual(by_cat(plan, 'dup_lanes'), [])
        self.assertEqual([c.detail for c in by_cat(plan, 'empty_lanes')], ['1 of 3 lanes'])

    def test_a_set_that_follows_the_template_has_no_changes(self):
        b = SetBuilder()
        g = b.track('Group', 'DRUMS', color=12, solo='1')
        b.track('Midi', 'kick', group=g, color=12)
        self.assertEqual(restyle.analyze(b.root).changes, [])


class Apply(unittest.TestCase):
    def test_all_categories_keep_the_sound_and_converge(self):
        root = messy_set().root
        before = als.sound_fingerprint(root)
        plan = restyle.analyze(root)
        restyle.apply(root, plan, list(restyle.CATEGORIES))
        self.assertEqual(als.compare_sound(before, als.sound_fingerprint(root), root), [])
        self.assertEqual([als.name(t) for t in als.tracks(root) if als.group_id(t) == '-1'],
                         ['Parts', 'DRUMS', 'VOX LEAD', 'something else', 'A-amb'])
        again = restyle.analyze(root)
        self.assertEqual([(c.category, c.track, c.detail) for c in again.changes], [])

    def test_sound_check_catches_a_change_in_a_clip(self):
        root = messy_set().root
        before = als.sound_fingerprint(root)
        root.find('.//ArrangerAutomation/Events/AudioClip/CurrentEnd').set('Value', '15')
        self.assertEqual(als.compare_sound(before, als.sound_fingerprint(root), root), ["track 'rec'"])


class Validate(unittest.TestCase):
    def test_a_top_level_track_that_sends_to_a_group_is_a_problem(self):
        b = SetBuilder()                    # Live crashes on loading such a set
        t = b.track('Audio', 'fx')
        routing = als.ET.SubElement(t.find('DeviceChain'), 'AudioOutputRouting')
        target = als.ET.SubElement(routing, 'Target', Value='AudioOut/GroupTrack')
        self.assertEqual(als.validate(b.root), ["track 'fx' sends its audio to a group but is in none"])
        target.set('Value', 'AudioOut/Main')
        self.assertEqual(als.validate(b.root), [])


class Files(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def path(self, name, age=0):
        p = os.path.join(self.dir.name, name)
        als.save(messy_set().root, p)
        t = time.time() - age
        os.utime(p, (t, t))
        return p

    def test_round_trip(self):
        p = self.path('song 1.0.als')
        self.assertEqual(als.sound_fingerprint(als.load(p)), als.sound_fingerprint(messy_set().root))

    def test_restyle_file_writes_a_new_version_and_leaves_the_source(self):
        p = self.path('song 2.5 (harmonics).als')
        original = pathlib.Path(p).read_bytes()
        out, done = restyle.restyle_file(p, [k for k, v in restyle.CATEGORIES.items() if v[1]])
        self.assertEqual(os.path.basename(out), 'song 2.6 (restyle).als')
        self.assertTrue(done)
        self.assertEqual(pathlib.Path(p).read_bytes(), original)
        self.assertEqual(sorted(os.listdir(self.dir.name)), ['song 2.5 (harmonics).als', 'song 2.6 (restyle).als'])

    def test_next_version_follows_the_newest_save_not_the_highest_number(self):
        self.path('song 3.41.als', age=100)   # 3.4.1, older than 3.5
        self.path('song 3.5.als', age=10)
        p = self.path('song 3.4.als', age=200)
        self.assertEqual(os.path.basename(restyle.next_version_path(p)), 'song 3.6 (restyle).als')

    def test_next_version_without_a_number(self):
        p = self.path('idea.als')
        self.assertEqual(os.path.basename(restyle.next_version_path(p)), 'idea 1.1 (restyle).als')

    def test_nothing_is_left_behind_when_the_write_fails(self):
        p = self.path('song 1.0.als')
        real = als.save
        als.save = lambda root, path: (_ for _ in ()).throw(OSError('disk full'))
        self.addCleanup(setattr, als, 'save', real)
        with self.assertRaises(OSError):
            restyle.restyle_file(p, ['group_names'])
        self.assertEqual(os.listdir(self.dir.name), ['song 1.0.als'])

    def test_not_a_live_set_is_reported_as_such(self):
        p = os.path.join(self.dir.name, 'x.als')
        pathlib.Path(p).write_text('not gzip')
        with self.assertRaises(ValueError):
            als.load(p)


if __name__ == '__main__':
    unittest.main()
