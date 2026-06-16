from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cabinet", "0016_migrate_specialty"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="specialist",
            name="specialty",
        ),
        migrations.RenameField(
            model_name="specialist",
            old_name="specialty_new",
            new_name="specialty",
        ),
    ]
