# Ableton-only version of a set: note and plan

`bbb/stock.py` makes a version of a Live set that needs nothing but Live: third-party plugins
replaced by built-in devices, take lanes and unused tracks removed. Light, loads anywhere,
sounds roughly the same. Never the mix itself. First tried on one real project
(21 Nov 2026): 277 plugin instances of 32 kinds, 11.4 MB to 2.9 MB, opens in Live 12.4.6.

    python3 -m bbb.stock song.als            report only
    python3 -m bbb.stock song.als --write    writes 'song <next version> (ableton only).als'

## How it works now

- **Replacements come from Live's own presets** (Core Library `.adv` files, same format as the
  set), so every inserted device is one Live wrote itself.
- **Settings are carried over where they can be read.** Live keeps the values of the parameters
  a plugin publishes (UAD, Valhalla, Soundtoys, Waves DeEsser, Pro-C 2). FabFilter Pro-Q and
  Pro-R keep theirs as a plain list of numbers. Other plugins get a preset as it is.
- **One table** (`REPLACE` in `stock.py`) says what each plugin becomes. A plugin not in it is
  removed and reported.
- **Unused tracks go:** no clips, only deactivated clips, muted (unless the mute is automated),
  and groups left empty. Helper tracks, returns and tracks something is routed from stay.
- **Checks before writing:** no new duplicate ids, no automation pointing at removed
  parameters, no plugin left, no element Live would not know. Not a check of the sound: only
  ears can do that.

## Known gaps

- **Drums.** No single built-in acoustic kit, so Superior Drummer becomes a 606 with remapped
  notes; notes 82, 90 and 105 are dropped (unknown articulations). Needs a real kit: a drum
  rack built from Live's acoustic samples, which means generating rack XML (rack presets are
  stored differently from racks inside a set).
- **Sampled instruments.** What Kontakt and MODO Bass played is not in the set; the stand-in
  is guessed from the track name.
- **Levels.** Compressor thresholds and makeup are rules of thumb; the master limiter adds no
  gain, so the result is quieter. Rules should be tuned from listening, one number at a time.
- **Racks** from Live's library (`.adg`) cannot be inserted yet, only single devices.
- **Only tested on one set,** with Live 12.4 on this Mac (the preset path is fixed).

## Plan

1. **Let the user say what they have.** The target is not always "Live and nothing else". A
   small profile, asked once and kept:
   - Live edition (Intro / Standard / Suite), which decides the built-in devices available
     (Auto Shift, Hybrid Reverb, Roar, Drift ... are not in every edition);
   - installed packs (Drum Essentials, Orchestral Strings, Electric Pianos ...), which widen
     the instrument choices;
   - third-party plugins to keep, per maker or per plugin ("FabFilter: yes", "UAD: no").
     A kept plugin is left alone; only the rest is replaced.
   The converter then picks, per plugin, the best replacement the profile allows, and falls
   back in steps (kept plugin -> pack instrument -> core device -> removed).
2. **Report before writing.** Per plugin: what it becomes, what was carried over, what will
   sound different. The user can overrule a row.
3. **Close the gaps above,** drums first.
4. **A skill around it:** look at an unknown set, propose replacements for plugins not yet in
   the table (by name and by the parameters they publish), run the converter, and say plainly
   what is approximate. Rules only go in after someone has listened to them.
5. **The other direction, later:** from the same profile, flag what a collaborator would be
   missing before a set is sent to them.
