from __future__ import annotations

from datetime import timedelta
from typing import Optional


class GetDocumentStoreOptions:
    def __init__(self):
        self.wait_for_indexing_timeout: Optional[timedelta] = None

    @classmethod
    def with_timeout(cls, timeout: timedelta) -> GetDocumentStoreOptions:
        options = cls()
        options.wait_for_indexing_timeout = timeout
        return options
