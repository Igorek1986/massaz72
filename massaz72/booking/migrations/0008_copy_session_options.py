from django.db import migrations


def forwards(apps, schema_editor):
    Old = apps.get_model("tgbot", "BookingSessionOption")
    New = apps.get_model("booking", "BookingSessionOption")
    for opt in Old.objects.all():
        New.objects.get_or_create(
            count=opt.count,
            label=opt.label,
            defaults={"is_active": opt.is_active, "order": opt.order},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("booking", "0007_bookingsessionoption_bookingrequest_sessions"),
        ("tgbot", "0006_bookingnotification"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
