"""Service modules for the Dedalus Labs Proxy."""

from dedalus_labs_proxy.services.dedalus import (
    DedalusClient,
    DedalusRunner,
    global_client,
)

__all__ = ["DedalusClient", "DedalusRunner", "global_client"]
