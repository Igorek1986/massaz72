import secrets

from django.db import migrations


def forwards(apps, schema_editor):
    BookingRequest = apps.get_model("booking", "BookingRequest")
    for booking in BookingRequest.objects.filter(link_token=""):
        booking.link_token = secrets.token_urlsafe(16)
        booking.save(update_fields=["link_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0002_bookingrequest_link_token_bookingrequest_messenger_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
