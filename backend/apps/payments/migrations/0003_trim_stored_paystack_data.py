from django.db import migrations

# Copied rather than imported, so this migration keeps working if the service changes.
KEEP = ("id", "status", "reference", "amount", "currency", "channel", "gateway_response", "paid_at", "fees")


def trim(apps, schema_editor):
    """Drop the payer's IP address, email and card details from payments stored before trimming."""
    Payment = apps.get_model("payments", "Payment")
    for payment in Payment.objects.exclude(raw_response={}).iterator():
        trimmed = {key: payment.raw_response[key] for key in KEEP if key in payment.raw_response}
        if trimmed != payment.raw_response:
            payment.raw_response = trimmed
            payment.save(update_fields=["raw_response"])


class Migration(migrations.Migration):
    dependencies = [("payments", "0002_payment_consultation_alter_payment_order_and_more")]
    operations = [migrations.RunPython(trim, migrations.RunPython.noop)]
