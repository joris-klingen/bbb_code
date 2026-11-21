import binascii
import os
import struct
import unittest
import xml.etree.ElementTree as ET

from bbb import als, stock
from tests.fixture import SetBuilder

LIVE = os.path.isdir(stock.LIBRARY)     # the replacements come from Live's own presets


def plugin(name, state=b'', **published):
    """A plugin device as Live stores it: name, state and the parameters it published."""
    d = ET.Element('PluginDevice', Id='0')
    ET.SubElement(ET.SubElement(d, 'On'), 'Manual', Value='true')
    info = ET.SubElement(ET.SubElement(d, 'PluginDesc'), 'Vst3PluginInfo', Id='0')
    ET.SubElement(info, 'Name', Value=name)
    ET.SubElement(info, 'ProcessorState').text = binascii.hexlify(state).decode()
    plist = ET.SubElement(d, 'ParameterList')
    for i, (pname, value) in enumerate(list(published.items()) + [('', 0.1234567687)]):
        p = ET.SubElement(plist, 'PluginFloatParameter', Id=str(i))
        ET.SubElement(p, 'ParameterName', Value=pname.replace('_', ' '))
        ET.SubElement(p, 'ParameterId', Value=str(i) if pname else '-1')
        ET.SubElement(ET.SubElement(p, 'ParameterValue'), 'Manual', Value=str(value))
        ET.SubElement(ET.SubElement(p, 'ParameterValue'), 'AutomationTarget', Id=str(5000 + i))
    return d


def ffbs(values):
    return b'FFBS' + struct.pack('<II', 1, len(values)) + struct.pack('<%df' % len(values), *values)


class Reading(unittest.TestCase):
    def test_published_parameters_without_the_empty_slots(self):
        self.assertEqual(stock.published(plugin('X', Mix=0.25, Peak_Reduct=0.5)), {'Mix': 0.25, 'Peak Reduct': 0.5})

    def test_fabfilter_state(self):
        self.assertEqual(stock.fabfilter(plugin('Pro-Q 3', ffbs([1.0, 1.0, 7.5, -3.0]))), [1.0, 1.0, 7.5, -3.0])
        self.assertEqual(stock.fabfilter(plugin('Other', b'VstW....')), [])

    def test_every_plugin_name_has_one_answer(self):
        self.assertIs(stock.replacement('UADx LA-2A Silver Compressor'), stock.la2a)
        self.assertIs(stock.replacement('soothe2'), stock.nothing)
        self.assertIsNone(stock.replacement('Some New Plugin'))


class Notes(unittest.TestCase):
    def test_drum_notes_move_to_the_built_in_kit(self):
        b = SetBuilder()
        t = b.track('Midi', 'drums')
        kts = ET.SubElement(t, 'KeyTracks')
        for i, (key, times) in enumerate([(36, [0, 4]), (18, [1, 3]), (19, [2]), (105, [0.5])]):
            kt = ET.SubElement(kts, 'KeyTrack', Id=str(i))
            notes = ET.SubElement(kt, 'Notes')
            for time in times:
                ET.SubElement(notes, 'MidiNoteEvent', Time=str(time), NoteId=str(100 * i + int(time * 2)))
            ET.SubElement(kt, 'MidiKey', Value=str(key))
        dropped = stock.remap_notes(t, stock.DRUM_NOTES)
        self.assertEqual(dict(dropped), {105: 1})
        now = {int(als.val(kt, 'MidiKey')): [float(n.get('Time')) for n in kt.find('Notes')] for kt in kts}
        self.assertEqual(now, {60: [0.0, 4.0], 64: [1.0, 2.0, 3.0]})       # both hats on one key, in time order
        self.assertEqual([kt.get('Id') for kt in kts], ['0', '1'])


class UnusedTracks(unittest.TestCase):
    def build(self):
        b = SetBuilder()
        made = {}

        def track(kind, name, group=None, clips=(), muted=False):
            t = made[name] = b.track(kind, name, group=made.get(group))
            speaker = t.find('DeviceChain/Mixer/Speaker')
            speaker.find('Manual').set('Value', 'false' if muted else 'true')
            ET.SubElement(speaker, 'AutomationTarget', Id=b._id())
            for i, disabled in enumerate(clips):
                clip = b.midi_clip(b.arrangement(t), i * 4, i * 4 + 4, name='c')
                ET.SubElement(clip, 'Disabled', Value='true' if disabled else 'false')
            return t

        track('Midi', 'Parts')                                  # a helper: stays, clips or not
        track('Group', 'GUIT')
        track('Midi', 'plays', 'GUIT', clips=[False])
        track('Midi', 'one clip off', 'GUIT', clips=[True, False])
        track('Midi', 'all clips off', 'GUIT', clips=[True, True])
        track('Midi', 'rec', 'GUIT')
        track('Midi', 'muted take', 'GUIT', clips=[False], muted=True)
        track('Group', 'OLD', muted=True)
        track('Midi', 'old lick', 'OLD', clips=[False])
        track('Group', 'ALTS')
        track('Midi', 'alt', 'ALTS', clips=[True])
        track('Midi', 'vocoder in', clips=[True])
        track('Midi', 'rides the mute', clips=[False], muted=True)
        return b, made

    def test_tracks_that_add_nothing_go(self):
        b, made = self.build()
        routing = ET.SubElement(made['plays'].find('DeviceChain'), 'AudioInputRouting')      # a sidechain from it
        ET.SubElement(routing, 'Target', Value='AudioIn/Track.%s/PostFxOut' % made['vocoder in'].get('Id'))
        env = ET.SubElement(ET.SubElement(made['plays'], 'Envelopes'), 'AutomationEnvelope', Id='0')
        target = made['rides the mute'].find('DeviceChain/Mixer/Speaker/AutomationTarget').get('Id')
        ET.SubElement(ET.SubElement(env, 'EnvelopeTarget'), 'PointeeId', Value=target)       # mute is automated
        report = {'tracks removed': []}
        stock.remove_unused_tracks(b.root, report)
        self.assertEqual([als.name(t) for t in als.tracks(b.root)],
                         ['Parts', 'GUIT', 'plays', 'one clip off', 'vocoder in', 'rides the mute'])
        self.assertEqual(dict(report['tracks removed']), {
            'all clips off': 'only deactivated clips', 'rec': 'no clips', 'muted take': 'muted',
            'old lick': 'in a muted group', 'OLD': 'muted', 'alt': 'only deactivated clips', 'ALTS': 'empty group'})
        self.assertEqual(als.validate(b.root), [])


@unittest.skipUnless(LIVE, 'Live 12.4 is not installed here')
class Devices(unittest.TestCase):
    def test_pro_q_bands_become_eq_eight_bands(self):
        band = lambda used, freq, db, shape: [used, 1.0, freq, db, 0.0, 1.0, 1.0, 0.5, shape, 1.0, 2.0, 1.0, 0.0]
        state = ffbs(band(1.0, 7.0, -3.0, 0.0) + band(1.0, 5.0, 0.0, 2.0) + band(0.0, 9.97, 6.0, 0.0) * 22)
        (eq,) = stock.replacement('Pro-Q 3')(plugin('Pro-Q 3', state), 'VOX')
        on = [i for i in range(8) if als.val(eq, 'Bands.%d/ParameterA/IsOn/Manual' % i) == 'true']
        self.assertEqual(on, [0, 1])                                        # the unused bands stay off
        cut, bell = eq.find('Bands.0/ParameterA'), eq.find('Bands.1/ParameterA')
        self.assertEqual((als.val(cut, 'Mode/Manual'), als.val(cut, 'Freq/Manual')), ('1', '32'))
        self.assertEqual((als.val(bell, 'Mode/Manual'), als.val(bell, 'Freq/Manual'), als.val(bell, 'Gain/Manual'),
                          als.val(bell, 'Q/Manual')), ('3', '128', '-3', '1'))

    def test_a_flat_eq_is_left_out(self):
        self.assertEqual(stock.pultec(plugin('UADx Pultec EQP-1A EQ', Enable=1.0), 'x'), [])

    def test_compressor_settings_stay_in_range(self):
        (c,) = stock.la2a(plugin('UADx LA-2A', Peak_Reduct=0.6, Mix=1.0), 'x')
        self.assertAlmostEqual(float(als.val(c, 'Threshold/Manual')), 10 ** (-18 / 20.0), places=4)
        self.assertEqual((als.val(c, 'Ratio/Manual'), als.val(c, 'GainCompensation/Manual')), ('3', 'false'))
        (r,) = stock.reverb(999, 5.0)                                       # far too long and too wet
        self.assertEqual((als.val(r, 'DecayTime/Manual'), als.val(r, 'MixDirect/Manual')), ('60000', '1'))


if __name__ == '__main__':
    unittest.main()
