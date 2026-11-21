"""BBB Ableton conventions: the single source of truth for names, order, colors and solo keys.

Colors are indices into Live's 70-color palette (0-69), as stored in the .als XML.
Solo keys are computer-keyboard mappings on the track's solo button (Mixer/HeadKeyMidi).
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Group:
    name: str                 # canonical name, top-level groups are CAPS
    color: int
    solo: Optional[str]       # solo hotkey; families share a key (PIANO solos with KEYS on 3)
    family: str               # core group this belongs to
    optional: bool = False    # only present when a song needs it
    aliases: List[str] = field(default_factory=list)  # existing names that map onto this group (lowercase)


# Top-level order. Optional groups sit directly after their family's core group.
GROUPS = [
    Group('DRUMS',    12, '1', 'DRUMS', aliases=['drums', 'drums live']),
    Group('PERC',     12, '1', 'DRUMS', optional=True, aliases=['perc']),
    Group('BASS',     23, '2', 'BASS', aliases=['bass']),
    Group('KEYS',      3, '3', 'KEYS', aliases=['keys']),
    Group('PIANO',     3, '3', 'KEYS', optional=True, aliases=['piano']),
    Group('SYNTHS',   30, '4', 'SYNTHS', aliases=['synths', 'synth', 'juno']),
    Group('STRINGS',  30, '4', 'SYNTHS', optional=True, aliases=['strings']),  # or '6' when it stands on its own
    Group('GUIT',      2, '5', 'GUIT', aliases=['guit', 'guitar', 'guitar rythm']),
    Group('GUIT ACC',  2, '6', 'GUIT', optional=True, aliases=['guit acc', 'acc guitar']),  # '5' when not really distinct
    Group('VOX LEAD',  7, '7', 'VOX LEAD', aliases=['vox lead', 'vox main', 'vox', 'vocals']),
    Group('BACKINGS',  5, '8', 'BACKINGS', aliases=['backings', 'vox backing', 'vox backings', 'vox back']),
    # Ideas, old takes and alternatives go here instead of being deleted. Always last, folded.
    Group('ARCHIVE',  69, None, 'ARCHIVE', aliases=['archive', 'bin', 'old', 'unused']),
]

# Naming rule for tracks called 'rec', 'NN-Audio', 'NN-MIDI': <prefix> + the subgroup names,
# without repeated words, numbered when several end up with the same name in one group.
# Empty 'rec' tracks (no clips at all) are the ready-to-record tracks and keep their name.
REC_PREFIX = {
    'DRUMS': 'drums', 'PERC': 'perc', 'BASS': 'bass', 'KEYS': 'keys', 'PIANO': 'piano',
    'SYNTHS': 'synth', 'STRINGS': 'strings', 'GUIT': 'guit', 'GUIT ACC': 'guit acc',
    'VOX LEAD': 'vox', 'BACKINGS': 'back',
}
REC_MAX_WORDS = 4   # longer than this: prefix + nearest subgroup only

# Standard subgroups inside a top-level group (Title case), in this order.
SUBGROUPS = {
    'VOX LEAD': ['Vox Verse', 'Vox Chorus'],
}

# Generic song layout for the Parts track: (name, bars, clip color). Colors follow existing use.
SECTION_COLORS = {'intro': 17, 'verse': 23, 'pre': 26, 'chorus': 14, 'post': 26, 'bridge': 26, 'outro': 26}
SECTIONS = [(n, bars, SECTION_COLORS[n]) for n, bars in [
    ('intro', 4), ('verse', 8), ('verse', 8), ('pre', 4), ('chorus', 8), ('post', 4),
    ('verse', 8), ('pre', 4), ('chorus', 8), ('bridge', 8), ('chorus', 8), ('chorus', 8), ('outro', 4),
]]

SCENES = 8

# Helper tracks that come before the groups, in this order.
HELPERS = [
    ('length', 16),   # song length marker
    ('Parts', 7),     # section clips (verse/chorus/...)
]

# Return tracks, in this order. Live prefixes the letter itself (A-, B-, ...).
RETURNS = [
    ('amb', 18),       # Pro-R 2, short room
    ('verb', 19),      # Decapitator -> Pro-R 2, hall
    ('delay', 25),     # EchoBoy, synced
    ('drum par', 2),   # Devil-Loc Deluxe
    ('scheps', 3),     # SCHEPS rack (parallel vocal chain): DeEsser -> Pultec -> LA-2A -> Pultec -> DeEsser
]

# Default send levels in dB, set on the top-level groups. Optional groups use their family's.
SENDS = {
    'DRUMS':    {'amb': -20, 'drum par': -10},
    'KEYS':     {'amb': -20, 'verb': -20},
    'SYNTHS':   {'amb': -20, 'verb': -20, 'delay': -25},
    'GUIT':     {'amb': -20, 'delay': -25},
    'VOX LEAD': {'amb': -20, 'verb': -20, 'delay': -25, 'scheps': -10},
    'BACKINGS': {'amb': -20, 'verb': -20},
}

# Plugins that are never part of the standard chains (they depend on the source).
EXCLUDED_PLUGINS = ('Pro-Q',)   # matches Pro-Q 3 and Pro-Q 4


def excluded(device_name):
    return device_name.startswith(EXCLUDED_PLUGINS)

# Groups whose tracks keep their own names (no 'rec' / auto renaming inside).
KEEP_NAMES_IN = ['ARCHIVE']

# Groups that always come last, even after top-level tracks/groups that are not in the template.
LAST_GROUPS = ['ARCHIVE']

# Groups that are left alone entirely.
IGNORE_GROUPS = ['live rig']


def group_by_name(name):
    for g in GROUPS:
        if g.name == name:
            return g
    raise KeyError(name)


# --- looser naming, for the controllers --------------------------------------------------
# Restyle only renames what it knows exactly (the aliases above). The controllers have to find
# the groups and song parts in any set as it is, so they also go by the words in a name:
# 'Vocals', 'vocs lead', 'BVs', 'Gtr acoustic', 'Verse2', 'last chorus', 'refrein'.

# Words that mean the same, under the word used in WORD_GROUPS.
WORDS = {
    'drums':   ['drums', 'drum', 'drms', 'drm', 'kit', 'drumkit'],
    'perc':    ['perc', 'percussion', 'percs'],
    'bass':    ['bass', 'bas', 'basses'],
    'keys':    ['keys', 'key', 'keyboard', 'keyboards', 'kbd', 'toetsen'],
    'piano':   ['piano', 'pianos', 'pno'],
    'synths':  ['synths', 'synth', 'syn', 'synthesizer', 'synthesizers', 'juno'],
    'strings': ['strings', 'string', 'strijkers'],
    'guit':    ['guit', 'guitar', 'guitars', 'guits', 'gtr', 'gtrs', 'git', 'gitaar', 'gitaren'],
    'acc':     ['acc', 'acoustic', 'ac', 'akoestisch', 'akoestische'],
    'vox':     ['vox', 'vocal', 'vocals', 'voc', 'vocs', 'voice', 'voices', 'zang', 'stem'],
    'lead':    ['lead', 'main', 'ld'],
    'back':    ['back', 'backs', 'backing', 'backings', 'bv', 'bvs', 'bgv', 'bgvs', 'bvox',
                'choir', 'koor', 'koortjes'],
}
# Words that say nothing about which group it is.
FILLER = ['group', 'grp', 'bus', 'all', 'total', 'sum', 'mix', 'the', 'live', 'el', 'electric',
          'rhythm', 'rythm']
# The words of a name (in any order, without filler) -> group.
WORD_GROUPS = {
    ('drums',): 'DRUMS', ('perc',): 'PERC', ('bass',): 'BASS', ('keys',): 'KEYS',
    ('piano',): 'PIANO', ('synths',): 'SYNTHS', ('strings',): 'STRINGS',
    ('guit',): 'GUIT', ('acc', 'guit'): 'GUIT ACC',
    ('vox',): 'VOX LEAD', ('lead', 'vox'): 'VOX LEAD',
    ('back',): 'BACKINGS', ('back', 'vox'): 'BACKINGS',
}
_WORD = {variant: word for word, variants in WORDS.items() for variant in variants}

# Kinds of song parts (the controllers color by kind). A part with one of PART_BEFORE in its
# name is none of these: a pre-chorus is not a chorus.
PART_WORDS = {
    'verse':  ['verse', 'verses', 'vers', 'vrs', 'v', 'couplet', 'strofe'],
    'chorus': ['chorus', 'choruses', 'chor', 'chrs', 'c', 'refrein', 'ref', 'refrain', 'hook'],
    'intro':  ['intro', 'in', 'start', 'opening'],
    'outro':  ['outro', 'out', 'end', 'ending', 'einde', 'slot'],
}
PART_BEFORE = ['pre', 'post', 'prechorus', 'postchorus']
_PART = {variant: kind for kind, variants in PART_WORDS.items() for variant in variants}


def _words(name):
    return re.findall(r'[a-z]+', name.lower())      # 'Verse2', 'pre-chorus', 'BVs (new)'


def group_named(name):
    """The name of the group a track name stands for, or None: exactly (name or alias), else by
    its words when every word is known and together they mean one group."""
    n = name.strip().lower()
    if n in [x.lower() for x in IGNORE_GROUPS]:
        return None
    for g in GROUPS:
        if n == g.name.lower() or n in g.aliases:
            return g.name
    words = [w for w in _words(name) if w not in FILLER]
    if not words or any(w not in _WORD for w in words):
        return None
    return WORD_GROUPS.get(tuple(sorted({_WORD[w] for w in words})))


def part_kind(name):
    """'verse', 'chorus', 'intro' or 'outro' for the name of a song part, or None."""
    words = _words(name)
    if any(w in PART_BEFORE for w in words):
        return None
    return next((_PART[w] for w in words if w in _PART), None)
