# Generated by Django 5.1.6 on 2025-03-29 10:47

import massaz72.utils
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0007_massage_is_archived'),
    ]

    operations = [
        migrations.AlterField(
            model_name='category',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to=massaz72.utils.get_file_path, validators=[massaz72.utils.validate_file_size], verbose_name='Изображение категории'),
        ),
        migrations.AlterField(
            model_name='massage',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to=massaz72.utils.get_file_path, validators=[massaz72.utils.validate_file_size], verbose_name='Изображение'),
        ),
    ]
