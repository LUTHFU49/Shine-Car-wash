"""
ASGI config for the ShineHub project.

Wraps Django's HTTP application with Channels' ProtocolTypeRouter so
the same process can serve normal HTTP requests AND WebSocket
connections (used for real-time, no-page-reload notifications).
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shinehub.settings')

django_asgi_app = get_asgi_application()

# Imported after get_asgi_application() so app registry is populated
# before any app-level websocket routing modules are imported.
from apps.notifications.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    # AuthMiddlewareStack resolves the Django session cookie sent with
    # the WebSocket handshake into scope['user'], the same session a
    # person is already logged in with over HTTP -- no separate
    # WebSocket auth step required.
    'websocket': AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
