from django.db import migrations

from apps.products.concern_intros import CONCERN_INTROS


def fill_blank_intros(apps, schema_editor):
    """Gives existing concerns starter text; never overwrites an intro someone has written."""
    Symptom = apps.get_model("products", "Symptom")
    for symptom in Symptom.objects.filter(intro="", name__in=CONCERN_INTROS):
        symptom.intro = CONCERN_INTROS[symptom.name]
        symptom.save(update_fields=["intro"])


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0004_symptom_intro"),
    ]

    operations = [
        migrations.RunPython(fill_blank_intros, migrations.RunPython.noop),
    ]
