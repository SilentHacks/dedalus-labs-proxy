"""Route modules for the Dedalus Labs Proxy."""

from dedalus_labs_proxy.routes.admin_usage import router as admin_usage_router
from dedalus_labs_proxy.routes.chat import router as chat_router
from dedalus_labs_proxy.routes.health import router as health_router
from dedalus_labs_proxy.routes.models import router as models_router

__all__ = ["admin_usage_router", "chat_router", "health_router", "models_router"]
