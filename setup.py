from setuptools import find_packages, setup

setup(
    name="ravendb-test-driver",
    packages=find_packages(exclude=["*.tests.*", "tests", "*.tests", "tests.*"]),
    version="6.0.0.post3",
    description="RavenDB package for writing integration tests against RavenDB server",
    long_description_content_type="text/markdown",
    long_description=open("README.md").read(),
    author="RavenDB",
    author_email="support@ravendb.net",
    url="https://github.com/ravendb/ravendb-python-testdriver",
    license="MIT",
    keywords=["ravendb", "nosql", "database", "test", "driver"],
    python_requires="~=3.7",
    install_requires=["ravendb-embedded~=5.2.5.post1", "ravendb~=5.2.5.post1"],
)
