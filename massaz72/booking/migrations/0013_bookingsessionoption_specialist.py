from django.db import migrations, models
import django.db.models.deletion


def assign_specialists(apps, schema_editor):
    """Переносим глобальные варианты сеансов на специалистов без потери ссылок:
    оригинал привязываем к первому специалисту, остальным создаём копии."""
    Option = apps.get_model("booking", "BookingSessionOption")
    Specialist = apps.get_model("cabinet", "Specialist")

    specialists = list(Specialist.objects.all())
    if not specialists:
        Option.objects.all().delete()
        return

    first = specialists[0]
    for opt in Option.objects.filter(specialist__isnull=True):
        for sp in specialists[1:]:
            Option.objects.create(
                specialist=sp, count=opt.count, label=opt.label,
                is_active=opt.is_active, order=opt.order,
            )
        opt.specialist = first
        opt.save(update_fields=["specialist"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    # Неатомарно: на PostgreSQL нельзя ALTER после вставки данных (RunPython)
    # в одной транзакции («pending trigger events»).
    atomic = False

    dependencies = [
        ("cabinet", "0022_workschedule_lead_time_minutes"),
        ("booking", "0012_alter_bookingrequest_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookingsessionoption",
            name="specialist",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="session_options",
                to="cabinet.specialist",
                verbose_name="Специалист",
            ),
        ),
        migrations.RunPython(assign_specialists, noop),
        migrations.AlterField(
            model_name="bookingsessionoption",
            name="specialist",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="session_options",
                to="cabinet.specialist",
                verbose_name="Специалист",
            ),
        ),
        migrations.AlterModelOptions(
            name="bookingsessionoption",
            options={
                "ordering": ["specialist", "order", "count"],
                "verbose_name": "Вариант кол-ва сеансов",
                "verbose_name_plural": "Варианты кол-ва сеансов",
            },
        ),
    ]
