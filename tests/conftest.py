import pytest
import asyncio
import os

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

def pytest_addoption(parser):
    parser.addoption(
        "--live", action="store_true", default=False, help="Run live API tests"
    )

def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        # If --live is passed, do not skip anything
        return
    skip_live = pytest.mark.skip(reason="need --live option to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
