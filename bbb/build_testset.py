"""Build a small set to try the Launchpad script on (see docs/controllers.md).

Usage: python3 -m bbb.build_testset <BBB template.als> [out.als]

Made from the template, without plugins so it opens at once, with what the script has to cope with:

  column 1  DRUMS + PERC          a family of two: solo / mute take both
  column 3  KEYS + PIANO          same
  column 6  (no GUIT ACC)         no lights, the controls do nothing
  column 8  'vox backing'         a group found by an alias instead of its name
  'bass' inside DRUMS             not top level: must not react to column 2
  'fx' at top level, 'kick'       not a known group / inside a group: solo them in Live and
  inside DRUMS                    the unsolo button on the right lights up and clears both
"""
import os
import sys

from . import als

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'testsets',
                   'BBB controller test Project', 'BBB controller test.als')
VOLUMES = {'DRUMS': 0, 'PERC': -12, 'BASS': -6, 'KEYS': -18, 'PIANO': -3, 'SYNTHS': -30,
           'GUIT': -9, 'VOX LEAD': 0, 'vox backing': -24}       # dB


def build(template):
    root = als.load(template)
    tracks_el = als.tracks_el(root)
    by_name = {als.name(t): t for t in tracks_el}

    def add(src, name, parent=None, after=None):
        """A copy of track src, placed after the track (and its subtree) `after`."""
        t = als.clone_track(root, by_name[src])
        als.set_name(t, name)
        als.set_group_id(t, parent.get('Id') if parent is not None else '-1')
        als.set_solo_key(t, None)
        if parent is None:      # may be a copy from inside a group: send its audio to Main, like DRUMS
            for field in ('Target', 'UpperDisplayString', 'LowerDisplayString'):
                path = 'DeviceChain/AudioOutputRouting/' + field
                als.set_val(t, path, als.val(by_name['DRUMS'], path))
        last = after if after is not None else parent
        if als.is_group(last):
            last = als.subtree(root, last)[-1]
        tracks_el.insert(list(tracks_el).index(last) + 1, t)
        by_name[name] = t
        return t

    perc = add('DRUMS', 'PERC', after=by_name['DRUMS'])
    add('bass', 'shaker', parent=perc)
    piano = add('KEYS', 'PIANO', after=by_name['KEYS'])
    add('nord audio', 'piano', parent=piano)
    add('bass', 'kick', parent=by_name['DRUMS'])
    add('bass', 'bass', parent=by_name['DRUMS'])
    add('bass', 'fx', after=by_name['BACKINGS'])
    als.set_name(by_name['BACKINGS'], 'vox backing')
    by_name['vox backing'] = by_name['BACKINGS']

    for t in als.tracks(root):
        als.clear_devices(t)
    for name, db in VOLUMES.items():
        als.set_val(by_name[name], 'DeviceChain/Mixer/Volume/Manual', 10 ** (db / 20))

    inner, last = list(tracks_el)[0].tail, list(tracks_el)[-1].tail
    als._retail(tracks_el, inner, last)
    problems = als.validate(root)
    if problems:
        raise SystemExit('validation failed: ' + '; '.join(problems))
    return root


if __name__ == '__main__':
    out = os.path.normpath(sys.argv[2] if len(sys.argv) > 2 else OUT)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    als.save(build(sys.argv[1]), out)
    print('wrote', out)
