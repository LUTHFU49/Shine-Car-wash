import re

from django.core.exceptions import ValidationError

DEFAULT_MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
DEFAULT_ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}

# Kenyan number plates: 3 letters (starting with K), 3 digits, 1 trailing
# letter -- e.g. "KDA 001A". We accept the input with or without a space
# and normalize it to the canonical spaced form.
KENYA_PLATE_PATTERN = re.compile(r'^K[A-Z]{2}\d{3}[A-Z]$')


def validate_image_upload(file, max_size_bytes=DEFAULT_MAX_IMAGE_SIZE_BYTES, allowed_content_types=None):
    """
    Shared image-upload validation: size, declared content-type, and an
    actual Pillow decode so a renamed non-image file (or a corrupt one)
    is rejected rather than silently stored. Returns the file unchanged
    (with its read position reset) so it can be used directly as a
    form field's cleaned value.
    """
    if allowed_content_types is None:
        allowed_content_types = DEFAULT_ALLOWED_IMAGE_TYPES

    if not file:
        return file

    if file.size > max_size_bytes:
        raise ValidationError(f'Image must be smaller than {max_size_bytes // (1024 * 1024)}MB.')

    content_type = getattr(file, 'content_type', None)
    if content_type and content_type not in allowed_content_types:
        raise ValidationError('Only JPEG, PNG, and WEBP images are allowed.')

    try:
        from PIL import Image
        image = Image.open(file)
        image.verify()
    except Exception:
        raise ValidationError('This file is not a valid image.')

    file.seek(0)
    return file


def normalize_kenyan_license_plate(raw_value):
    """
    Strips all whitespace/dashes, uppercases, validates against the
    standard Kenyan plate format, then returns the canonical
    "KDA 001A" spaced form. Raises ValidationError on anything else.
    """
    compact = re.sub(r'[\s\-]', '', raw_value or '').upper()
    if not KENYA_PLATE_PATTERN.match(compact):
        raise ValidationError(
            'Enter a valid Kenyan license plate, e.g. KDA 001A.'
        )
    return f'{compact[:3]} {compact[3:6]}{compact[6]}'
