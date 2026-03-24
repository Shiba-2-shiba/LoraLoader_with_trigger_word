"""Remote metadata clients and providers."""

try:
    from .civarchive_client import CivArchiveMetadataClient
    from .civitai_client import CivitaiMetadataClient
    from .providers import (
        CivitaiMetadataProvider,
        CivArchiveMetadataProvider,
        RemoteModelMetadataProvider,
    )
except ImportError:
    from civarchive_client import CivArchiveMetadataClient
    from civitai_client import CivitaiMetadataClient
    from providers import (
        CivitaiMetadataProvider,
        CivArchiveMetadataProvider,
        RemoteModelMetadataProvider,
    )


__all__ = [
    "CivArchiveMetadataClient",
    "CivitaiMetadataClient",
    "CivitaiMetadataProvider",
    "CivArchiveMetadataProvider",
    "RemoteModelMetadataProvider",
]
