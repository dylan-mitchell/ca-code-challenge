from django.core.exceptions import ValidationError


def nonblank(value):
    if not value.strip():
        raise ValidationError("This value must contain non-whitespace text.")
