# ravendb-test-driver: labs

Runnable, self-checking guides for using the test driver. Each lab ships a script next to it, so
you can run the exact code the guide shows.

| Lab | Covers | Needs system .NET? |
|-----|--------|--------------------|
| [01](01-attach-to-server.md) | Attach to a server you run yourself (Docker, testcontainers, shared CI) | No |
| [02](02-embedded-per-test.md) | Embedded server, one isolated database per test (the default) | Yes |
| [03](03-seeding-indexes.md) | Seed data and query an index (`setup_database`, `wait_for_indexing`) | Yes |

Looking for how to run RavenDB itself (embedded, or self-contained without .NET)? That belongs to
the [`ravendb-python-embedded`](https://github.com/ravendb/ravendb-python-embedded) package and
has its own labs there.
