# BBB songbook: plan

The short version of the plan, to work from in this repo.

**Idea.** One record per song (parts, lyrics, chords, key, tempo, its Live projects). BoothCue, the
Google Drive sheets, the band's phones and the restyle of Live sets are views of that record.

**Decided (Joris, 12 Nov 2026).** Local-first plus web. The app is master for lyrics and chords;
Drive mirrors. For Ableton: read structure, and clean up / restructure. Users: Joris in the studio
and the whole band at rehearsals (not on stage).

**Pieces.**
- *Songbook*: a private repo of text files, one folder per song: `song.yaml`, `lyrics.txt` and
  `chords.txt` in BoothCue's own formats, `facts/<version>.json`, `notes.md`. A small hosted hub
  serves a phone app (offline), signs in the band and runs the LLM tools. Also exposed as an MCP
  server, so the songbook can be used from Claude.
- *Studio agent* (grows from this repo): watches the project folders, reads every version of every
  set with `bbb.facts`, links projects to songs, runs restyle / restructure, writes the files
  BoothCue loads. Live sets and audio never leave the Mac.
- *BoothCue*: gets "link song folder" (load lyrics and chords when the files change, save tapped
  timings back), later broadcasts the playhead so phones can follow Live. Its plain C++ core can be
  compiled to WebAssembly so the phone app uses the same parser and display.

**Who is master of what.** Text: the songbook. Line timings: BoothCue. Parts, tempo, tracks: the
Live set (read only; changes are proposed as a restructure). Drive: a mirror, edits there come back
as proposals.

**LLM rule.** The model never edits a Live set. It writes a plan in a fixed vocabulary (rename,
recolour, move, group, archive); the engine applies it to a copy; `als.sound_fingerprint` must match
or nothing is written. Elsewhere the model handles messy text (importing the Drive doc, classifying
unknown groups, wording version changelogs) and deterministic code goes first.

**Steps.**
0. Done: tests, `bbb.facts`, take-lane and app fixes. To do: run `bbb.facts` on a real project.
1. Songbook repo and formats, import of the Drive doc, BoothCue song-folder link, read-only phone app.
2. Studio agent: index of all projects and versions, version changelogs, MCP server, `inputs.yaml`.
3. Restructure by plan, editing by the band, Drive mirror, chart vs detected chords.
4. Rehearsal room: BoothCue core as WebAssembly, phones follow the playhead, play-along with bounces.

**Open decisions.** Where the hub runs (recommended: hosted), which Drive documents to import, who
may edit, and a first Mac build of BoothCue in Live before step 1.
