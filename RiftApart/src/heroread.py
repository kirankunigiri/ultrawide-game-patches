# Native hero reader. The pause map resolves this entity handle, then reads its transform.
# No candidate scans, copy voting, or indefinitely cached position. See TRACKING.md.
from mem import read, EXE
from player_tracking import HeroReader
from hero_states import HeroStateReader

_reader = HeroReader(read, EXE.lpBaseOfDll)
_states = HeroStateReader(_reader, EXE.lpBaseOfDll)


def hero_sample():
    return _reader.sample()


def tracking_status():
    return _reader.status


def hero_xz():
    sample = hero_sample()
    return sample.xz if sample else None


def hero_xz_filtered(max_step=3.0, confirm=3):
    # Compatibility for the existing benchmark. Identity/generation checks replace
    # voting and spike filtering; real teleports and fast movement should be immediate.
    return hero_xz()


def hero_heading():
    sample = hero_sample()
    return sample.heading if sample else None


def hide_state(sample):
    """Native hero state that should hide the overlay (cutscene, ...), else None."""
    return _states.active(sample.entity) if sample else None
