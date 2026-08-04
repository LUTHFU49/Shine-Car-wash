from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.core.redirects import safe_redirect_target

from .models import Notification
from .utils import push_unread_count

PAGE_SIZE = 20


@login_required
def notification_list_view(request):
    queryset = Notification.objects.filter(recipient=request.user)
    paginator = Paginator(queryset, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'notifications/list.html', {'page_obj': page_obj})


@login_required
@require_POST
def mark_read_view(request, public_id):
    notification = get_object_or_404(Notification, public_id=public_id, recipient=request.user)
    notification.mark_read()
    push_unread_count(request.user)
    fallback = notification.url or 'notifications:list'
    return redirect(safe_redirect_target(request, request.POST.get('next'), fallback))


@login_required
@require_POST
def mark_all_read_view(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    push_unread_count(request.user)
    return redirect(safe_redirect_target(request, request.POST.get('next'), 'notifications:list'))


@login_required
@ratelimit(key='user', rate=settings.RATELIMIT_NOTIFICATIONS_POLL, block=True)
def unread_count_view(request):
    """Fallback for the topbar bell when its WebSocket isn't connected
    yet (or reconnecting) -- see static/js/notifications.js. The live
    path is the socket; this is just so the badge is never wrong for
    long if a connection drops."""
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'unread_count': count})


@login_required
@ratelimit(key='user', rate=settings.RATELIMIT_NOTIFICATIONS_POLL, block=True)
def recent_view(request):
    """Small JSON slice for the topbar dropdown."""
    notifications = Notification.objects.filter(recipient=request.user)[:8]
    data = [{
        'public_id': str(n.public_id),
        'title': n.title,
        'message': n.message,
        'level': n.level,
        'url': n.url or '',
        'is_read': n.is_read,
        'created_at': n.created_at.strftime('%b %d, %H:%M'),
    } for n in notifications]
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'results': data, 'unread_count': unread_count})
