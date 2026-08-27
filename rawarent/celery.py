"""
Celery application entry point for RAWA-RENT.
"""
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rawarent.settings')

app = Celery('rawarent')

# Pull config from Django settings, namespace CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all INSTALLED_APPS
app.autodiscover_tasks()


# ─────────────────────────────────────────
# BEAT SCHEDULE  (periodic tasks)
# ─────────────────────────────────────────
app.conf.beat_schedule = {

    # Run at 07:00 Nairobi time every day.
    # The task itself checks billing_day against today's date,
    # so it is safe to run daily — it only generates when due.
    'generate-rent-notices-daily': {
        'task': 'finance.tasks.generate_rent_notices',
        'schedule': crontab(hour=7, minute=0),
    },

    # Mark overdue charges every morning at 06:00
    'mark-overdue-charges-daily': {
        'task': 'finance.tasks.mark_overdue_charges',
        'schedule': crontab(hour=6, minute=0),
    },

    # Send rent-due reminder notifications 3 days before due date
    'send-rent-reminders-daily': {
        'task': 'finance.tasks.send_rent_due_reminders',
        'schedule': crontab(hour=8, minute=0),
    },
}

app.conf.timezone = 'Africa/Nairobi'


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
