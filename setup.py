from setuptools import find_packages, setup

setup(
    name="ravendb-python-testdriver",
    packages=find_packages(exclude=["*.tests.*", "tests", "*.tests", "tests.*"]),  # todo : adjust
    version="6.0",
    description="",  # todo
    author="RavenDB",
    author_email="support@ravendb.net",
    url="https://github.com/ravendb/ravendb-python-client",
    license="MIT",
    keywords=["ravendb", "nosql", "database", "test", "driver"],
    python_requires="~=3.7",
    install_requires=["ravendb-embedded~=5.2.5.post1", "ravendb~=5.2.5.post1"],
)
