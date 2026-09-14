"""
Frame extraction (section 11 pipeline step).

Like transcript.py, this is a placeholder for a future, legitimate frame-
extraction step (e.g. from video the user has explicitly uploaded, which
SavedFlow does have legitimate access to). Since V1 does not implement
video download/access, this always reports frames as unavailable rather
than pretending to have inspected frames it never saw.
"""


def get_frames_if_available(item):
    return None
