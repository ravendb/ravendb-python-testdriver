from __future__ import annotations

from datetime import timedelta
from typing import Optional

from ravendb_embedded import ServerOptions


class TestServerOptions(ServerOptions):
    """Embedded server options for a test run.

    The defaults a test server needs (in-memory storage, a scratch data directory, an empty
    settings file) are applied by the driver to *any* `ServerOptions` it is given, right before
    the server starts, so `configure_server` keeps accepting the base type and nobody has to
    migrate. This subclass is the documented entry point for that intent, and the place where
    test-only defaults that cannot be inferred from a plain `ServerOptions` will live.
    """

    # pytest collects Test*-named classes it finds in a test module's namespace, imported ones
    # included, and warns about the __init__ it cannot construct.
    __test__ = False

    def __init__(self) -> None:
        super().__init__()
        self.run_in_memory: bool = True


class GetDocumentStoreOptions:
    def __init__(self):
        self.wait_for_indexing_timeout: Optional[timedelta] = None

    @classmethod
    def with_timeout(cls, timeout: timedelta) -> GetDocumentStoreOptions:
        options = cls()
        options.wait_for_indexing_timeout = timeout
        return options
