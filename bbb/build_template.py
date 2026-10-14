"""Build the BBB template .als from existing projects that already follow the conventions.

Usage: python3 -m bbb.build_template <base.als> <vocal_source.als> <out_dir>

  base.als          project whose tracks, returns and plugins are reused (Charlotte studio)
  vocal_source.als  project whose Vox Verse / Vox Chorus chains are copied (my song)

Writes <out_dir>/BBB template.als with the core groups. This was the starting point; the
template in 'BBB template Project' is maintained by hand in Live since.

Clips, take lanes, automation and locators are removed, the mixer is reset to default
sends, scenes are trimmed, the Parts track gets a generic song layout, groups carry no
plugins (except the vocal subgroups) and tracks only a basic chain.
"""
import os
import sys

from . import als, spec

# Which track of the base project (Charlotte studio, Live 12.4.3) becomes which placeholder.
# Keyed by base track id; tracks not listed here are dropped.
BASE_HELPERS = {'255': 'length', '130': 'Parts'}
BASE_GROUPS = {'46': 'DRUMS', '42': 'BASS', '49': 'KEYS', '44': 'SYNTHS', '52': 'GUIT',
               '80': 'VOX LEAD', '270': 'BACKINGS'}
BASE_RETURNS = {'2': 'amb', '3': 'verb', '239': 'drum par', '271': 'scheps'}
NEW_RETURN = ('delay', '325', 'EchoBoy')  # name, base track to take the plugin from, plugin
# Children per group: (base track id, name). Under a group with subgroups, children are
# keyed by subgroup name; the same base id may be used twice (the second one is cloned).
BASE_CHILDREN = {
    'DRUMS': [('330', 'drums midi')],
    'BASS': [('302', 'bass')],
    'KEYS': [('298', 'keys audio'), ('328', 'keys midi')],
    'SYNTHS': [('303', 'synth audio')],
    'GUIT': [('313', 'guit amp')],
    'VOX LEAD': {'Vox Verse': [('325', 'vox verse')], 'Vox Chorus': [('325', 'vox chorus')]},
    'BACKINGS': [('326', 'backing')],
}
# Optional groups: (base track to clone as the child, child name)
OPTIONAL_CHILD = {
    'PERC': ('302', 'perc'),
    'PIANO': ('298', 'piano'),
    'STRINGS': ('303', 'strings'),
    'GUIT ACC': ('313', 'guit acc'),
}
# Basic chain per placeholder track: plugins kept from the base track. Unlisted = empty.
TRACK_CHAINS = {
    'drums midi': ['Superior Drummer 3'],
    'bass': ['UADx LA-2A Gray Compressor', 'Decapitator'],
    'guit amp': ['UADx LA-2A Silver Compressor'],
    'guit acc': ['UADx LA-2A Silver Compressor'],
    'backing': ['Pro-C 2'],
}
# Chains copied from the vocal source project, by track id there.
VOCAL_SOURCE = {
    'Vox Verse': '199',    # group chain
    'Vox Chorus': '389',   # group chain
    'vox verse': '484',    # Waves Tune Real-Time
    'vox chorus': '488',
}


class Builder:
    def __init__(self, base_path):
        self.root = als.load(base_path)
        self.tracks_el = als.tracks_el(self.root)
        self.by_id = {t.get('Id'): t for t in self.tracks_el}
        self.used = set()
        self.order = []

    def new_clone(self, src):
        t = als.clone_track(self.root, src)
        self.tracks_el.append(t)  # temporary, so the next clone gets a fresh track id
        return t

    def take(self, tid):
        """The base track itself the first time, a clone after that."""
        if tid in self.used:
            return self.new_clone(self.by_id[tid])
        self.used.add(tid)
        return self.by_id[tid]

    def place(self, t, name, color, parent=None, solo=None):
        als.set_name(t, name)
        als.set_color(t, color)
        als.set_group_id(t, parent.get('Id') if parent is not None else '-1')
        als.set_solo_key(t, solo)
        self.order.append(t)
        return t


def build(base_path, vocal_path, with_optional):
    b = Builder(base_path)
    root, ls = b.root, als.liveset(b.root)
    vocal = als.load(vocal_path)
    vocal_by_id = {t.get('Id'): t for t in als.tracks(vocal)}

    # prototypes for the generic Parts/length clips, taken before stripping
    proto = {k: next(b.by_id[tid].iter('MidiClip')) for tid, k in BASE_HELPERS.items()}

    als.strip_content(b.tracks_el)
    locs = ls.find('Locators/Locators')
    for l in list(locs):
        locs.remove(l)
    als.trim_scenes(root, spec.SCENES)
    als.remove_time_signature_changes(root)
    als.set_val(ls, 'Transport/CurrentTime', 0)

    # returns first, so every track (and every later clone) gets the extra send
    return_names = [n for n, _ in spec.RETURNS]
    rname, src_tid, plugin = NEW_RETURN
    plugin_el = next(d for d in als.device_list(b.by_id[src_tid]) if als.device_name(d) == plugin)
    first_return = next(t for t in b.tracks_el if t.tag == 'ReturnTrack')
    new_return = als.add_return(root, first_return, return_names.index(rname))
    als.device_list(new_return).append(als.clone(root, plugin_el))
    returns = {n: b.by_id[tid] for tid, n in BASE_RETURNS.items()}
    returns[rname] = new_return

    for tid, (hname, hcol) in zip(BASE_HELPERS, spec.HELPERS):
        b.place(b.take(tid), hname, hcol)

    base_group = {v: b.by_id[k] for k, v in BASE_GROUPS.items()}
    top_groups = []
    for g in spec.GROUPS:
        if g.optional and not with_optional:
            continue
        if g.optional:
            gt = b.place(b.new_clone(base_group[g.family]), g.name, g.color, solo=g.solo)
            src, cname = OPTIONAL_CHILD[g.name]
            b.place(b.new_clone(b.by_id[src]), cname, g.color, gt)
        else:
            gt = b.place(b.take(base_group[g.name].get('Id')), g.name, g.color, solo=g.solo)
            kids = BASE_CHILDREN[g.name]
            if isinstance(kids, dict):
                for sub in spec.SUBGROUPS[g.name]:
                    st = b.place(b.new_clone(gt), sub, g.color, gt)
                    for tid, cname in kids[sub]:
                        b.place(b.take(tid), cname, g.color, st)
            else:
                for tid, cname in kids:
                    b.place(b.take(tid), cname, g.color, gt)
        top_groups.append((g, gt))

    # plugins: groups empty, tracks a basic chain, vocal chains from the vocal source
    for t in b.order:
        n = als.name(t)
        if n in VOCAL_SOURCE:
            als.clear_devices(t)
            als.copy_devices(root, vocal_by_id[VOCAL_SOURCE[n]], t, skip=spec.excluded)
        elif als.is_group(t):
            als.clear_devices(t)
        else:
            als.keep_devices(t, TRACK_CHAINS.get(n, []))
    for t in returns.values():
        als.remove_devices(t, spec.excluded)

    for letter, (rname, rcol) in zip('ABCDEFGH', spec.RETURNS):
        t = returns[rname]
        als.set_val(t, 'Name/UserName', rname)
        als.set_val(t, 'Name/EffectiveName', f'{letter}-{rname}')
        als.set_color(t, rcol)
        b.order.append(t)

    for t in b.order:
        als.reset_mixer(t)
    als.reset_mixer(ls.find('MainTrack'))
    for g, gt in top_groups:
        for rname, db in spec.SENDS.get(g.family, {}).items():
            als.set_send(gt, return_names.index(rname), db)

    # generic song layout on Parts, total song length on length (4/4 assumed)
    parts, length = b.order[1], b.order[0]
    pos = 0
    events = als.arrangement_events(parts)
    for i, (sname, bars, scol) in enumerate(spec.SECTIONS):
        events.append(als.make_empty_midi_clip(root, proto['Parts'], pos, bars * 4, sname, scol, i))
        pos += bars * 4
    als.arrangement_events(length).append(
        als.make_empty_midi_clip(root, proto['length'], 0, pos, 'length', spec.HELPERS[0][1], 0))

    # rebuild the track list in the new order, keeping the file's indentation
    inner_tail, last_tail = list(b.tracks_el)[0].tail, list(b.tracks_el)[-1].tail
    for t in list(b.tracks_el):
        b.tracks_el.remove(t)
    for t in b.order:
        b.tracks_el.append(t)
    als._retail(b.tracks_el, inner_tail, last_tail)

    problems = als.validate(root)
    if problems:
        raise SystemExit('validation failed: ' + '; '.join(problems))
    return root


def main():
    base, vocal, out_dir = sys.argv[1:4]
    out = os.path.join(out_dir, 'BBB template.als')
    if os.path.exists(out):
        raise SystemExit(f'{out} already exists')
    als.save(build(base, vocal, with_optional=False), out)
    print('wrote', out)


if __name__ == '__main__':
    main()
