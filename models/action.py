"""Action schema (section 19)."""
from utils.dates import utcnow

ACTION_STATUSES = {"NOT_STARTED", "PLANNED", "IN_PROGRESS", "COMPLETED", "ABANDONED"}
ACTION_PRIORITIES = {"LOW", "MEDIUM", "HIGH"}


def new_action(item_id, title, description="", priority="MEDIUM", due_date=None):
    now = utcnow()
    return {
        "item_id": item_id,
        "title": title,
        "description": description,
        "priority": priority if priority in ACTION_PRIORITIES else "MEDIUM",
        "status": "NOT_STARTED",
        "due_date": due_date,
        "notes": "",
        "result": "",
        "rating": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }
