import os
import uuid
from typing import Optional

from django.core.exceptions import ValidationError
from django.utils.text import slugify


def _slugify_ru(text: str) -> str:
    """
    Преобразует русский текст в slug с транслитерацией.
    Для внутреннего использования.
    """
    transliteration = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '',
        'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
    }
    
    # Переводим в нижний регистр и транслитерируем
    text = text.lower()
    result = ''
    for char in text:
        result += transliteration.get(char, char)
    
    # Используем стандартный slugify для остальных преобразований
    return slugify(result)


def _get_base_filename(instance) -> tuple[str, str]:
    """
    Возвращает базовое имя файла и папку для сохранения в зависимости от типа модели.
    Для внутреннего использования.
    
    Returns:
        tuple: (base_name, folder)
    """
    model_name = str(instance._meta.model_name)
    
    if model_name == 'massage':
        base_name = _slugify_ru(instance.name)  # Название массажа
        folder = os.path.join('massages', 'children' if instance.massage_type == 'child' else 'adults')
    elif model_name == 'certificate':
        # Получаем имя массажиста из связанной модели About
        masseur_name = _slugify_ru(instance.about.name) if instance.about else "massazhist"
        base_name = f"sertifikat-{masseur_name}-{_slugify_ru(instance.title)}"  # Добавляем имя массажиста
        folder = 'certificates'
    elif model_name == 'about':
        base_name = _slugify_ru(instance.name)  # Имя массажиста
        folder = 'about'
    elif model_name == 'sitesettings':
        base_name = 'sitesettings'
        folder = 'sitesettings'
    else:
        base_name = model_name
        folder = model_name
        
    return base_name, folder


def get_file_path(instance, filename):
    """
    Генерирует путь для файла используя название и короткий уникальный идентификатор.
    Для массажей создает подпапки adults/children.
    """
    # Получаем расширение файла
    ext = filename.split('.')[-1]

    # Получаем базовое имя файла и папку
    base_name, folder = _get_base_filename(instance)

    # Формируем имя файла с коротким идентификатором
    filename = f"{base_name}_{uuid.uuid4().hex[:4]}.{ext}"
    
    return os.path.join(folder, filename)


def delete_old_file(instance, field_name):
    """
    Удаляет старый файл при обновлении
    """
    try:
        old_instance = instance.__class__.objects.get(pk=instance.pk)
        old_file = getattr(old_instance, field_name)
        new_file = getattr(instance, field_name)
        if old_file and old_file != new_file:
            old_file.delete(save=False)
    except instance.__class__.DoesNotExist:
        pass


def validate_file_size(value):
    filesize = value.size
    max_size_mb = int(os.getenv('MAX_UPLOAD_SIZE_MB', 5))  # По умолчанию 5MB
    max_size_bytes = max_size_mb * 1024 * 1024  # Конвертируем MB в байты
    if filesize > max_size_bytes:
        raise ValidationError(f'Максимальный размер файла {max_size_mb}MB')
