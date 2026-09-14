"""
User preference weighting (section 15).

Weights live in [0, 1] and drift toward 1 when the user marks matching
content useful, and toward 0 when they mark it not useful. The step size
is intentionally small and transparent (see services/ai/recommendations.py)
rather than a black-box learned rate.
"""
from utils.dates import utcnow

DEFAULT_WEIGHT = 0.5


def new_preference(topic, weight=DEFAULT_WEIGHT):
    now = utcnow()
    return {
        "topic": topic,
        "weight": max(0.0, min(1.0, weight)),
        "created_at": now,
        "updated_at": now,
    }
