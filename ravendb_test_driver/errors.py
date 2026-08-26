from typing import Iterable, List


class DriverCloseError(RuntimeError):
    """Raised when closing the driver hit one or more errors.

    Subclasses RuntimeError so existing `except RuntimeError` handlers keep working, and keeps
    the original exceptions in `exceptions` instead of flattening them into a string, which is
    what AggregateException.InnerExceptions gives the C# driver.
    """

    def __init__(self, exceptions: Iterable[BaseException]) -> None:
        self.exceptions: List[BaseException] = list(exceptions)
        super().__init__(
            f"{len(self.exceptions)} error(s) while closing the test driver: "
            + "; ".join(f"{type(e).__name__}: {e}" for e in self.exceptions)
        )
