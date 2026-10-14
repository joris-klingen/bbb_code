"""BBB Ableton conventions: the single source of truth for names, order, colors and solo keys.

Colors are indices into Live's 70-color palette (0-69), as stored in the .als XML.
Solo keys are computer-keyboard mappings on the track's solo button (Mixer/HeadKeyMidi).
"""
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
    ('vox par', 3),    # SCHEPS rack: DeEsser -> Pultec -> LA-2A -> Pultec -> DeEsser
]

# Default send levels in dB, set on the top-level groups. Optional groups use their family's.
SENDS = {
    'DRUMS':    {'amb': -20, 'drum par': -10},
    'KEYS':     {'amb': -20, 'verb': -20},
    'SYNTHS':   {'amb': -20, 'verb': -20, 'delay': -25},
    'GUIT':     {'amb': -20, 'delay': -25},
    'VOX LEAD': {'amb': -20, 'verb': -20, 'delay': -25, 'vox par': -10},
    'BACKINGS': {'amb': -20, 'verb': -20},
}

# Plugins that are never part of the standard chains (they depend on the source).
EXCLUDED_PLUGINS = ('Pro-Q',)   # matches Pro-Q 3 and Pro-Q 4


def excluded(device_name):
    return device_name.startswith(EXCLUDED_PLUGINS)

# Groups that are left alone entirely.
IGNORE_GROUPS = ['live rig']


def group_by_name(name):
    for g in GROUPS:
        if g.name == name:
            return g
    raise KeyError(name)
