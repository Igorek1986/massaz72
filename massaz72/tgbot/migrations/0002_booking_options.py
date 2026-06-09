from django.db import migrations, models


def add_initial_data(apps, schema_editor):
    BookingSessionOption = apps.get_model("tgbot", "BookingSessionOption")
    BookingTimeSlot = apps.get_model("tgbot", "BookingTimeSlot")

    BookingSessionOption.objects.bulk_create([
        BookingSessionOption(count=7,  label="7 сеансов",  is_active=True, order=0),
        BookingSessionOption(count=10, label="10 сеансов", is_active=True, order=1),
    ])

    BookingTimeSlot.objects.bulk_create([
        BookingTimeSlot(label="9:00–12:00",  is_active=True, order=0),
        BookingTimeSlot(label="12:00–18:00", is_active=True, order=1),
        BookingTimeSlot(label="18:00–20:00", is_active=True, order=2),
    ])


class Migration(migrations.Migration):

    dependencies = [
        ("tgbot", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BookingSessionOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("count", models.PositiveIntegerField(verbose_name="Количество сеансов")),
                ("label", models.CharField(blank=True, default="", help_text="Если пусто — отображается «N сеансов».", max_length=50, verbose_name="Метка кнопки")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активна")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Порядок")),
            ],
            options={
                "verbose_name": "Вариант кол-ва сеансов",
                "verbose_name_plural": "Варианты кол-ва сеансов",
                "ordering": ["order", "count"],
            },
        ),
        migrations.CreateModel(
            name="BookingTimeSlot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=50, verbose_name="Время (напр. «9:00–12:00»)")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Порядок")),
            ],
            options={
                "verbose_name": "Временной слот",
                "verbose_name_plural": "Временные слоты",
                "ordering": ["order"],
            },
        ),
        migrations.RunPython(add_initial_data, migrations.RunPython.noop),
    ]
