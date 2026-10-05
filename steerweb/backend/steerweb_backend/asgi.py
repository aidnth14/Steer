"""
ASGI config for steerweb_backend project.

Routes HTTP to Django as usual and WebSocket connections (/ws/lobby/) to the game app's
Channels consumer -- this is the multiplayer transport, replacing steer/server.py + net.py.
"""

import os

import django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'steerweb_backend.settings')
django.setup()

import game.routing  # noqa: E402  (must come after django.setup())

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AllowedHostsOriginValidator(
        URLRouter(game.routing.websocket_urlpatterns)
    ),
})
