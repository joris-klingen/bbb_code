"""Make a Live set that needs nothing but Live: every third-party plugin replaced by a built-in
device, take lanes and unused tracks (no clips, only deactivated clips, or muted) removed. A light version that loads anywhere and sounds
roughly the same; never the mix itself.

    python3 -m bbb.stock song.als            report only
    python3 -m bbb.stock song.als --write    write '<song> <next version> (ableton only).als'

The replacements come from Live's own presets (Core Library, same file format as the set), with
the settings of the plugin carried over where they can be read: Live keeps the values of the
parameters a plugin publishes (thresholds, mix, EQ knobs), and FabFilter plugins keep theirs as
a plain list of numbers. Where nothing can be read the preset stays as it is. What every plugin
becomes is in REPLACE below; a plugin that is not in it is removed and reported.

Unlike restyle this changes the sound on purpose, so there is no sound fingerprint to hold it
to: the checks at the end only see to it that Live can load the result.
"""
import binascii
import copy
import glob
import gzip
import math
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
from collections import Counter

from . import als, restyle

LIBRARY = '/Applications/Ableton Live 12.4.app/Contents/App-Resources/Core Library/Devices'
PLUGIN_TAGS = ('PluginDevice', 'AuPluginDevice')
_presets = {}


# --- built-in devices -------------------------------------------------------------------

def preset(pattern):
    """The device of a Core Library preset, e.g. 'Audio Effects/Reverb/**/Vocal Hall.adv'."""
    if pattern not in _presets:
        found = glob.glob(os.path.join(LIBRARY, pattern), recursive=True)
        if not found:
            raise FileNotFoundError('no preset ' + pattern)
        with gzip.open(found[0]) as f:
            _presets[pattern] = ET.parse(f).getroot()[0]
    return copy.deepcopy(_presets[pattern])


def setp(device, path, value):
    """Set a parameter of a built-in device, kept inside the range the device gives for it."""
    p = device.find(path)
    manual = p.find('Manual') if p.find('Manual') is not None else p
    if isinstance(value, bool):
        manual.set('Value', 'true' if value else 'false')
        return
    lo, hi = p.find('MidiControllerRange/Min'), p.find('MidiControllerRange/Max')
    if lo is not None:
        value = type(value)(min(float(hi.get('Value')), max(float(lo.get('Value')), value)))
    # plain decimals: no exponent, which Live may not read
    manual.set('Value', ('%.6f' % value).rstrip('0').rstrip('.') if isinstance(value, float) else str(value))


def fresh(root, device):
    """Give every automation target of a preset device an id of its own in this set (in a preset
    they are all 0, which als.clone would map onto one new id)."""
    ls = als.liveset(root)
    nxt = int(als.val(ls, 'NextPointeeId'))
    for e in device.iter():
        if als.is_pointee(e):
            e.set('Id', str(nxt))
            nxt += 1
    als.set_val(ls, 'NextPointeeId', nxt)
    return device


def gain(db):
    return 10 ** (db / 20.0)


# --- what a plugin was set to -----------------------------------------------------------

def published(plugin):
    """{parameter name: value} of the parameters the plugin published to Live."""
    out = {}
    for p in plugin.findall('ParameterList/*'):
        if als.val(p, 'ParameterId') != '-1' and als.val(p, 'ParameterName'):
            out[als.val(p, 'ParameterName')] = float(als.val(p, 'ParameterValue/Manual'))
    return out


def fabfilter(plugin):
    """The parameter values of a FabFilter plugin (its state is 'FFBS', version, count, floats)."""
    buf = plugin.find('.//ProcessorState')
    raw = binascii.unhexlify(re.sub(r'\s', '', (buf.text or '') if buf is not None else ''))
    if raw[:4] != b'FFBS':
        return []
    count = struct.unpack_from('<I', raw, 8)[0]
    return list(struct.unpack_from('<%df' % count, raw, 12))


# --- the replacements: each returns a list of built-in devices --------------------------

EQ_CUT_LOW, EQ_CUT_LOW_STEEP, EQ_SHELF_LOW, EQ_BELL, EQ_NOTCH, EQ_SHELF_HIGH, EQ_CUT_HIGH, EQ_CUT_HIGH_STEEP = \
    1, 0, 2, 3, 4, 5, 6, 7


def eq_eight(bands):
    """EQ Eight with up to eight bands: (mode, frequency in Hz, gain in dB, Q)."""
    bands = [b for b in bands if b[0] in (EQ_CUT_LOW, EQ_CUT_LOW_STEEP, EQ_CUT_HIGH, EQ_CUT_HIGH_STEEP, EQ_NOTCH)
             or abs(b[2]) >= 0.1]
    if not bands:
        return []
    bands = sorted(sorted(bands, key=lambda b: -abs(b[2]) if b[0] in (EQ_BELL, EQ_SHELF_LOW, EQ_SHELF_HIGH) else -99)[:8],
                   key=lambda b: b[1])
    eq = preset('Audio Effects/EQ Eight/**/LowCut.adv')
    for i in range(8):
        band = eq.find('Bands.%d/ParameterA' % i)
        setp(band, 'IsOn', i < len(bands))
        if i < len(bands):
            mode, freq, db, q = bands[i]
            setp(band, 'Mode', mode)
            setp(band, 'Freq', float(freq))
            setp(band, 'Gain', float(db))
            setp(band, 'Q', float(q))
    return [eq]


def pro_q(stride, q_at, shape_at, slope_at):
    """FabFilter Pro-Q 3 / 4: per band used, enabled, frequency (log2 Hz), gain (dB), then Q,
    shape and slope at the given places. Dynamic bands become their static gain."""
    shapes = {0: EQ_BELL, 1: EQ_SHELF_LOW, 3: EQ_SHELF_HIGH, 5: EQ_NOTCH}

    def convert(plugin, track):
        f, bands = fabfilter(plugin), []
        for b in range(min(24, len(f) // stride)):
            used, enabled, freq, db = f[b * stride: b * stride + 4]
            if not (used and enabled):
                continue
            shape, steep = int(round(f[b * stride + shape_at])), f[b * stride + slope_at] >= 4
            q = 0.025 * 1600 ** f[b * stride + q_at]
            if shape == 2:
                bands.append((EQ_CUT_LOW_STEEP if steep else EQ_CUT_LOW, 2 ** freq, 0.0, 0.71))
            elif shape == 4:
                bands.append((EQ_CUT_HIGH_STEEP if steep else EQ_CUT_HIGH, 2 ** freq, 0.0, 0.71))
            elif shape in shapes:
                bands.append((shapes[shape], 2 ** freq, db, q))
        return eq_eight(bands)
    return convert


def pultec(plugin, track):
    """Low shelf (boost minus cut), a bell for the high boost, a shelf for the high cut."""
    p = published(plugin)
    if not p or p.get('Enable', 1) < 0.5:
        return []
    pick = lambda values, x: values[min(len(values) - 1, int(round(x * (len(values) - 1))))]
    low = pick([20, 30, 60, 100], p.get('Low Freq', 0.66))
    high = pick([3000, 4000, 5000, 8000, 10000, 12000, 16000], p.get('High Freq', 0.5))
    cut = pick([5000, 10000, 20000], p.get('HF Atten Freq', 0.5))
    return eq_eight([
        (EQ_SHELF_LOW, low * 2.5, 12 * p.get('LF Boost', 0) - 8 * p.get('LF Atten', 0), 0.6),
        (EQ_BELL, high, 14 * p.get('HF Boost', 0), 2.0 - 1.4 * p.get('HF Q', 0.5)),
        (EQ_SHELF_HIGH, cut, -12 * p.get('HF Atten', 0), 0.71),
    ])


def spectre(plugin, track):
    """An enhancer: every band only adds. Its boosts as gentle EQ boosts."""
    p, bands = published(plugin), []
    for name, mode in [('LowShelf', EQ_SHELF_LOW), ('Peak 01', EQ_BELL), ('Peak 02', EQ_BELL), ('Peak 03', EQ_BELL),
                       ('Peak 04', EQ_BELL), ('Peak 05', EQ_BELL), ('HighShelf', EQ_SHELF_HIGH)]:
        if p.get(name + ' Gain', 0) > 0.01 and p.get(name + ' Switch', 1) >= 0.5:
            freq = 20 * 1000 ** p.get(name + ' Frequency', 0.5)
            bands.append((mode, freq, 3 * p[name + ' Gain'], 1.0))    # it adds harmonics, not level
    return eq_eight(bands)


def compressor(threshold_db, ratio, attack_ms, release_ms, makeup_db=None, knee=6.0, mix=1.0):
    c = preset('Audio Effects/Compressor/**/Generic Compressor.adv')
    if makeup_db is None:       # about a third of what it can take off at full level
        makeup_db = min(6.0, -threshold_db * (1 - 1.0 / ratio) * 0.35)
    setp(c, 'Threshold', gain(threshold_db))
    setp(c, 'Ratio', float(ratio))
    setp(c, 'Attack', float(attack_ms))
    setp(c, 'Release', float(release_ms))
    setp(c, 'GainCompensation', False)
    setp(c, 'Gain', float(makeup_db))
    setp(c, 'Knee', float(knee))
    setp(c, 'DryWet', float(mix))
    return [c]


def la2a(plugin, track):
    """Opto: slow and gentle. Peak reduction 0-1 is how far the threshold comes down."""
    p = published(plugin)
    return compressor(-30 * p.get('Peak Reduct', 0.4), 10 if p.get('Comp/Limit', 0) >= 0.5 else 3, 10, 400,
                      mix=p.get('Mix', 1))


def u1176(plugin, track):
    """FET: fast. Input 0-1 drives into a fixed threshold."""
    p = published(plugin)
    ratio = [4, 8, 12, 20][min(3, int(p.get('Ratio', 0) * 4))]
    return compressor(-24 * p.get('Input', 0.4), ratio, 0.5, 120, mix=p.get('Mix', 1))


def pro_c(plugin, track):
    p = published(plugin)
    return compressor(p.get('Threshold', -18), 4, 10, 150, makeup_db=p.get('Wet Gain', 0), knee=p.get('Knee', 6))


def fixed(pattern, **values):
    """A preset as it is, with some parameters set."""
    def convert(plugin, track):
        d = preset(pattern)
        for path, value in values.items():
            setp(d, path, value)
        return [d]
    return convert


def reverb(decay_s, mix, predelay_ms=None):
    r = preset('Audio Effects/Reverb/**/Vocal Hall.adv')
    setp(r, 'DecayTime', float(decay_s) * 1000)
    setp(r, 'MixDirect', float(mix))
    if predelay_ms is not None:
        setp(r, 'PreDelay', float(predelay_ms))
    return [r]


def pro_r(plugin, track):
    """Pro-R 2: the first number is the size of the space (0-1), the tenth the mix in percent."""
    f = fabfilter(plugin)
    if len(f) < 10:
        return reverb(1.5, 0.2)
    return reverb(0.25 * 40 ** f[0], f[9] / 100.0, max(0.5, f[8]))


def valhalla(longest):
    def convert(plugin, track):
        p = published(plugin)
        return reverb(0.5 + longest * p.get('Decay', 0.2) ** 1.5, p.get('Mix', 0.2))
    return convert


def decapitator(plugin, track):
    p = published(plugin)
    drive = p.get('Drive', 0.25)
    return fixed('Audio Effects/Saturator/**/A Bit Warmer.adv', PreDrive=18.0 * drive, PostDrive=-9.0 * drive,
                 DryWet=float(p.get('Mix', 1)))(plugin, track)


def echoboy(plugin, track):
    p = published(plugin)
    return fixed('Audio Effects/Delay/**/8th Note.adv', DryWet=float(p.get('Mix', 0.25)),
                 Feedback=0.9 * p.get('Feedback', 0.3))(plugin, track)


def wider(plugin, track):
    return fixed('Audio Effects/Utility/**/Wide Stereo.adv',
                 StereoWidth=1.0 + 0.6 * published(plugin).get('Amount', 0.3))(plugin, track)


def synth(plugin, track):
    """Juno-style synth: a bass patch on tracks in a bass group, a chord patch elsewhere."""
    bass = 'bass' in track.lower()
    return [preset('Instruments/Drift/**/%s.adv' % ('Vintage Chorus Bass' if bass else 'Gentle Sixty'))]


def sampler(plugin, track):
    """Kontakt: what it played is not in the set. Guess from the track name."""
    organ = 'organ' in track.lower()
    return [preset('Instruments/Electric/**/%s.adv' % ('Organ Soft' if organ else 'E-Piano MKI Mellow'))]


def nothing(plugin, track):
    return []


# Plugin name (start of it) -> what it becomes. Order matters: the first match wins.
REPLACE = [
    ('Pro-Q 3', pro_q(13, q_at=7, shape_at=8, slope_at=9)),
    ('Pro-Q 4', pro_q(23, q_at=4, shape_at=5, slope_at=6)),
    ('UADx Pultec', pultec),
    ('Spectre', spectre),
    ('UADx LA-2A', la2a),
    ('UADx 1176', u1176),
    ('Pro-C 2', pro_c),
    ('Devil-Loc', fixed('Audio Effects/Compressor/**/Brute Compression.adv')),
    ('DeEsser', fixed('Audio Effects/Compressor/**/De-esser.adv')),
    ('Pro-R 2', pro_r),
    ('ValhallaVintageVerb', valhalla(longest=8.0)),
    ('ValhallaSupermassive', valhalla(longest=20.0)),
    ('Decapitator', decapitator),
    ('J37', fixed('Audio Effects/Saturator/**/A Bit Warmer.adv', DryWet=0.5)),
    ('EchoBoy', echoboy),
    ('Wider', wider),
    ('Waves Tune', fixed('Audio Effects/Auto Shift/Tune Gentle.adv')),
    ('smartLimit', fixed('Audio Effects/Limiter/**/Fast.adv', Gain=0.0, Ceiling=-0.3)),
    ('Model 84', synth),
    ('Kontakt', sampler),
    ('MODO BASS', fixed('Instruments/Drift/**/Deep Bass.adv')),
    ('Superior Drummer', fixed('Instruments/Impulse/Impulse 606.adv')),
    # nothing built in does this, and the mix holds without it
    ('soothe2', nothing), ('Pro-MB', nothing), ('Oxford Inflator', nothing), ('BoothCue', nothing),
]
# Impulse plays its eight sounds on the white keys from C3. Superior Drummer's notes -> those.
# Its sounds: kick 60, snare 62, closed hat 64, open hat 65, low tom 67, high tom 69, cymbal 71.
DRUM_NOTES = {36: 60, 35: 60, 38: 62, 40: 62, 37: 62,
              18: 64, 19: 64, 20: 64, 22: 64, 62: 64, 63: 64, 64: 64, 21: 64, 65: 64, 42: 64, 44: 64,
              51: 64, 53: 64, 59: 64,                       # the ride: on the closed hat
              24: 65, 25: 65, 26: 65, 60: 65, 61: 65, 46: 65, 23: 65,
              41: 67, 43: 67, 45: 67, 47: 69, 48: 69, 50: 69,
              49: 71, 52: 71, 55: 71, 57: 71}


def replacement(name):
    return next((convert for start, convert in REPLACE if name.startswith(start)), None)


# --- the conversion ---------------------------------------------------------------------

def track_path(t, by_id):
    names, g = [als.name(t)], als.group_id(t)
    while g != '-1' and g in by_id:
        names.insert(0, als.name(by_id[g]))
        g = als.group_id(by_id[g])
    return ' / '.join(names)


def replace_plugins(root, report):
    by_id = {t.get('Id'): t for t in als.tracks(root)}
    owners = als.tracks(root) + [root.find('LiveSet/MainTrack'), root.find('LiveSet/PreHearTrack')]
    drum_tracks = []
    for t in owners:
        path = track_path(t, by_id) if t.find('TrackGroupId') is not None else 'Main'
        for devices in [e for e in t.iter('Devices')]:
            for plugin in [d for d in devices if d.tag in PLUGIN_TAGS]:
                name = als.device_name(plugin)
                convert = replacement(name)
                new = convert(plugin, path) if convert else []
                at = list(devices).index(plugin)
                devices.remove(plugin)
                taken = [int(d.get('Id')) for d in devices if d.get('Id', '').isdigit()]
                for i, d in enumerate(new):
                    d = fresh(root, d)
                    d.set('Id', str(max(taken + [-1]) + 1 + i))
                    als.set_val(d, 'On/Manual', als.val(plugin, 'On/Manual', 'true'))
                    if d.find('UserName') is not None:
                        d.find('UserName').set('Value', 'was ' + name)
                    d.tail = plugin.tail
                    devices.insert(at + i, d)
                kind = 'unknown: removed' if convert is None else ('removed' if not new else new[0].tag)
                report['plugins'][(name, kind)] += 1
                if name.startswith('Superior Drummer') and new and t not in drum_tracks:
                    drum_tracks.append(t)
    for t in drum_tracks:
        report['drum notes'].update(remap_notes(t, DRUM_NOTES))


def remap_notes(t, mapping):
    """Move the notes of every MIDI clip of the track to other keys; notes on keys that are not
    in the mapping are dropped. Returns {old key: notes} of what was dropped."""
    dropped = Counter()
    for tracks in t.iter('KeyTracks'):
        by_key = {}
        for kt in list(tracks):
            key = int(als.val(kt, 'MidiKey'))
            notes = kt.find('Notes')
            if key not in mapping:
                dropped[key] += len(notes)
                tracks.remove(kt)
            elif mapping[key] in by_key:
                for n in list(notes):
                    by_key[mapping[key]].find('Notes').append(n)
                tracks.remove(kt)
            else:
                als.set_val(kt, 'MidiKey', mapping[key])
                by_key[mapping[key]] = kt
        for i, kt in enumerate(tracks):
            kt.set('Id', str(i))
            notes = kt.find('Notes')
            notes[:] = sorted(notes, key=lambda n: float(n.get('Time')))     # as Live writes them
    return dropped


def remove_take_lanes(root, report):
    for t in als.tracks(root):
        inner, lanes = als.take_lanes(t)
        for lane in lanes:
            inner.remove(lane)
        report['take lanes'] += len(lanes)


def remove_unused_tracks(root, report):
    """Tracks that add nothing to what is heard: without clips, with only deactivated clips, or
    muted (and never unmuted by automation), with everything inside a muted group; then the
    groups left with nothing in them. Not the helper tracks, the returns, or a track something
    is routed from (a sidechain or vocoder input)."""
    tracks_el = als.tracks_el(root)
    routed = {m.group(1) for e in root.iter() for m in [re.search(r'Track\.(\d+)', e.get('Value') or '')] if m}
    keep_names = {'length', 'parts'}
    automated = {e.get('Value') for e in root.iter('PointeeId')}

    def why(t):
        speaker = t.find('DeviceChain/Mixer/Speaker')
        if als.val(speaker, 'Manual') == 'false' and speaker.find('AutomationTarget').get('Id') not in automated:
            return 'muted'
        if als.is_group(t):
            return None
        clips = [e for e in t.iter() if e.tag in als.CLIP_TAGS]
        if not clips:
            return 'no clips'
        if all(als.val(c, 'Disabled') == 'true' for c in clips):
            return 'only deactivated clips'
        return None

    def protected(t):
        return t.tag == 'ReturnTrack' or t.get('Id') in routed or als.name(t).strip().lower() in keep_names

    def remove(t, reason):
        report['tracks removed'].append((als.name(t), reason))
        tracks_el.remove(t)

    for t in list(tracks_el):
        if t not in list(tracks_el) or protected(t):
            continue
        reason = why(t)
        inside = als.subtree(root, t)[1:] if als.is_group(t) else []
        if reason and not any(protected(x) for x in inside):
            for x in inside:
                remove(x, 'in a muted group')
            remove(t, reason)
    changed = True
    while changed:                      # groups that have nothing left in them
        changed = False
        parents = {als.group_id(t) for t in tracks_el}
        for t in list(tracks_el):
            if als.is_group(t) and t.get('Id') not in parents and not protected(t):
                remove(t, 'empty group')
                changed = True


def remove_orphan_envelopes(root, report):
    """Automation of a parameter that is gone with its plugin."""
    alive = {str(i) for i in als.pointee_ids(root)}
    for envelopes in root.iter('Envelopes'):
        for env in list(envelopes):
            target = env.find('EnvelopeTarget/PointeeId')
            if target is not None and target.get('Value') not in alive:
                envelopes.remove(env)
                report['automation removed'] += 1


def check(root, source):
    """What would stop Live from loading the set, as far as that can be seen from outside."""
    was = als.validate(source)          # a quirk the original has and Live opens is not ours
    problems = [x for x in als.validate(root) if x not in was]
    twice = lambda r: {i for i, n in Counter(als.pointee_ids(r)).items() if n > 1}
    if twice(root) - twice(source):
        problems.append('%d new duplicate pointee ids' % len(twice(root) - twice(source)))
    for devices in root.iter('Devices'):
        seen = [d.get('Id') for d in devices]
        if len(seen) != len(set(seen)):
            problems.append('two devices with the same Id in one chain')
    alive = {str(i) for i in als.pointee_ids(root)}
    dangling = sum(1 for e in root.iter('PointeeId') if e.get('Value') not in alive)
    if dangling:
        problems.append('%d references to parameters that are gone' % dangling)
    left = Counter(als.device_name(d) for d in root.iter() if d.tag in PLUGIN_TAGS)
    if left:
        problems.append('plugins left: %s' % dict(left))
    known = {(e.tag, tuple(sorted(e.attrib))) for e in source.iter()}
    for pattern, device in _presets.items():
        known |= {(e.tag, tuple(sorted(e.attrib))) for e in device.iter()}
    known |= {(d.tag, ('Id',)) for d in _presets.values()}
    odd = {(e.tag, tuple(sorted(e.attrib))) for e in root.iter()} - known
    if odd:
        problems.append('elements Live may not know: %s' % sorted(odd)[:5])
    return problems


def convert(root):
    source = copy.deepcopy(root)
    report = {'plugins': Counter(), 'drum notes': Counter(), 'take lanes': 0, 'tracks removed': [],
              'automation removed': 0}
    replace_plugins(root, report)
    remove_take_lanes(root, report)
    remove_unused_tracks(root, report)
    remove_orphan_envelopes(root, report)
    report['problems'] = check(root, source)
    return report


def output_path(path):
    return restyle.next_version_path(path).replace(' (restyle', ' (ableton only')


def main():
    path, write = sys.argv[1], '--write' in sys.argv
    root = als.load(path)
    report = convert(root)
    for (name, kind), n in sorted(report['plugins'].items(), key=lambda kv: -kv[1]):
        print('%4d  %-34s -> %s' % (n, name, kind))
    print('take lanes removed: %d, automation removed: %d' % (report['take lanes'], report['automation removed']))
    for reason, n in Counter(r for _, r in report['tracks removed']).most_common():
        print('tracks removed, %s (%d): %s' % (reason, n, ', '.join(name for name, r in report['tracks removed'] if r == reason)))
    if report['drum notes']:
        print('drum notes with no sound in the built-in kit:', dict(report['drum notes']))
    if report['problems']:
        raise SystemExit('not written: ' + '; '.join(report['problems']))
    if write:
        out = output_path(path)
        als.save(root, out)
        print('wrote %s (%.1f MB, was %.1f MB)' % (out, os.path.getsize(out) / 1e6, os.path.getsize(path) / 1e6))


if __name__ == '__main__':
    main()
