from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("gttrl")
except PackageNotFoundError:
    __version__ = "2.0.0"
