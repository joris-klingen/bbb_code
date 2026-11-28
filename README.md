# bbb_code

Tools for managing Ableton Live projects, built for and with the band
[Bovenburen](https://bovenburen.com); bbb is short for Bovenburen band. This is where they are
developed: small, readable Python that works on real sets and stays out of the way of the music.

Python 3.9+, standard library only. Nothing to install.

## What is in it

| | |
|---|---|
| **Restyle** | One convention for every set: group and track names, order, colors, solo keys, returns. As a local web app or from the command line. A set is only written if it still sounds the same. → [docs/restyle.md](docs/restyle.md) |
| **Controller** | A Launchpad Mini that finds your groups and song parts by name in any set: solo, mute, jump to a part on the bar line, see what plays and what is armed. → [docs/controllers.md](docs/controllers.md) |
| **Facts** | What a set is, as plain data: tempo, song parts, tracks, plugins, audio files. `python3 -m bbb.facts song.als` |
| **Ableton only** | A light version of a set that needs nothing but Live: third-party plugins replaced by built-in devices. A first version. → [PLAN-stock.md](PLAN-stock.md) |

## Try it

    python3 -m bbb.app                        # the restyle app, at http://localhost:8765
    python3 -m bbb.restyle song.als           # report what would change; --write to do it
    python3 -m bbb.install_remote             # put the controller scripts in Live
    python3 -m unittest discover -s tests -t .

Source sets are never written over: every result is a new version next to the original. The
tests run on small synthetic sets; real sets stay out of the repo.

## Related

[BoothCue](https://github.com/joris-klingen/boothcue) is the VST plugin that goes with these
tools: it aids singers while tracking, with lyrics and chords in time with the set.

## License

MIT, see [LICENSE](LICENSE).
