from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Service-layer code raises Django ValidationError; surface it as a clean 400."""
    if isinstance(exc, DjangoValidationError):
        from rest_framework.exceptions import ValidationError

        exc = ValidationError(detail=exc.message_dict if hasattr(exc, "error_dict") else exc.messages)
    return exception_handler(exc, context)
