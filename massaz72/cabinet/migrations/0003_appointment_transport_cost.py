from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cabinet', '0002_discount'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='transport_cost',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Транспортные расходы'),
        ),
    ]
