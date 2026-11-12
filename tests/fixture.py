"""Build small synthetic Live sets for the tests (real sets are private and large).

Only the parts of the XML that bbb reads are present; the element paths follow real sets.
"""
import xml.etree.ElementTree as ET


class SetBuilder:
    def __init__(self, creator='Ableton Live 12.1', tempo=120, signature=201):
        self.root = ET.Element('Ableton', Creator=creator, MajorVersion='5')
        self.ls = ET.SubElement(self.root, 'LiveSet')
        ET.SubElement(self.ls, 'NextPointeeId', Value='100000')
        self.tracks = ET.SubElement(self.ls, 'Tracks')
        main = ET.SubElement(self.ls, 'MainTrack')
        mixer = ET.SubElement(ET.SubElement(main, 'DeviceChain'), 'Mixer')
        ET.SubElement(ET.SubElement(mixer, 'Tempo'), 'Manual', Value=str(tempo))
        ET.SubElement(ET.SubElement(mixer, 'TimeSignature'), 'Manual', Value=str(signature))
        self.locators = ET.SubElement(ET.SubElement(self.ls, 'Locators'), 'Locators')
        self._pointee = 1000
        self._track = 0
        self._clip = 0

    def _id(self):
        self._pointee += 1
        return str(self._pointee)

    def track(self, kind, name, group=None, color=0, user=None, solo=None):
        """kind: Audio / Midi / Group / Return. Returns the track element."""
        self._track += 1
        t = ET.SubElement(self.tracks, kind + 'Track', Id=str(self._track))
        n = ET.SubElement(t, 'Name')
        ET.SubElement(n, 'EffectiveName', Value=name)
        ET.SubElement(n, 'UserName', Value=name if user is None else user)
        ET.SubElement(t, 'Color', Value=str(color))
        ET.SubElement(t, 'TrackGroupId', Value=group.get('Id') if group is not None else '-1')
        ET.SubElement(ET.SubElement(t, 'TakeLanes'), 'TakeLanes')
        dc = ET.SubElement(t, 'DeviceChain')
        mixer = ET.SubElement(dc, 'Mixer')
        ET.SubElement(mixer, 'Sends')
        ET.SubElement(ET.SubElement(mixer, 'Speaker'), 'Manual', Value='true')
        ET.SubElement(mixer, 'SoloSink', Value='false')
        if solo:
            km = ET.SubElement(mixer, 'HeadKeyMidi')
            ET.SubElement(km, 'PersistentKeyString', Value=solo)
        vol = ET.SubElement(mixer, 'Volume')
        ET.SubElement(vol, 'Manual', Value='1')
        ET.SubElement(vol, 'AutomationTarget', Id=self._id())
        seq = ET.SubElement(dc, 'MainSequencer')
        holder = ET.SubElement(seq, 'ClipTimeable' if kind == 'Midi' else 'Sample')
        ET.SubElement(ET.SubElement(holder, 'ArrangerAutomation'), 'Events')
        ET.SubElement(ET.SubElement(dc, 'DeviceChain'), 'Devices')
        return t

    def _clip_el(self, parent, tag, time, length, name, color):
        self._clip += 1
        c = ET.SubElement(parent, tag, Id=str(self._clip), Time=str(time))
        ET.SubElement(c, 'CurrentStart', Value=str(time))
        ET.SubElement(c, 'CurrentEnd', Value=str(time + length))
        ET.SubElement(c, 'Name', Value=name)
        ET.SubElement(c, 'Color', Value=str(color))
        return c

    def audio_clip(self, parent, time, length, path, offset=0, name='', color=0, take=None):
        c = self._clip_el(parent, 'AudioClip', time, length, name, color)
        loop = ET.SubElement(c, 'Loop')
        ET.SubElement(loop, 'LoopStart', Value=str(offset))
        ET.SubElement(loop, 'LoopEnd', Value=str(offset + length))
        ET.SubElement(ET.SubElement(ET.SubElement(c, 'SampleRef'), 'FileRef'), 'RelativePath', Value=path)
        if take is not None:
            ET.SubElement(c, 'TakeId', Value=str(take))
        return c

    def midi_clip(self, parent, time, length, name='', color=0, notes=()):
        """notes: (pitch, time, duration) tuples."""
        c = self._clip_el(parent, 'MidiClip', time, length, name, color)
        kts = ET.SubElement(ET.SubElement(c, 'Notes'), 'KeyTracks')
        for pitch, t, d in notes:
            kt = ET.SubElement(kts, 'KeyTrack')
            ET.SubElement(ET.SubElement(kt, 'Notes'), 'MidiNoteEvent', Time=str(t), Duration=str(d))
            ET.SubElement(kt, 'MidiKey', Value=str(pitch))
        return c

    @staticmethod
    def arrangement(t):
        tag = 'ClipTimeable' if t.tag == 'MidiTrack' else 'Sample'
        return t.find(f'DeviceChain/MainSequencer/{tag}/ArrangerAutomation/Events')

    def lane(self, t, lane_id):
        lane = ET.SubElement(t.find('TakeLanes/TakeLanes'), 'TakeLane', Id=str(lane_id))
        return ET.SubElement(ET.SubElement(lane, 'ClipAutomation'), 'Events')

    def device(self, t, plugin):
        d = ET.SubElement(t.find('DeviceChain/DeviceChain/Devices'), 'PluginDevice', Id=self._id())
        ET.SubElement(ET.SubElement(ET.SubElement(d, 'PluginDesc'), 'Vst3PluginInfo'), 'Name', Value=plugin)
        return d

    def locator(self, time, name):
        loc = ET.SubElement(self.locators, 'Locator', Id=self._id(), Time=str(time))
        ET.SubElement(loc, 'Name', Value=name)
        return loc


def messy_set():
    """A set that deviates from the template in every category."""
    b = SetBuilder()
    vox = b.track('Group', 'vocals', color=1)
    chorus = b.track('Group', 'Vox Chorus', group=vox, color=1)
    rec = b.track('Audio', 'rec', group=chorus, color=1)
    b.audio_clip(b.arrangement(rec), 0, 16, 'Samples/vox 1.wav', take=1)
    b.audio_clip(b.lane(rec, 1), 0, 16, 'Samples/vox 1.wav')
    b.lane(rec, 2)                                                   # empty, unreferenced
    b.audio_clip(b.lane(rec, 3), 0, 16, 'Samples/vox 1.wav')         # same as lane 1
    b.audio_clip(b.lane(rec, 4), 0, 16, 'Samples/vox 1.wav', offset=32)   # same file, another part of it
    drums = b.track('Group', 'drums live', color=3)
    kit = b.track('Midi', '17-Kontakt 7', group=drums, color=3, user='')
    b.midi_clip(b.arrangement(kit), 0, 8, notes=[(36, 0, 1)])
    b.device(kit, 'Kontakt 7')
    parts = b.track('Midi', 'parts', color=0)
    for i, (n, col) in enumerate([('intro', 17), ('verse', 23), ('chorus', 14)]):
        b.midi_clip(b.arrangement(parts), i * 16, 16, name=n, color=col)
    b.track('Audio', 'something else', color=9)
    b.track('Return', 'A-ambience', color=0, user='ambience')
    b.locator(16, 'verse 1')
    return b
