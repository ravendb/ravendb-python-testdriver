# ravendb-test-driver: server labs

Ways to provide a RavenDB server for your tests, from most convenient to most portable.

| Lab | Path | For whom | Needs system .NET? |
|-----|------|----------|--------------------|
| [03](03-attach-to-server.md) | Attach to a server you run yourself (Docker, testcontainers, shared CI) | Containerized CI pipelines | No |

The embedded options live in the `ravendb-python-embedded` repository:

- Lab 01 - embedded, zero-config (needs a system .NET)
- Lab 02 - external self-contained server (no .NET)

Every lab ships a runnable script next to it, so you can run the exact code the guide shows.
