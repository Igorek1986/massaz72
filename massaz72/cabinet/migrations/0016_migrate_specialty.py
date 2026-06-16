from django.db import migrations

# Старое значение CharField -> название специальности.
LEGACY = {
    "masseur": "Массажист",
    "other": "Другое",
}


def forwards(apps, schema_editor):
    Specialty = apps.get_model("cabinet", "Specialty")
    Specialist = apps.get_model("cabinet", "Specialist")

    cache = {}
    for order, (code, name) in enumerate(LEGACY.items()):
        cache[code] = Specialty.objects.get_or_create(
            name=name, defaults={"order": order}
        )[0]

    for spec in Specialist.objects.all():
        target = cache.get(spec.specialty) or cache["masseur"]
        spec.specialty_new = target
        spec.save(update_fields=["specialty_new"])


class Migration(migrations.Migration):

    dependencies = [
        ("cabinet", "0015_specialty_specialist_specialty_new"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
