"""
One WebSocket per logged-in user, joined to a per-user group so
apps.notifications.utils can push straight to whichever tabs/devices
that user currently has open. This consumer only ever pushes data out
-- every mutation (mark read, mark all read) still goes through the
existing HTTP views in apps.notifications.views exactly as it did
before this phase, which then broadcast the updated state back over
the group. That keeps one code path for "what happens when a
notification is read" instead of two.
"""
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


def group_name_for_user(user_id):
    return f'notifications_user_{user_id}'


@database_sync_to_async
def _unread_count(user):
    from .models import Notification
    return Notification.objects.filter(recipient=user, is_read=False).count()


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            await self.close(code=4001)
            return

        self.group_name = group_name_for_user(user.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send the current unread count immediately on connect so the
        # badge is correct even if it was stale from before this socket
        # existed (e.g. another device marked things read meanwhile).
        await self.send_json({'event': 'unread_count', 'count': await _unread_count(user)})

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # No client -> server messages are expected; mutations happen over
    # the existing HTTP endpoints. Anything received is ignored rather
    # than erroring, so a stray keepalive ping from a proxy doesn't
    # kill the connection.
    async def receive_json(self, content, **kwargs):
        return

    # ---- Group event handlers (dispatched by channel_layer.group_send) ----

    async def notification_message(self, event):
        await self.send_json({'event': 'notification', 'notification': event['notification']})

    async def unread_count_update(self, event):
        await self.send_json({'event': 'unread_count', 'count': event['count']})
