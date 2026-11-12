"""Cosmetic restyle of an existing project, split into categories that can be switched on/off.

Usage: python3 -m bbb.restyle <project.als> [--write] [--only cat1,cat2]

Without --write it only prints what would change. With --write it saves the result as the
next version next to the original (e.g. 'song 2.5 (x).als' -> 'song 2.6 (restyle).als');
the original is never modified. Tracks, returns, devices, sends and clips are never added
or removed; only the take-lane categories remove (empty or duplicate, unreferenced) lanes.
"""
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Callable

from . import als, spec

# key: (title, on by default, description)
CATEGORIES = {
    'group_names': ('Group names', True, 'Top-level groups and helper tracks get their canonical name'),
    'solo_keys': ('Solo hotkeys', True, 'Top-level groups get their solo key'),
    'track_colors': ('Track colors', True, 'Every track in a group gets the group color'),
    'clip_colors': ('Clip colors', True, 'Clips (arrangement, session, take lanes) get the group color'),
    'order': ('Group order', True, 'Helpers, then groups in template order, then the rest'),
    'auto_names': ('Auto names', True, "'17-Kontakt 7' becomes 'kontakt 7'"),
    'rec_names': ("'rec' names", False,
                  "'rec' / 'NN-Audio' / 'NN-MIDI' get instrument + subgroup, e.g. 'vox chorus main 2'"),
    'returns': ('Returns', True, 'Return names and colors (never their order)'),
    'empty_lanes': ('Empty take lanes', False, 'Remove take lanes without clips that nothing refers to'),
    'dup_lanes': ('Duplicate take lanes', False,
                  'Remove take lanes identical to an earlier lane (same or other track) that nothing refers to'),
}

# Effect on the sound per category: (level, explanation). Levels: 'none' or 'caution'.
# Whatever is selected, the written file is checked: everything that can affect playback
# must be identical to the original (see als.sound_fingerprint), otherwise nothing is written.
SOUND = {
    'group_names': ('none', 'Names are not used for routing or playback.'),
    'solo_keys': ('none', 'Only a key mapping; nothing is soloed.'),
    'track_colors': ('none', 'Visual only.'),
    'clip_colors': ('none', 'Visual only.'),
    'order': ('none', 'Routing goes by track id and group, not by position.'),
    'auto_names': ('none', 'Names are not used for routing or playback.'),
    'rec_names': ('none', 'Names are not used for routing or playback.'),
    'returns': ('none', 'Sends go by position, which stays the same.'),
    'empty_lanes': ('none', 'Removes nothing playable.'),
    'dup_lanes': ('caution', 'Sound unchanged, but these takes can no longer be re-comped on this track '
                             '(identical copies stay on the track listed).'),
}
NAME_CATEGORIES = ('group_names', 'auto_names', 'rec_names', 'returns')

AUTO_NAME = re.compile(r'^\d+-(.*)$')                  # Live's default 'NN-Device' names
GENERIC = re.compile(r'^(rec|audio|midi|group)$', re.I)  # names that say nothing


def is_generic(t):
    """'rec', or a Live default like '61-Audio' / '15-MIDI' / '16-Group' that was never renamed."""
    name = als.name(t)
    m = AUTO_NAME.match(name)
    return bool(GENERIC.match(name) or (m and not als.val(t, 'Name/UserName', '')
                                        and GENERIC.match(m.group(1).split(' ')[0])))


def rec_base_name(t, group, by_id):
    """Name for a generic track: instrument prefix + subgroup names, no repeated words."""
    subs, g = [], als.group_id(t)
    while g != '-1' and als.group_id(by_id[g]) != '-1':   # stop below the top-level group
        if not is_generic(by_id[g]):
            subs.append(als.name(by_id[g]).lower())
        g = als.group_id(by_id[g])
    subs.reverse()

    def join(parts):
        words = []
        for w in ' '.join(parts).split():
            if w not in words:
                words.append(w)
        return words
    prefix = spec.REC_PREFIX.get(group.name, group.name.lower())
    def names_instrument(parts):  # 'pre back', 'backings chorus', 'guitar solo'
        return any(w.startswith(p) for p in prefix.split() for w in ' '.join(parts).split())
    # keep a subgroup's own words when it already names the instrument
    words = join(([] if names_instrument(subs) else [prefix]) + subs)
    if len(words) > spec.REC_MAX_WORDS:
        words = join(([] if names_instrument(subs[-1:]) else [prefix]) + subs[-1:])
    if t.tag == 'MidiTrack' and 'midi' not in words:
        words.append('midi')
    return ' '.join(words)


def has_clips(t):
    return any(e.tag in als.CLIP_TAGS for e in t.iter())
RETURN_ALIASES = {'amb': ['ambience', 'amb'], 'verb': ['long verb', 'verb', 'reverb'], 'delay': ['delay'],
                  'drum par': ['dums par', 'drums par', 'drum par'], 'scheps': ['scheps', 'vox par']}


@dataclass
class Change:
    category: str
    track: str          # display path, e.g. '#61 VOX LEAD › Vox Chorus › rec'
    track_id: str       # '' when not about one track
    detail: str
    apply: Callable = field(repr=False)
    # what it does to the track list, for the before/after view: name / color / solo / clips /
    # lanes (delta) / order (list of track ids, top to bottom)
    effect: dict = field(default_factory=dict)


@dataclass
class Plan:
    changes: list
    notes: list
    tracks: list        # current structure for display: dicts with name/type/depth/color/solo/flags
    warnings: list = field(default_factory=list)  # dicts: categories (empty = any write), text
    baseline: list = field(default_factory=list)  # integrity problems already in the original file


def _helper(name):
    for hname, hcol in spec.HELPERS:
        if name.lower() == hname.lower():
            return hname, hcol
    return None


def _group(name):
    n = name.strip().lower()
    if n in [x.lower() for x in spec.IGNORE_GROUPS]:
        return None
    for g in spec.GROUPS:
        if n == g.name.lower() or n in g.aliases:
            return g
    return None


def _return(name):
    n = name.split('-', 1)[-1].strip().lower()
    for rname, rcol in spec.RETURNS:
        if n in RETURN_ALIASES[rname]:
            return rname, rcol
    return None


def _name_generic(generic, block, add, setter):
    """Add rec_names changes for one top-level group; number names that repeat anywhere in it
    or clash with an existing track name there."""
    by_base = {}
    for t, base in generic:
        by_base.setdefault(base, []).append(t)
    generic_ids = {t.get('Id') for t, _ in generic}
    existing = {als.name(x).lower() for x in block if x.get('Id') not in generic_ids and not als.is_group(x)}
    for base, ts in by_base.items():
        numbered = len(ts) > 1 or base in existing
        for n, t in enumerate(ts, 1):
            new = f'{base} {n}' if numbered else base
            add('rec_names', t, f'→ {new}', setter(als.set_name, t, new), {'name': new})


def analyze(root):
    tracks = als.tracks(root)
    by_id = {t.get('Id'): t for t in tracks}
    pos = {t.get('Id'): i + 1 for i, t in enumerate(tracks)}
    changes, notes = [], []

    def path(t):
        parts = [als.name(t)]
        g = als.group_id(t)
        while g != '-1':
            parts.append(als.name(by_id[g]))
            g = als.group_id(by_id[g])
        return f"#{pos[t.get('Id')]} " + ' › '.join(reversed(parts))

    def add(cat, t, detail, fn, effect=None):
        changes.append(Change(cat, path(t), t.get('Id'), detail, fn, effect or {}))

    def setter(fn, *args):
        return lambda: fn(*args)

    # --- top-level blocks -------------------------------------------------------
    blocks = [als.subtree(root, t) if als.is_group(t) else [t]
              for t in tracks if als.group_id(t) == '-1' and t.tag != 'ReturnTrack']
    keyed = []
    for i, block in enumerate(blocks):
        generic = []
        top = block[0]
        h = _helper(als.name(top))
        g = _group(als.name(top)) if als.is_group(top) else None
        if h:
            if als.name(top) != h[0]:
                add('group_names', top, f'→ {h[0]}', setter(als.set_name, top, h[0]), {'name': h[0]})
            if als.color(top) != h[1]:
                add('track_colors', top, f'color {als.color(top)} → {h[1]}', setter(als.set_color, top, h[1]),
                    {'color': h[1]})
            keyed.append(((0, [x[0] for x in spec.HELPERS].index(h[0])), i, block))
            continue
        if not g:
            kind = 'group' if als.is_group(top) else 'track'
            notes.append(f'Top-level {kind} “{als.name(top)}” is not in the template; left as is, placed after the groups.')
            keyed.append(((2, 0), i, block))
            continue
        keyed.append(((3 if g.name in spec.LAST_GROUPS else 1, spec.GROUPS.index(g)), i, block))
        if als.name(top) != g.name:
            add('group_names', top, f'→ {g.name}', setter(als.set_name, top, g.name), {'name': g.name})
        if als.solo_key(top) != (g.solo or ''):
            add('solo_keys', top, f'key {als.solo_key(top) or "none"} → {g.solo or "none"}',
                setter(als.set_solo_key, top, g.solo), {'solo': g.solo or ''})
        for t in block:
            if als.color(t) != g.color:
                add('track_colors', t, f'color {als.color(t)} → {g.color}', setter(als.set_color, t, g.color),
                    {'color': g.color})
            clips = [c for c in t.iter() if c.tag in als.CLIP_TAGS and als.val(c, 'Color') != str(g.color)]
            if clips:
                add('clip_colors', t, f'{len(clips)} clips → {g.color}',
                    setter(lambda cs, col: [als.set_val(c, 'Color', col) for c in cs], clips, g.color),
                    {'clips': len(clips)})
            if t is top or g.name in spec.KEEP_NAMES_IN:
                continue
            name, user = als.name(t), als.val(t, 'Name/UserName', '')
            m = AUTO_NAME.match(name)
            if is_generic(t):
                if als.is_group(t):
                    notes.append(f'Group “{path(t)}” has a default name; name it by hand (its tracks skip it).')
                elif not has_clips(t) and GENERIC.match(name):
                    pass  # empty 'rec' track: ready to record, keeps its name
                else:
                    generic.append((t, rec_base_name(t, g, by_id)))
            elif m and not user:
                add('auto_names', t, f'→ {m.group(1).lower()}', setter(als.set_name, t, m.group(1).lower()),
                    {'name': m.group(1).lower()})
        _name_generic(generic, block, add, setter)

    seen = set()
    for key, _, block in keyed:
        n = als.name(block[0]).lower()
        if key[0] in (1, 3) and _group(n).name in seen:
            notes.append(f'More than one top-level group maps to {_group(n).name}.')
        if key[0] in (1, 3):
            seen.add(_group(n).name)

    # --- order ------------------------------------------------------------------
    keyed_sorted = sorted(keyed, key=lambda x: (x[0], x[1]))
    if [b[0] for _, _, b in keyed_sorted] != [b[0] for _, _, b in keyed]:
        new_tops = [b[0] for _, _, b in keyed_sorted]
        order = [t for _, _, b in keyed_sorted for t in b] + [t for t in tracks if t.tag == 'ReturnTrack']

        def reorder():
            tel = als.tracks_el(root)
            current = list(tel)
            inner, last = current[0].tail, current[-1].tail
            for t in current:
                tel.remove(t)
            for t in order:
                tel.append(t)
            als._retail(tel, inner, last)
        changes.append(Change('order', 'top level', '', ' | '.join(als.name(t) for t in new_tops), reorder,
                              {'order': [t.get('Id') for t in order]}))

    # --- returns ----------------------------------------------------------------
    for t in tracks:
        if t.tag != 'ReturnTrack':
            continue
        r = _return(als.name(t))
        if r is None:
            notes.append(f'Return “{als.name(t)}” is not in the template; left as is.')
            continue
        old = als.name(t)
        letter = old.split('-', 1)[0] + '-' if '-' in old else ''
        if als.val(t, 'Name/UserName') != r[0]:
            def rn(t=t, n=r[0], eff=letter + r[0]):
                als.set_val(t, 'Name/UserName', n)
                als.set_val(t, 'Name/EffectiveName', eff)
            add('returns', t, f'→ {letter}{r[0]}', rn, {'name': letter + r[0]})
        if als.color(t) != r[1]:
            add('returns', t, f'color {als.color(t)} → {r[1]}', setter(als.set_color, t, r[1]), {'color': r[1]})

    # --- take lanes -----------------------------------------------------------------
    first_seen = {}   # lane fingerprint -> track path where it first occurs
    for t in tracks:
        inner, lanes = als.take_lanes(t)
        if not lanes:
            continue
        events = als.arrangement_events(t)
        referenced = {als.val(c, 'TakeId') for c in (events if events is not None else [])}
        empty, dups = [], []
        for lane in lanes:
            clips = als.lane_clips(lane)
            free = lane.get('Id') not in referenced
            if not clips:
                if free:
                    empty.append(lane)
                continue
            fp = frozenset(als.clip_fingerprint(c) for c in clips)
            if fp in first_seen and free:
                dups.append((lane, first_seen[fp]))
            first_seen.setdefault(fp, path(t))

        def remove(inner=inner, gone=None):
            tail = list(inner)[-1].tail
            for lane in gone:
                inner.remove(lane)
            if len(inner):
                inner[-1].tail = tail
        if empty:
            add('empty_lanes', t, f'{len(empty)} of {len(lanes)} lanes', setter(remove, inner, empty),
                {'lanes': -len(empty)})
        if dups:
            where = sorted({w for _, w in dups})
            add('dup_lanes', t, f'{len(dups)} of {len(lanes)} lanes, same as on: ' + '; '.join(where),
                setter(remove, inner, [l for l, _ in dups]), {'lanes': -len(dups)})

    # --- structure for display ----------------------------------------------------------
    flagged = {}
    for c in changes:
        flagged.setdefault(c.track_id, set()).add(c.category)
    struct = []
    for t in tracks:
        _, lanes = als.take_lanes(t)
        struct.append(dict(id=t.get('Id'), pos=pos[t.get('Id')], name=als.name(t), type=t.tag.replace('Track', ''),
                           depth=path(t).count(' › '), color=als.color(t), solo=als.solo_key(t),
                           lanes=len(lanes), flags=sorted(flagged.get(t.get('Id'), []))))
    warnings = []
    m4l = sum(1 for e in root.iter() if e.tag.startswith('MxDevice'))
    if m4l:
        warnings.append(dict(kind='m4l', categories=list(NAME_CATEGORIES),
                             text=f'This set has {m4l} Max for Live device(s). Some refer to tracks by name; '
                                  'check them after renaming.'))
    creator = root.get('Creator', '')
    if 'Live 11' in creator or 'Live 10' in creator:
        warnings.append(dict(kind='live_version', categories=[], text=f'Saved by {creator}. The new version is unchanged in sound, '
                                                 'but saving it from Live 12 upgrades it for good.'))
    return Plan(changes, notes, struct, warnings, als.validate(root))


def apply(root, plan, categories):
    """Apply the selected categories; order goes last because it rebuilds the track list."""
    done = []
    for c in sorted(plan.changes, key=lambda c: c.category == 'order'):
        if c.category in categories:
            c.apply()
            done.append(c)
    # only problems the restyle introduced count; some sets saved by Live already have quirks
    problems = [p for p in als.validate(root) if p not in plan.baseline]
    if problems:
        raise ValueError('validation failed: ' + '; '.join(problems))
    return done


VERSION = re.compile(r'^(.*?)(\d+)\.(\d+)(?!\d)')   # 'my song 2.5 (harmonics)' -> 2.5


def next_version_path(path):
    """Next free version after the most recently saved version of this song in its folder.

    Goes by save date, not by number: '3.41' may mean 3.4.1 (before 3.5) while '1.10' follows
    1.9, so numbers alone are ambiguous. E.g. newest 3.7 -> 3.8 (restyle); numbers that already
    exist are skipped.
    """
    d, f = os.path.split(path)
    stem = f[:-4]
    m = VERSION.match(stem)
    if m:
        prefix = m.group(1)
        versions = {}   # (major, minor) -> newest mtime among files with that version
        for o in os.listdir(d):
            x = VERSION.match(o[:-4]) if o.endswith('.als') else None
            if x and x.group(1).lower() == prefix.lower():
                v = (int(x.group(2)), int(x.group(3)))
                versions[v] = max(versions.get(v, 0), os.path.getmtime(os.path.join(d, o)))
        major, minor = max(versions, key=versions.get)
        minor += 1
        while (major, minor) in versions:
            minor += 1
        base = f'{prefix}{major}.{minor}'
    else:
        base = f'{stem} 1.1'
    out = os.path.join(d, base + ' (restyle).als')
    n = 2
    while os.path.exists(out):
        out = os.path.join(d, f'{base} (restyle {n}).als')
        n += 1
    return out


def restyle_file(path, categories):
    """Load, apply the categories, save as the next version, verified to sound identical.

    Returns (out_path, applied changes). Raises ValueError (and writes nothing) if anything
    that can affect playback differs from the original.
    """
    root = als.load(path)
    before = als.sound_fingerprint(root)
    plan = analyze(root)
    done = apply(root, plan, categories)
    diffs = als.compare_sound(before, als.sound_fingerprint(root), root)
    if diffs:
        raise ValueError('sound check failed, nothing written; changed: ' + ', '.join(diffs))
    out = next_version_path(path)
    tmp = out + '.partial'
    try:
        als.save(root, tmp)
        written = als.load(tmp)  # verify what actually landed on disk
        diffs = als.compare_sound(before, als.sound_fingerprint(written), written)
        if diffs:
            raise ValueError('sound check of the written file failed, nothing kept; changed: ' + ', '.join(diffs))
        os.rename(tmp, out)
    finally:
        if os.path.exists(tmp):   # a failed write or check leaves no half file behind
            os.remove(tmp)
    return out, done


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith('-'):
        sys.exit(__doc__.strip())
    path = args[0]
    cats = [k for k, (_, on, _) in CATEGORIES.items() if on]
    if '--only' in args:
        cats = args[args.index('--only') + 1:][:1]
        cats = cats[0].split(',') if cats else []
        unknown = [c for c in cats if c not in CATEGORIES]
        if unknown or not cats:
            sys.exit(f"--only takes categories from: {', '.join(CATEGORIES)}"
                     + (f" (unknown: {', '.join(unknown)})" if unknown else ''))
    root = als.load(path)
    plan = analyze(root)
    for c in plan.changes:
        mark = '*' if c.category in cats else ' '
        print(f'{mark} {c.category:12} {c.track}: {c.detail}')
    for n in plan.notes:
        print('  note', n)
    if '--write' in sys.argv:
        out, done = restyle_file(path, cats)
        print(f'wrote {out} ({len(done)} changes)')


if __name__ == '__main__':
    main()
