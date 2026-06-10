from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cabinet", "0008_make_specialist_required"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="discount",
            name="specialist",
        ),
        migrations.AddField(
            model_name="specialist",
            name="can_manage_prices",
            field=models.BooleanField(
                default=True,
                help_text="Разрешить изменять цены и скидки",
                verbose_name="Управление ценами",
            ),
        ),
    ]
