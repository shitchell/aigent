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
    parser.addoption(
        "--e2e", action="store_true", default=False, help="Run E2E UI tests"
    )

def pytest_collection_modifyitems(config, items):
    skip_live = pytest.mark.skip(reason="need --live option to run")
    skip_e2e = pytest.mark.skip(reason="need --e2e option to run")
    
    for item in items:
        if "live" in item.keywords and not config.getoption("--live"):
            item.add_marker(skip_live)
        if "e2e" in item.keywords and not config.getoption("--e2e"):
            item.add_marker(skip_e2e)
