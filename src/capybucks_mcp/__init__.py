"""Read-only MCP server for the capybucks market-data library."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("capybucks-mcp")
except PackageNotFoundError:  # pragma: no cover — editable / source tree
    __version__ = "0.1.0"

__all__ = ["__version__"]
