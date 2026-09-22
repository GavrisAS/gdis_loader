"""GDIS data loader."""

SOURCE_VERSION = "0.1"

try:
    from gdis_loader._build_version import (  # ty: ignore[unresolved-import]
        BUILD_VERSION as _BUILD_VERSION,
    )
except ModuleNotFoundError:
    __version__ = SOURCE_VERSION
else:
    __version__ = _BUILD_VERSION
