# finance/management/commands/check_celery.py

from django.core.management.base import BaseCommand
from finance.utils.celery_utils import is_celery_available
from django.conf import settings


class Command(BaseCommand):
    help = 'Check Celery status and configuration'

    def handle(self, *args, **options):
        self.stdout.write("Checking Celery configuration...")
        self.stdout.write(
            f"  CELERY_TASK_ALWAYS_EAGER: {getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', 'Not Set')}")
        self.stdout.write(
            f"  CELERY_BROKER_URL: {getattr(settings, 'CELERY_BROKER_URL', 'Not Set')}")

        self.stdout.write("\nChecking Celery availability...")
        available = is_celery_available()

        if available:
            self.stdout.write(self.style.SUCCESS("  ✅ Celery is available"))
        else:
            self.stdout.write(self.style.WARNING(
                "  ⚠️ Celery is not available"))
            self.stdout.write("     Tasks will run synchronously.")

        self.stdout.write("\nRecommendations:")
        if not available:
            self.stdout.write("  1. Start Redis: redis-server")
            self.stdout.write(
                "  2. Start Celery worker: celery -A rawarent worker -l info")
            self.stdout.write(
                "  3. Or set CELERY_TASK_ALWAYS_EAGER=True in .env")
        else:
            self.stdout.write("  Celery is configured correctly.")
