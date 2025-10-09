from setuptools import find_packages, setup

setup(
    name="ravendb-test-driver",
    packages=find_packages(exclude=["*.tests.*", "tests", "*.tests", "tests.*"]),
    version="7.1.2.post1",
    description="RavenDB package for writing integration tests against RavenDB server",
    long_description_content_type="text/markdown",
    long_description=open("README.md").read(),
    author="RavenDB",
    author_email="support@ravendb.net",
    url="https://github.com/ravendb/ravendb-python-testdriver",
    license="MIT",
    keywords=["ravendb", "nosql", "database", "test", "driver"],
    python_requires="~=3.9",
    license_files="LICENSE",
    install_requires=["ravendb-embedded==7.1.2.post1", "ravendb~=7.1.2"],
)
