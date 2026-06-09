from django.db import migrations


def create_specialists_and_assign(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Specialist = apps.get_model('cabinet', 'Specialist')
    WorkSchedule = apps.get_model('cabinet', 'WorkSchedule')
    ScheduleException = apps.get_model('cabinet', 'ScheduleException')
    BlockedSlot = apps.get_model('cabinet', 'BlockedSlot')
    AppointmentSeries = apps.get_model('cabinet', 'AppointmentSeries')
    Appointment = apps.get_model('cabinet', 'Appointment')
    Discount = apps.get_model('cabinet', 'Discount')

    users = list(User.objects.filter(is_staff=False).order_by('pk'))
    if not users:
        users = list(User.objects.order_by('pk'))
    if not users:
        return

    for user in users:
        full_name = f"{user.first_name} {user.last_name}".strip()
        name = full_name or user.username
        Specialist.objects.get_or_create(
            user=user,
            defaults={'name': name, 'specialty': 'masseur'},
        )

    first_specialist = Specialist.objects.order_by('pk').first()
    if first_specialist is None:
        return

    WorkSchedule.objects.filter(specialist__isnull=True).update(specialist=first_specialist)
    ScheduleException.objects.filter(specialist__isnull=True).update(specialist=first_specialist)
    BlockedSlot.objects.filter(specialist__isnull=True).update(specialist=first_specialist)
    AppointmentSeries.objects.filter(specialist__isnull=True).update(specialist=first_specialist)
    Appointment.objects.filter(specialist__isnull=True).update(specialist=first_specialist)
    Discount.objects.filter(specialist__isnull=True).update(specialist=first_specialist)


def reverse_specialists(apps, schema_editor):
    Specialist = apps.get_model('cabinet', 'Specialist')
    Specialist.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cabinet', '0006_add_specialist_fks'),
        ('auth', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_specialists_and_assign, reverse_specialists),
    ]
