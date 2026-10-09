from django.db import migrations, models


def whatsapp_to_email(apps, schema_editor):
    Consultation = apps.get_model("consultations", "Consultation")
    Consultation.objects.filter(mode="whatsapp").update(mode="email")


class Migration(migrations.Migration):
    dependencies = [("consultations", "0001_initial")]

    operations = [
        migrations.RenameField("expert", "offers_whatsapp", "offers_email"),
        migrations.AlterField(
            model_name="consultation",
            name="mode",
            field=models.CharField(
                choices=[("email", "Email consultation"), ("phone", "Phone call"), ("video", "Video call")],
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="consultation",
            name="phone_number",
            field=models.CharField(blank=True, help_text="Needed for phone sessions.", max_length=20),
        ),
        migrations.RunPython(whatsapp_to_email, migrations.RunPython.noop),
    ]
