"""Install the controller scripts for Live: `python3 -m bbb.install_remote`

Writes the folder `BBB_Launchpad` (Launchpad Mini MK3) in `~/Music/Ableton/User Library/Remote
Scripts`: `remote_script.py` (as `__init__.py`), `launchpad.py`, `groups.py`, `spec.py`, and a
`device.py` that says which controller it is. Run it again after changing the groups in
`spec.py`; Live reads the scripts when it starts.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.expanduser('~/Music/Ableton/User Library/Remote Scripts')
CONTROLLERS = {'BBB_Launchpad': 'launchpad'}      # folder -> module


def install(scripts=SCRIPTS):
    """Returns the folders written."""
    targets = []
    for folder, module in CONTROLLERS.items():
        target = os.path.join(scripts, folder)
        os.makedirs(target, exist_ok=True)
        shutil.copyfile(os.path.join(HERE, 'remote_script.py'), os.path.join(target, '__init__.py'))
        for name in (module, 'groups', 'spec'):
            shutil.copyfile(os.path.join(HERE, name + '.py'), os.path.join(target, name + '.py'))
        with open(os.path.join(target, 'device.py'), 'w') as f:
            f.write('"""Which controller this script is for (written by bbb.install_remote)."""\n'
                    'from .%s import FORWARD_CCS, FORWARD_NOTES, NAME, Surface  # noqa: F401\n' % module)
        targets.append(target)
    return targets


if __name__ == '__main__':
    for target in install(*sys.argv[1:2]):
        print('Installed in', target)
    print('Restart Live, then Settings > Link, Tempo & MIDI > Control Surface:')
    print('  BBB Launchpad  Input and Output: Launchpad Mini MK3 (LPMiniMK3 DAW)')
