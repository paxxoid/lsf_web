import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def scheduler_test(message: str = "Django Q2 scheduler is working") -> str:
    """
    Simple test task for verifying Django Q2.

    The returned value will be stored in the Django Q2
    successful task record.
    """
    current_time = timezone.now()
    result = f"{message} at {current_time.isoformat()}"

    logger.info(result)

    return result