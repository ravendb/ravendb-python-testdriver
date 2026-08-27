"""Lab 02: Embedded server, one isolated database per test (the default).

For: the normal way to write tests with the driver. Subclass RavenTestDriver (or hold an
instance); each get_document_store() returns a store backed by a fresh, isolated database that is
cleaned up afterwards, so tests never see each other's data. This path boots the embedded server
and therefore needs a matching .NET (see the README).

Run:  python labs/02_embedded_per_test.py
"""

from ravendb_test_driver import RavenTestDriver


def main() -> None:
    with RavenTestDriver() as driver:
        with driver.get_document_store() as first, driver.get_document_store() as second:
            assert first.database != second.database, (first.database, second.database)

            with first.open_session() as session:
                session.store({"name": "only in first"}, "people/1")
                session.save_changes()

            # The second store is a different database, so it cannot see the first store's data.
            with second.open_session() as session:
                assert session.load("people/1", dict) is None

    # You do not have to close the stores. Leaving the driver's `with` block closes whatever is
    # still open and deletes those databases, so a test that throws halfway still cleans up.
    with RavenTestDriver() as driver:
        forgotten = driver.get_document_store()  # no forgotten.close() anywhere
        assert forgotten.database.startswith("test_"), forgotten.database

    assert driver.disposed

    # The server is shared by every driver in the process, and nothing closes it before the
    # interpreter exits. Call this from your runner's teardown to keep that cost inside the run.
    RavenTestDriver.stop_test_server()

    print("Lab 02 OK: two stores, two isolated databases, driver-level cleanup, server stopped.")


if __name__ == "__main__":
    main()
