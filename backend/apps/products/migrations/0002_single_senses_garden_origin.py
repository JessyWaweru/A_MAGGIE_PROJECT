from django.db import migrations

NAME = "Senses Garden"


def use_senses_garden(apps, schema_editor):
    """Every herb is grown in one garden, so point all products at it and drop the other origins."""
    PlantOrigin = apps.get_model("products", "PlantOrigin")
    Product = apps.get_model("products", "Product")
    garden, _ = PlantOrigin.objects.get_or_create(
        name=NAME,
        defaults={
            "country": "Kenya",
            "description": "Our own home garden, where every herb is grown and tended.",
        },
    )
    Product.objects.exclude(plant_origin=garden).update(plant_origin=garden)
    PlantOrigin.objects.exclude(pk=garden.pk).delete()


class Migration(migrations.Migration):
    dependencies = [("products", "0001_initial")]

    operations = [migrations.RunPython(use_senses_garden, migrations.RunPython.noop)]
