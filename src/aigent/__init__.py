# simple_agent package
from importlib.metadata import version, PackageNotFoundError

_pkg = __package__.split('.')[0]

try:
    __version__: str = version(_pkg)
except PackageNotFoundError:
    __version__: str = "0.0.1-dev"  # fallback for running directly from source
