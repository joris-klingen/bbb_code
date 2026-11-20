"""Install the Launch Control XL script for Live: `python3 -m bbb.install_remote`

Copies `remote_script.py` (as `__init__.py`), `lcxl.py` and `spec.py` to
`~/Music/Ableton/User Library/Remote Scripts/BBB_Groups`. Run it again after changing the groups
in `spec.py`; Live reads the script when it starts.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.expanduser('~/Music/Ableton/User Library/Remote Scripts/BBB_Groups')
FILES = [('remote_script.py', '__init__.py'), ('lcxl.py', 'lcxl.py'), ('spec.py', 'spec.py')]


def install(target=TARGET):
    os.makedirs(target, exist_ok=True)
    for src, dst in FILES:
        shutil.copyfile(os.path.join(HERE, src), os.path.join(target, dst))
    return target


if __name__ == '__main__':
    print('Installed in', install(*sys.argv[1:2]))
    print('Restart Live, then Settings > Link, Tempo & MIDI > Control Surface: BBB Groups,')
    print('Input and Output: Launch Control XL. On the device: hold User, press 8.')
