import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0019_migrate_about_to_specialist"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="certificate",
            name="about",
        ),
        migrations.AlterField(
            model_name="certificate",
            name="specialist",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="certificates",
                to="cabinet.specialist",
                verbose_name="Специалист",
            ),
        ),
        migrations.DeleteModel(
            name="About",
        ),
    ]
