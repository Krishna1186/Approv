"""Keep exhaustive local-catalogue acceptance explicit, without hiding fast checks."""
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--schema-exhaustive", action="store_true", default=False,
        help="run schema acceptance against the complete local catalogue caches",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "schema_exhaustive: full local catalogue acceptance (opt in with --schema-exhaustive)"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--schema-exhaustive"):
        return
    skip = pytest.mark.skip(reason="full catalogue: pass --schema-exhaustive to run")
    for item in items:
        if "schema_exhaustive" in item.keywords:
            item.add_marker(skip)
