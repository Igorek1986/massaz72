from django.db import migrations

# Поля профиля, переносимые из About в Specialist.
PROFILE_FIELDS = [
    "description", "start_date",
    "telegram_username", "telegram_active",
    "whatsapp_number", "whatsapp_active",
    "max_messanger", "max_messanger_active",
    "is_active", "order",
]


def _norm(value):
    return (value or "").strip().lower()


def forwards(apps, schema_editor):
    About = apps.get_model("main", "About")
    Specialist = apps.get_model("cabinet", "Specialist")
    Certificate = apps.get_model("main", "Certificate")

    abouts = list(About.objects.all())
    specialists = list(Specialist.objects.all())
    used = set()       # id уже занятых специалистов
    mapping = {}       # about_id -> Specialist

    def copy_into(about, spec):
        if about.name:
            spec.name = about.name  # полное имя из профиля
        if about.photo:
            spec.photo = about.photo
        for field in PROFILE_FIELDS:
            setattr(spec, field, getattr(about, field))
        spec.save()

    def match(about):
        """Ищем специалиста, чьё имя — подмножество слов имени профиля (или
        наоборот / подстрока). Так «Марина» матчится к «Пономарева Марина»."""
        a = _norm(about.name)
        a_tokens = set(a.split())
        for spec in specialists:
            if spec.id in used:
                continue
            sn = _norm(spec.name)
            if not sn:
                continue
            s_tokens = set(sn.split())
            if (s_tokens and s_tokens <= a_tokens) or (a_tokens and a_tokens <= s_tokens) \
                    or sn in a or a in sn:
                return spec
        return None

    if len(abouts) == 1 and len(specialists) == 1:
        copy_into(abouts[0], specialists[0])
        mapping[abouts[0].id] = specialists[0]
    else:
        for about in abouts:
            spec = match(about)
            if spec is None:
                # Профиль без пары — становится отдельным специалистом без входа.
                spec = Specialist(name=about.name or "Специалист", user=None)
                copy_into(about, spec)
            else:
                used.add(spec.id)
                copy_into(about, spec)
            mapping[about.id] = spec

    for cert in Certificate.objects.all():
        spec = mapping.get(cert.about_id)
        if spec is not None:
            cert.specialist = spec
            cert.save(update_fields=["specialist"])


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0018_certificate_specialist_alter_certificate_about"),
        ("cabinet", "0014_alter_specialist_options_specialist_description_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
