"""Serialize MongoDB documents (ObjectId, datetime) into plain JSON-safe dicts."""
from datetime import datetime
from bson import ObjectId


def serialize_doc(doc):
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize_doc(d) for d in doc]
    if isinstance(doc, dict):
        out = {}
        for key, value in doc.items():
            if key == "_id":
                out["id"] = str(value)
            else:
                out[key] = serialize_doc(value)
        return out
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, datetime):
        return doc.isoformat()
    return doc
