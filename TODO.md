# TODO

## Use the recording input in track names

Generic `rec` tracks are now named by instrument + subgroup (`vox chorus main 2`). Add the
source a track records from, so e.g. two `bass` tracks become `bass DI` and `bass amp`.

- [ ] Joris: add `inputs.yaml` (interface channel map) to this folder
- [ ] Read it in `spec.py`; the standard library has no YAML parser, so either add PyYAML or
      keep the file to the simple `key: value` subset below and parse that ourselves
- [ ] In `restyle.rec_base_name`, append the source name when the track's input is in the map
      (only when it adds information, e.g. not `vox mic` for every vocal track)
- [ ] Optional: flag tracks whose input doesn't fit their group (a BASS track recording the vocal mic)

How Live stores the input (`DeviceChain/AudioInputRouting/Target`): `AudioIn/External/M1` is
mono input 2 (counted from 0), `AudioIn/External/S0` is stereo pair 1/2. The display string
next to it reads `Ext. In 2` / `Ext. In 1/2`, which is what the map should use.

Suggested format (input as Live shows it → short source name):

```yaml
# inputs.yaml: interface channel map
interface: RME …            # for reference only
inputs:
  "2": vox mic
  "11": bass DI
  "19": bass amp
  "4": guit amp
  "1/2": keys
  "7/8": synth
```
