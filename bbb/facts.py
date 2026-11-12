"""Read what a Live set is, as plain data: tempo, time signature, song parts, locators, tracks.

Usage: python3 -m bbb.facts <project.als>      prints JSON

Read only. This is the 'read structure' side of the tools: the same facts for every version
of every project, to index, compare and hand to other programs (BoothCue reads the parts
the same way). Times are in beats from the start of the arrangement.
"""
import json
import sys

from . import als, plugins


def tempo(root):
    ls = als.liveset(root)
    for main in ('MainTrack', 'MasterTrack'):   # Live 12 / Live 11 and older
        v = als.val(ls, f'{main}/DeviceChain/Mixer/Tempo/Manual')
        if v is not None:
            return float(v)
    return None


def time_signature(root):
    """(numerator, denominator). Live stores both in one number: 201 = 4/4, 200 = 3/4, 302 = 6/8."""
    ls = als.liveset(root)
    for main in ('MainTrack', 'MasterTrack'):
        v = als.val(ls, f'{main}/DeviceChain/Mixer/TimeSignature/Manual')
        if v is not None:
            n = int(float(v))
            if 0 <= n < 99 * 5:
                return n % 99 + 1, 2 ** (n // 99)
    return 4, 4


def parts_track(root):
    """The MIDI track named 'parts' (any case) whose arrangement clips are the song parts."""
    for t in als.tracks(root):
        if t.tag == 'MidiTrack' and als.name(t).strip().lower() == 'parts':
            return t
    return None


def sections(root):
    t = parts_track(root)
    events = als.arrangement_events(t) if t is not None else None
    if events is None:
        return []
    num, den = time_signature(root)
    bar = num * 4 / den   # beats (quarter notes) per bar
    out = []
    for c in sorted(events.findall('MidiClip'), key=lambda c: float(c.get('Time'))):
        start = float(als.val(c, 'CurrentStart', c.get('Time')))
        end = float(als.val(c, 'CurrentEnd', start))
        if end > start and als.val(c, 'Disabled', 'false') != 'true':
            out.append(dict(name=als.val(c, 'Name', '').strip(), start=start, end=end,
                            bar=start / bar + 1, bars=(end - start) / bar, color=int(als.val(c, 'Color', '-1'))))
    return out


def locators(root):
    locs = als.liveset(root).findall('Locators/Locators/Locator')
    return sorted((dict(time=float(l.get('Time')), name=als.val(l, 'Name', '')) for l in locs),
                  key=lambda l: l['time'])


def track_list(root):
    by_id = {t.get('Id'): t for t in als.tracks(root)}
    out = []
    for t in als.tracks(root):
        depth, g = 0, als.group_id(t)
        while g != '-1' and g in by_id:
            depth, g = depth + 1, als.group_id(by_id[g])
        clips = [c for c in t.iter() if c.tag in als.CLIP_TAGS]
        _, lanes = als.take_lanes(t)
        lane_clips = {id(c) for lane in lanes for c in lane.iter() if c.tag in als.CLIP_TAGS}
        devs = als.device_list(t)
        out.append(dict(id=t.get('Id'), name=als.name(t), type=t.tag.replace('Track', ''), depth=depth,
                        group=None if als.group_id(t) == '-1' else als.group_id(t), color=als.color(t),
                        muted=als.val(t, 'DeviceChain/Mixer/Speaker/Manual', 'true') == 'false',
                        clips=len(clips) - len(lane_clips), take_lanes=len(lanes),
                        devices=plugins.devices(t) if devs is not None else []))
    return out


def samples(root):
    """Audio files the set refers to (relative to the project folder where Live stored it so)."""
    return sorted({als.clip_source(c)[2:] for c in root.iter('AudioClip')} - {'?'})


def facts(root):
    num, den = time_signature(root)
    secs = sections(root)
    return dict(live=root.get('Creator'), tempo=tempo(root), time_signature=f'{num}/{den}',
                length=max([s['end'] for s in secs], default=None), sections=secs,
                parts_track=parts_track(root) is not None, locators=locators(root),
                tracks=track_list(root), samples=samples(root))


def main():
    if len(sys.argv) != 2 or sys.argv[1].startswith('-'):
        sys.exit(__doc__.strip())
    json.dump(facts(als.load(sys.argv[1])), sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == '__main__':
    main()
