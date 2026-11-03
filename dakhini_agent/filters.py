"""Cheap title/description filtering before any audio is downloaded."""
from . import config
from .models import Candidate


def score(c: Candidate) -> int:
    title = c.title.lower()
    text = f"{c.title}\n{c.description}\n{c.channel}".lower()
    s = 0
    for t in config.POSITIVE_TERMS:
        t = t.lower()
        if t in title:
            s += 3
        elif t in text:
            s += 1
    for t in config.NEGATIVE_TERMS:
        if t in title:
            s -= 4
        elif t in text:
            s -= 1
    return s


def keep(c: Candidate) -> bool:
    c.score = score(c)
    if c.score < 2:
        return False
    if c.duration is not None and not (
        config.MIN_DURATION_S <= c.duration <= config.MAX_DURATION_S
    ):
        return False
    return True
