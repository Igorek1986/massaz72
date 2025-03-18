# Массажный сайт на Django с Docker

Этот проект представляет собой сайт, разработанный на Django с использованием базы данных PostgreSQL. Сайт позволяет пользователям ознакомиться с услугами массажа, их стоимостью, продолжительностью и описанием. Услуги разделены на две категории: детские массажи и взрослые массажи. Новые виды услуг могут быть добавлены через админку Django. Проект запускается через Docker Compose с использованием Gunicorn для production-режима.

Репозиторий проекта: [https://github.com/Igorek1986/massaz72](https://github.com/Igorek1986/massaz72)  
Для связи: [9129910001@mail.ru](mailto:9129910001@mail.ru)

---

## Основные функции

- **Просмотр услуг массажа**: На главной странице отображаются услуги массажа, разделенные на две категории: детские и взрослые. Сначала выводятся детские массажи, затем взрослые.
- **Адаптивная верстка**: Сайт адаптирован для просмотра на различных устройствах, включая мобильные телефоны, планшеты и десктопы.
- **Администрирование**: Новые виды массажей могут быть добавлены через админку Django. Также можно управлять порядком отображения услуг, их описанием, стоимостью и продолжительностью.

---

## Установка и запуск через Docker Compose

### 1. Клонирование репозитория
```bash
git clone https://github.com/Igorek1986/massaz72.git
cd massaz72
```

### 2. Настройка переменных окружения
- Скопируйте файл `.env.template` в `.env`:
  ```bash
  cp .env.template .env
  ```
- Отредактируйте файл `.env`, указав необходимые параметры для подключения к базе данных и другие настройки.

### 3. Запуск проекта через Docker Compose
```bash
docker-compose up --build
```
Проект будет доступен по адресу: [http://localhost:8000](http://localhost:8000).

### 4. Применение миграций
После запуска контейнеров примените миграции:
```bash
docker-compose exec web python manage.py migrate
```

### 5. Создание суперпользователя
Для доступа к админке создайте суперпользователя:
```bash
docker-compose exec web python manage.py createsuperuser
```

### 6. Сбор статических файлов
Если требуется, соберите статические файлы:
```bash
docker-compose exec web python manage.py collectstatic --noinput
```

---

## Модель Massage

Основная модель, используемая в проекте, выглядит следующим образом:

```python
class Massage(models.Model):
    ADULT = 'adult'
    CHILD = 'child'
    MASSAGE_TYPE_CHOICES = [
        (ADULT, 'Взрослый'),
        (CHILD, 'Детский'),
    ]

    name = models.CharField(max_length=255, verbose_name="Название массажа")
    price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Стоимость"
    )
    description = models.TextField(verbose_name="Описание", blank=True, null=True)
    duration_min = models.PositiveIntegerField(verbose_name="Минимальная продолжительность (в минутах)")
    duration_max = models.PositiveIntegerField(verbose_name="Максимальная продолжительность (в минутах)")
    massage_type = models.CharField(
        max_length=5,
        choices=MASSAGE_TYPE_CHOICES,
        default=CHILD,
        verbose_name="Тип массажа"
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Очередность")
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        verbose_name="Категория",
        blank=True,
        null=True,
    )
    image = models.ImageField(
        upload_to="massage_images/", verbose_name="Изображение", blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name="Дата последнего обновления"
    )
```

---

## Планируемые доработки

- **Отзывы**: Добавление функционала для оставления отзывов о массажах.
- **О себе**: Раздел с информацией о массажисте.
- **Календарь**: Отображение свободного времени для записи на массаж.
- **Телеграм бот**: Разработка бота для записи на массаж, уведомлений и подтверждения записей.
- **Уведомления**: Уведомление клиентов за сутки до начала массажа.
- **WhatsApp бот**: Интеграция с WhatsApp для записи и общения.

---

## Структура проекта

- **Dockerfile**: Файл для сборки Docker-образа приложения.
- **docker-compose.yml**: Конфигурация для запуска проекта через Docker Compose.
- **.env.template**: Шаблон для создания файла с переменными окружения.
- **pyproject.toml**: Файл конфигурации Poetry для управления зависимостями Python.
- **manage.py**: Скрипт для управления Django-проектом.
- **massaz72/**: Основная директория Django-проекта.
- **staticfiles/**: Статические файлы (CSS, JS, изображения), собранные командой `collectstatic`.
- **templates/**: HTML-шаблоны для отображения страниц.

---

## Зависимости

Зависимости проекта управляются через Poetry. Установите Poetry, если он ещё не установлен:

```bash
pip install poetry
```

Установите зависимости:

```bash
poetry install
```

---

## Использование Gunicorn

Для production-режима используется **Gunicorn**. Он настроен в `Dockerfile` и `docker-compose.yml` для запуска Django-приложения.

---

## Лицензия

Этот проект распространяется под лицензией MIT. Подробности см. в файле [LICENSE](LICENSE).

---

Если у вас есть вопросы или предложения, пожалуйста, создайте issue в репозитории или свяжитесь со мной через [9129910001@mail.ru](mailto:9129910001@mail.ru).


Если вам нужно что-то ещё, дайте знать! 😊