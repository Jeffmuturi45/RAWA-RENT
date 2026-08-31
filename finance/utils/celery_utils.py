# finance/utils/celery_utils.py

import logging
from celery import current_app
from django.conf import settings

logger = logging.getLogger(__name__)


def is_celery_available():
    """
    Check if Celery is available and can connect to the broker.
    Returns True if Celery is available, False otherwise.
    """
    try:
        # Check if we're in eager mode (development)
        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
            return True

        # Check if Celery is configured
        if not hasattr(settings, 'CELERY_BROKER_URL'):
            return False

        # Try to ping the broker
        inspect = current_app.control.inspect()
        ping_result = inspect.ping(timeout=1.0)

        if ping_result:
            logger.info("Celery is available with workers: %s",
                        list(ping_result.keys()))
            return True
        else:
            logger.warning("Celery is configured but no workers are running.")
            return False

    except Exception as e:
        logger.warning(f"Celery is not available: {str(e)}")
        return False


def get_task_status(task_id):
    """
    Get the status of a Celery task.
    """
    from celery.result import AsyncResult

    try:
        result = AsyncResult(task_id)
        return {
            'id': task_id,
            'status': result.status,
            'result': result.result if result.ready() else None,
            'ready': result.ready(),
            'successful': result.successful() if result.ready() else None,
        }
    except Exception as e:
        logger.error(f"Error getting task status: {str(e)}")
        return None
