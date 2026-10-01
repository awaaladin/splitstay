"""Endpoints Vercel Cron calls in place of Celery Beat. Vercel sends `Authorization: Bearer $CRON_SECRET`."""
import hmac
import logging

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

log = logging.getLogger(__name__)


def _tasks():
    from apps.groups.tasks import enforce_deadlines
    from apps.notifications.tasks import send_due_reminders
    from apps.payouts.tasks import reconcile_pending
    from apps.recurrence.tasks import spawn_due_cycles

    return {
        "enforce-deadlines": enforce_deadlines,
        "spawn-recurring-cycles": spawn_due_cycles,
        "send-due-reminders": send_due_reminders,
        "reconcile-pending-payouts": reconcile_pending,
    }


@csrf_exempt
@require_GET
def run_task(request, name):
    secret = getattr(settings, "CRON_SECRET", "") or ""
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not secret or not hmac.compare_digest(supplied, secret):
        return HttpResponseForbidden("forbidden")
    task = _tasks().get(name)
    if task is None:
        return JsonResponse({"detail": "unknown task"}, status=404)
    result = task()  # called directly: runs synchronously inside this invocation
    log.info("cron %s -> %s", name, result)
    return JsonResponse({"task": name, "result": result})


urlpatterns = [path("api/cron/<str:name>/", run_task, name="cron")]
