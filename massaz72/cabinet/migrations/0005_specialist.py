import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cabinet', '0004_workschedule_break_between_minutes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Specialist',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('specialty', models.CharField(
                    choices=[('masseur', 'Массажист'), ('other', 'Другое')],
                    default='masseur', max_length=30, verbose_name='Специальность',
                )),
                ('name', models.CharField(max_length=100, verbose_name='Имя')),
                ('photo', models.ImageField(blank=True, null=True, upload_to='specialists/', verbose_name='Фото')),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='specialist',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Пользователь',
                )),
            ],
            options={
                'verbose_name': 'Специалист',
                'verbose_name_plural': 'Специалисты',
            },
        ),
    ]
