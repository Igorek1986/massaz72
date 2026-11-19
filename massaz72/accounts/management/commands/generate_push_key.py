import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management.base import BaseCommand, CommandError

from accounts.web_push import encode_key


class Command(BaseCommand):
    help = "Создаёт файл окружения с ключом VAPID. Ключ в терминал не выводится."

    def add_arguments(self, parser):
        parser.add_argument("file", type=Path)

    def handle(self, *args, file, **options):
        private_key = ec.generate_private_key(ec.SECP256R1())
        raw_key = private_key.private_numbers().private_value.to_bytes(32, "big")
        try:
            fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as target:
                target.write(f"WEB_PUSH_VAPID_PRIVATE_KEY={encode_key(raw_key)}\n")
        except OSError as exc:
            raise CommandError("Не удалось создать файл. Укажите доступный новый путь.") from exc
        self.stdout.write(self.style.SUCCESS("Файл ключа VAPID создан."))
