#!/usr/bin/env python3
"""Platform identity and per-image configuration, shared by every Osmium build.

A single source tree feeds both the x86 and the Raspberry Pi images. The handful
of settings that genuinely differ per platform (the OTA repo/manifest bases, the
release-image filename prefix, the platform name itself) are NOT hardcoded in the
app code. Instead the image build writes ``/etc/hifi-player/platform.conf`` — a
plain ``KEY=VALUE`` file — and this module loads it into the process environment
*without overriding anything already set*. The existing
``os.environ.get('HIFI_*', <x86 default>)`` call sites then pick up the right
value with no change. On x86, or when the file is absent, the baked-in x86
defaults apply and behaviour is identical to before.

Keys are used verbatim as environment-variable names, e.g.::

    # /etc/hifi-player/platform.conf  (written by the Raspberry image build)
    HIFI_PLATFORM=rpi
    HIFI_IMAGE_PREFIX=osmium-rpi-
    HIFI_OTA_REPO=adri6412/osmium-sound-raspberry

This module has no third-party dependencies and never raises on a missing or
malformed file: it is safe to import at the very top of every server process.
"""

import os

# Where the image build drops the per-platform config. Overridable mainly so the
# test suite (and a dev box simulating a Pi) can point at a scratch file.
PLATFORM_CONF = os.environ.get('HIFI_PLATFORM_CONF', '/etc/hifi-player/platform.conf')

_loaded = False


def _parse_conf(path):
    """Parse a KEY=VALUE file into a dict. Blank lines and ``#`` comments are
    ignored; surrounding single/double quotes around the value are stripped.
    Returns an empty dict if the file is missing or unreadable."""
    out = {}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                if key:
                    out[key] = val
    except OSError:
        pass
    return out


def load(path=None):
    """Load the platform config into ``os.environ`` via ``setdefault`` (so an
    explicit environment value always wins). Idempotent: safe to call repeatedly
    and from every process at import time."""
    global _loaded
    if _loaded and path is None:
        return
    for key, val in _parse_conf(path or PLATFORM_CONF).items():
        os.environ.setdefault(key, val)
    if path is None:
        _loaded = True


def _detect_platform():
    """Best-effort hardware detection when nothing declared the platform.
    Mirrors the historical ``_is_rpi()`` check (``/proc/device-tree/model``)."""
    try:
        with open('/proc/device-tree/model', 'rb') as fh:
            if b'Raspberry Pi' in fh.read():
                return 'rpi'
    except OSError:
        pass
    return None


def platform():
    """Return the platform name: 'rpi' or 'x86' (the default). Resolution order:
    an explicit ``HIFI_PLATFORM`` / platform.conf value, then hardware
    detection, then 'x86'."""
    load()
    return (os.environ.get('HIFI_PLATFORM') or _detect_platform() or 'x86').lower()


def is_raspberry():
    """True when running on a Raspberry Pi build. Replaces the old per-file
    ``_is_rpi()`` helpers."""
    return platform() == 'rpi'


# Populate the environment on import so module-level ``os.environ.get('HIFI_*')``
# constants in the servers see the per-image defaults.
load()
