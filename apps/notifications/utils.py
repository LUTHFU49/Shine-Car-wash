"""
Central place other apps should call to raise an in-app notification.
Direct Notification.objects.create() calls are discouraged outside this
module so the transport (in-app row + a live WebSocket push, see
apps.notifications.consumers) stays in one place.
"""
from .models import Notification, NotificationLevel


def _serialize(notification):
    return {
        'public_id': str(notification.public_id),
        'title': notification.title,
        'message': notification.message,
        'level': notification.level,
        'url': notification.url,
        'created_at': notification.created_at.strftime('%b %d, %H:%M'),
    }


def _push(notification):
    """Broadcasts a freshly created notification to every WebSocket the
    recipient currently has open, and refreshes their unread badge.
    Best-effort: if no channel layer is configured (e.g. a management
    command run outside the web process) this quietly does nothing --
    the Notification row itself is already saved either way, so a
    missed push just means the badge catches up on next page load."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    from .consumers import group_name_for_user
    group_name = group_name_for_user(notification.recipient_id)
    unread_count = Notification.objects.filter(recipient_id=notification.recipient_id, is_read=False).count()

    async_to_sync(channel_layer.group_send)(group_name, {
        'type': 'notification_message', 'notification': _serialize(notification),
    })
    async_to_sync(channel_layer.group_send)(group_name, {
        'type': 'unread_count_update', 'count': unread_count,
    })


def push_unread_count(user):
    """Called after a read/mark-all-read HTTP request so every other
    open tab/device for that user updates its badge immediately too."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    from .consumers import group_name_for_user
    unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
    async_to_sync(channel_layer.group_send)(group_name_for_user(user.id), {
        'type': 'unread_count_update', 'count': unread_count,
    })


def notify(user, title, message='', level=NotificationLevel.INFO, url=''):
    if user is None:
        return None
    notification = Notification.objects.create(
        recipient=user, title=title, message=message, level=level, url=url,
    )
    _push(notification)
    return notification


def notify_roles(roles, title, message='', level=NotificationLevel.INFO, url=''):
    """Notify every active user holding any of the given roles (e.g. every
    Manager + Super Admin about a low-stock item)."""
    from apps.accounts.models import User

    if isinstance(roles, str):
        roles = [roles]

    recipients = User.objects.filter(role__in=roles, is_active=True, is_deactivated=False)
    return [notify(recipient, title, message, level, url) for recipient in recipients]
