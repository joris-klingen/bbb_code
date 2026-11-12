# bbb_code

Tools to keep the BBB Ableton projects consistent: track/group naming, order, colors,
solo hotkeys and (later) take-lane cleanup. Python 3.9+, standard library only.

- `bbb/spec.py` — the conventions (group names, order, colors, solo keys, returns). Edit here.
- `bbb/als.py` — read/write `.als` files (gzipped XML) and track helpers.
- `bbb/restyle.py` — restyle of an existing project, per category: names, order, colors, group
  solo keys, returns, and optional take-lane cleanup (empty / duplicate, unreferenced lanes).
- `bbb/app.py` + `bbb/app.html` — local web app around restyle: load an `.als`, see the
  differences with the template, pick categories, write a new version.
- `bbb/facts.py` — read only: what a set is, as JSON (tempo, time signature, song parts from the
  `parts` track, locators, tracks with their plugins, audio files). `python3 -m bbb.facts song.als`
- `tests/` — `python3 -m unittest discover -s tests -t .` Runs on small synthetic sets built in
  `tests/fixture.py`; real sets stay out of the repo.
- `bbb/build_template.py` — one-off generator of the first template (now maintained by hand in
  `../bbb_ableton_template/BBB template Project`).

Run the app: double-click `BBB Restyle.command` (or run `python3 -m bbb.app` from this folder);
it opens http://localhost:8765 in the browser. Close the Terminal window to stop it.

The app has two views: **Project** (one `.als`, with differences per category and the track
structure) and **All projects** (scan a whole folder, see per project how far its latest version
is from the template, and restyle a selection in one go). Every write is verified to sound the
same as the original; if anything that affects playback differs, nothing is written.

Or restyle from the command line. Without `--write` it only reports; with `--write` it saves
a new version after the newest one in the folder, e.g. `song 2.5.als` with `song 2.6.als`
present -> `song 2.7 (restyle).als`.
`--only` picks categories (default: the ones that are on by default in the app):

    python3 -m bbb.restyle "../../c_opzetjes/my song Project/my song 2.5 (harmonics).als" --write
    python3 -m bbb.restyle song.als --write --only group_names,solo_keys,track_colors

Never write over a source `.als`; output always goes to a new file.

The app looks for projects three folders above `bbb/` (the Bovenburen folder); set `BBB_ROOT` to
point it somewhere else. It only answers its own page on localhost, not other websites.
