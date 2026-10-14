"""List devices/plugins per track."""
from . import als


def label(d):
    n = als.device_name(d)
    user = als.val(d, 'UserName', '')
    return f'{n} ({user})' if user and user != n else n


def devices(track):
    return [label(d) for d in als.device_list(track)]
