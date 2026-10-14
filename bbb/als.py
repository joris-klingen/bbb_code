"""Read, inspect and modify Ableton Live .als files (gzipped XML) with the standard library only."""
import copy
import gzip
import hashlib
import xml.etree.ElementTree as ET

XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'


def load(path):
    with gzip.open(path) as f:
        return ET.parse(f).getroot()


def save(root, path):
    data = XML_HEADER + ET.tostring(root, encoding='unicode')
    with gzip.open(path, 'wb') as f:
        f.write(data.encode('utf-8'))


def val(el, path, default=None):
    x = el.find(path)
    return x.get('Value') if x is not None else default


def set_val(el, path, value):
    el.find(path).set('Value', str(value))


# --- tracks ---------------------------------------------------------------

def liveset(root):
    return root.find('LiveSet')


def tracks_el(root):
    return liveset(root).find('Tracks')


def tracks(root):
    return list(tracks_el(root))


def name(t):
    return val(t, 'Name/EffectiveName', '')


def set_name(t, new):
    set_val(t, 'Name/UserName', new)
    set_val(t, 'Name/EffectiveName', new)


def color(t):
    return int(val(t, 'Color'))


def set_color(t, c):
    set_val(t, 'Color', c)


def group_id(t):
    return val(t, 'TrackGroupId', '-1')


def set_group_id(t, gid):
    set_val(t, 'TrackGroupId', gid)


def is_group(t):
    return t.tag == 'GroupTrack'


def children(root, group):
    """Direct children of a group track, in track order."""
    gid = group.get('Id')
    return [t for t in tracks(root) if group_id(t) == gid]


def subtree(root, group):
    """The group plus all nested descendants, in track order."""
    out, ids = [], {group.get('Id')}
    for t in tracks(root):
        if t is group or group_id(t) in ids:
            out.append(t)
            ids.add(t.get('Id'))
    return out


# --- solo hotkey ------------------------------------------------------------

def _keymidi(key):
    km = ET.Element('HeadKeyMidi')
    for tag, v in [('PersistentKeyString', key), ('IsNote', 'false'), ('Channel', '-1'),
                   ('NoteOrController', '-1'), ('LowerRangeNote', '-1'), ('UpperRangeNote', '-1'),
                   ('ControllerMapMode', '0')]:
        ET.SubElement(km, tag, Value=v)
    return km


def solo_key(t):
    return val(t, 'DeviceChain/Mixer/HeadKeyMidi/PersistentKeyString', '')


def set_solo_key(t, key):
    """Set (or with key=None remove) the computer-key mapping on the solo button."""
    mixer = t.find('DeviceChain/Mixer')
    existing = mixer.find('HeadKeyMidi')
    if key is None:
        if existing is not None:
            mixer.remove(existing)
        return
    if existing is not None:
        existing.find('PersistentKeyString').set('Value', key)
        return
    # Live writes HeadKeyMidi directly after SoloSink
    kids = list(mixer)
    idx = next(i for i, e in enumerate(kids) if e.tag == 'SoloSink') + 1
    km = _keymidi(key)
    km.text, km.tail = kids[idx - 1].text, kids[idx - 1].tail
    mixer.insert(idx, km)


# --- content stripping ------------------------------------------------------

CLIP_TAGS = ('AudioClip', 'MidiClip')


def strip_content(el):
    """Remove all clips, take lanes and automation envelopes below el."""
    for parent in list(el.iter()):
        for child in list(parent):
            if child.tag in CLIP_TAGS:
                parent.remove(child)
    for tl in el.iter('TakeLanes'):
        inner = tl.find('TakeLanes')
        if inner is not None:
            for lane in list(inner):
                inner.remove(lane)
    for env in el.findall('.//AutomationEnvelopes/Envelopes'):
        for e in list(env):
            env.remove(e)


# --- pointee ids (globally unique ids for automation/modulation targets) ----

def is_pointee(el):
    t = el.tag
    return 'Id' in el.attrib and (t.endswith('Target') or t.startswith('ControllerTargets.')
                                  or t in ('Pointee', 'RemoteableBool'))


def pointee_ids(root):
    return [int(e.get('Id')) for e in root.iter() if is_pointee(e)]


def clone(root, el):
    """Deep copy any element with fresh pointee ids. Caller inserts it."""
    ls = liveset(root)
    nxt = int(val(ls, 'NextPointeeId'))
    new = copy.deepcopy(el)
    remap = {}
    for e in new.iter():
        if is_pointee(e):
            remap[e.get('Id')] = str(nxt)
            e.set('Id', str(nxt))
            nxt += 1
    for e in new.iter('PointeeId'):
        if e.get('Value') in remap:
            e.set('Value', remap[e.get('Value')])
    set_val(ls, 'NextPointeeId', nxt)
    return new


def clone_track(root, t):
    """Deep copy a track with fresh track id and pointee ids. Caller inserts it."""
    new = clone(root, t)
    new.set('Id', str(max(int(x.get('Id')) for x in tracks(root)) + 1))
    return new


# --- devices ------------------------------------------------------------------

def device_list(t):
    return t.find('DeviceChain/DeviceChain/Devices')


def device_name(d):
    for p in ('PluginDesc/Vst3PluginInfo/Name', 'PluginDesc/VstPluginInfo/PlugName', 'PluginDesc/AuPluginInfo/Name'):
        n = val(d, p)
        if n:
            return n
    return d.tag


def clear_devices(t):
    devs = device_list(t)
    for d in list(devs):
        devs.remove(d)


def remove_devices(t, match):
    """Remove devices whose name satisfies match(name)."""
    devs = device_list(t)
    for d in list(devs):
        if match(device_name(d)):
            devs.remove(d)


def keep_devices(t, names):
    """Keep only devices whose name is in names, in their existing order."""
    remove_devices(t, lambda n: n not in names)


def copy_devices(root, src_track, dst_track, skip=lambda n: False):
    """Append clones of src_track's devices (may come from another set) to dst_track."""
    devs = device_list(dst_track)
    for d in device_list(src_track):
        if not skip(device_name(d)):
            devs.append(clone(root, d))


# --- returns and sends ----------------------------------------------------------

def _retail(parent, inner, last):
    """Restore indentation after inserting: every child gets inner, the last one gets last."""
    for e in parent:
        e.tail = inner
    parent[-1].tail = last


def _renumber(parent):
    for i, e in enumerate(parent):
        e.set('Id', str(i))


def add_return(root, src_return, index):
    """Insert a new, empty return at position index (0 = A) and a matching send on every track.

    The new return is a device-less clone of src_return. Returns the new track; the caller
    names it and places it in the track list (it is appended at the end).
    """
    ls = liveset(root)
    for t in tracks(root):
        sends = t.find('DeviceChain/Mixer/Sends')
        holders = list(sends)
        h = clone(root, holders[0])
        set_val(h, 'Send/Manual', val(h, 'Send/MidiControllerRange/Min'))
        set_val(h, 'EnabledByUser', 'false' if t.tag == 'ReturnTrack' else 'true')
        sends.insert(index, h)
        _retail(sends, holders[0].tail, holders[-1].tail)
        _renumber(sends)
    pre = ls.find('SendsPre')
    p = copy.deepcopy(list(pre)[0])
    p.set('Value', 'false')
    first, last = list(pre)[0].tail, list(pre)[-1].tail
    pre.insert(index, p)
    _retail(pre, first, last)
    _renumber(pre)
    new = clone_track(root, src_return)  # already has the extra send from the loop above
    clear_devices(new)
    tracks_el(root).append(new)
    return new


def set_send(t, index, db):
    """Set send number index (0 = A) to a level in dB (None = off)."""
    send = t.findall('DeviceChain/Mixer/Sends/TrackSendHolder/Send')[index]
    lo = float(val(send, 'MidiControllerRange/Min'))
    set_val(send, 'Manual', lo if db is None else max(lo, min(1.0, 10 ** (db / 20))))


# --- mixer --------------------------------------------------------------------

def reset_mixer(t):
    """Volume 0 dB, pan center, sends off, track on."""
    m = t.find('DeviceChain/Mixer')
    set_val(m, 'Volume/Manual', 1)
    set_val(m, 'Pan/Manual', 0)
    set_val(m, 'PanMode', 0)
    for path, v in [('SplitStereoPanL/Manual', -1), ('SplitStereoPanR/Manual', 1), ('Speaker/Manual', 'true')]:
        if m.find(path) is not None:
            set_val(m, path, v)
    for send in m.findall('Sends/TrackSendHolder/Send'):
        set_val(send, 'Manual', val(send, 'MidiControllerRange/Min'))


# --- scenes -------------------------------------------------------------------

SLOT_LISTS = ('ClipSlotList', 'Slots')


def trim_scenes(root, n):
    """Keep the first n scenes and the matching clip slots on every track."""
    ls = liveset(root)
    scenes = ls.find('Scenes')
    for s in list(scenes)[n:]:
        scenes.remove(s)
    for lst in ls.iter():
        if lst.tag in SLOT_LISTS:
            kids = list(lst)
            for slot in kids[n:]:
                lst.remove(slot)
            if kids[n:]:
                lst[-1].tail = kids[-1].tail


# --- time signature -----------------------------------------------------------

def remove_time_signature_changes(root):
    """Keep only the initial time signature."""
    main = liveset(root).find('MainTrack')
    target = main.find('.//TimeSignature/AutomationTarget').get('Id')
    for env in main.findall('AutomationEnvelopes/Envelopes/AutomationEnvelope'):
        if val(env, 'EnvelopeTarget/PointeeId') == target:
            events = env.find('Automation/Events')
            evs = sorted(events, key=lambda e: float(e.get('Time')))
            for e in evs[1:]:
                events.remove(e)
            if evs[1:]:
                evs[0].tail = evs[-1].tail


# --- arrangement clips ----------------------------------------------------------

def arrangement_events(t):
    return (t.find('DeviceChain/MainSequencer/ClipTimeable/ArrangerAutomation/Events')
            if t.tag == 'MidiTrack' else
            t.find('DeviceChain/MainSequencer/Sample/ArrangerAutomation/Events'))


def clip_source(c):
    """What a clip plays: the audio file, or a fingerprint of the MIDI notes."""
    if c.tag == 'AudioClip':
        return 'A:' + (val(c, 'SampleRef/FileRef/RelativePath') or val(c, 'SampleRef/FileRef/Path') or '?')
    notes = sorted((val(kt, 'MidiKey'), n.get('Time'), n.get('Duration'))
                   for kt in c.findall('Notes/KeyTracks/KeyTrack') for n in kt.findall('Notes/MidiNoteEvent'))
    return 'M:' + hashlib.md5(repr(notes).encode()).hexdigest()


def take_lanes(t):
    inner = t.find('TakeLanes/TakeLanes')
    return inner, (list(inner) if inner is not None else [])


def lane_clips(lane):
    return lane.findall('ClipAutomation/Events/*')


def make_empty_midi_clip(root, proto, start, length, clip_name, clip_color, clip_id):
    """A note-less MIDI clip based on proto, placed at start (beats) with the given length."""
    c = clone(root, proto)
    c.set('Id', str(clip_id))
    c.set('Time', str(start))
    end = start + length
    for path, v in [('CurrentStart', start), ('CurrentEnd', end), ('Loop/LoopStart', 0), ('Loop/LoopEnd', length),
                    ('Loop/StartRelative', 0), ('Loop/LoopOn', 'false'), ('Loop/OutMarker', length),
                    ('Loop/HiddenLoopStart', 0), ('Loop/HiddenLoopEnd', length), ('Name', clip_name),
                    ('Color', clip_color)]:
        set_val(c, path, v)
    for kt in c.findall('Notes/KeyTracks'):
        for k in list(kt):
            kt.remove(k)
    for env in c.findall('Envelopes/Envelopes'):
        for e in list(env):
            env.remove(e)
    return c


# --- sound fingerprint ---------------------------------------------------------------
# Everything that can affect playback, per track. Restyling may only change what is skipped
# here: names, colors, solo-key mappings, track order and take lanes (never played; only
# the comped clips on the main lane are).

_TRACK_TAGS = ('MidiTrack', 'AudioTrack', 'GroupTrack', 'ReturnTrack')
_SKIP_IN_TRACK = ('Name', 'Color', 'TakeLanes')
_SKIP_IN_CLIP = ('Color',)
_SKIP_IN_MIXER = ('HeadKeyMidi',)


def _digest(el, h, skip):
    h.update(el.tag.encode())
    for k in sorted(el.attrib):
        h.update(f'{k}={el.attrib[k]};'.encode())
    if el.text and el.text.strip():
        h.update(el.text.strip().encode())
    for child in el:
        if child.tag in skip:
            continue
        if child.tag in CLIP_TAGS:
            sub = _SKIP_IN_CLIP
        elif child.tag == 'Mixer':
            sub = _SKIP_IN_MIXER
        else:
            sub = ()
        _digest(child, h, sub)
        h.update(b'/')


def sound_fingerprint(root):
    """{'set': hash of everything outside the tracks, <track id>: hash of that track}."""
    ls = liveset(root)
    fp = {}
    h = hashlib.sha1()
    for child in ls:
        if child.tag != 'Tracks':
            _digest(child, h, ())
    fp['set'] = h.hexdigest()
    for t in tracks(root):
        h = hashlib.sha1()
        _digest(t, h, _SKIP_IN_TRACK)
        fp[t.get('Id')] = h.hexdigest()
    return fp


def compare_sound(before, after, root=None):
    """List of differences in playback-relevant content (empty = sound unchanged)."""
    names = {t.get('Id'): name(t) for t in tracks(root)} if root is not None else {}
    diffs = []
    for k in sorted(set(before) | set(after)):
        if before.get(k) != after.get(k):
            diffs.append('project settings' if k == 'set' else f'track {names.get(k, k)!r}')
    return diffs


def validate(root):
    """Basic integrity checks; returns a list of problems (empty = ok)."""
    problems = []
    ids = pointee_ids(root)
    if len(ids) != len(set(ids)):
        problems.append('duplicate pointee ids')
    if ids and max(ids) >= int(val(liveset(root), 'NextPointeeId')):
        problems.append('pointee id >= NextPointeeId')
    tids = [t.get('Id') for t in tracks(root)]  # includes return tracks
    if len(tids) != len(set(tids)):
        problems.append('duplicate track ids')
    seen = set()
    for t in tracks(root):
        g = group_id(t)
        if g != '-1' and g not in seen:
            problems.append(f'track {name(t)!r} appears before its group {g}')
        seen.add(t.get('Id'))
    return problems
