"""
BaseImporter defines the common contract every import method follows, so
routes/imports.py can treat API/export/manual import uniformly and so the
result shape is always the same (section 3.3's example response).
"""
from abc import ABC, abstractmethod


class ImportResult:
    def __init__(self):
        self.total_submitted = 0
        self.imported = 0
        self.duplicates = 0
        self.invalid = 0
        self.invalid_items = []
        self.imported_ids = []
        self.content_available = 0
        self.metadata_only = 0

    def to_dict(self):
        return {
            "total_submitted": self.total_submitted,
            "imported": self.imported,
            "duplicates": self.duplicates,
            "invalid": self.invalid,
            "invalid_items": self.invalid_items,
            "imported_ids": [str(i) for i in self.imported_ids],
            "content_available": self.content_available,
            "metadata_only": self.metadata_only,
        }


class BaseImporter(ABC):
    """Every importer takes some raw input and returns an ImportResult."""

    @abstractmethod
    def run(self, *args, **kwargs) -> ImportResult:
        raise NotImplementedError
