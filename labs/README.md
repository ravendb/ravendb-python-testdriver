# ravendb-test-driver: labs

Runnable, self-checking guides for using the test driver. Each lab ships a script next to it, so
you can run the exact code the guide shows.

The scripts are part of this repository and are not installed into `site-packages`. Clone or
download the repository first, then run them from its root.

| Lab | Covers | Needs system .NET? |
|-----|--------|--------------------|
| [01](01-attach-to-server.md) | Attach to a server you run yourself (Docker, testcontainers, shared CI) | No |
| [02](02-embedded-per-test.md) | Embedded server, one isolated database per test (the default) | Yes |
| [03](03-seeding-indexes.md) | Seed data and query an index (`setup_database`, `wait_for_indexing`) | Yes |
| [04](04-embedded-no-dotnet.md) | Self-contained embedded server, downloaded and cached automatically | No |
| [05](05-secured-embedded.md) | Secured embedded server with client-certificate authentication | Yes |

For lower-level server configuration, see the
[`ravendb-python-embedded`](https://github.com/ravendb/ravendb-python-embedded) labs.
