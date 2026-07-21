from django.utils.text import slugify


def unique_slugify(instance, value, slug_field_name="slug", max_length=220):
    """Generate a unique slug for `instance` by appending -2, -3, ... on collision."""
    model = instance.__class__
    base_slug = slugify(value)[:max_length]
    slug = base_slug
    counter = 2
    qs = model.objects.all()
    if instance.pk:
        qs = qs.exclude(pk=instance.pk)
    while qs.filter(**{slug_field_name: slug}).exists():
        suffix = f"-{counter}"
        slug = f"{base_slug[: max_length - len(suffix)]}{suffix}"
        counter += 1
    return slug
