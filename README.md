# Массажный сайт на Django с Docker

Этот проект представляет собой сайт, разработанный на Django с использованием базы данных PostgreSQL. Сайт позволяет пользователям ознакомиться с услугами массажа, их стоимостью, продолжительностью и описанием. Услуги разделены на две категории: детские массажи и взрослые массажи. Новые виды услуг могут быть добавлены через админку Django. Проект запускается через Docker Compose с использованием Gunicorn для production-режима.

Репозиторий проекта: [https://github.com/Igorek1986/massaz72](https://github.com/Igorek1986/massaz72)  
Для связи: [9129910001@mail.ru](mailto:9129910001@mail.ru)

---

## Основные функции

- **Просмотр услуг массажа**: На главной странице отображаются услуги массажа, разделенные на две категории: детские и взрослые. Сначала выводятся детские массажи, затем взрослые.
- **Адаптивная верстка**: Сайт адаптирован для просмотра на различных устройствах, включая мобильные телефоны, планшеты и десктопы.
- **Администрирование**: Новые виды массажей могут быть добавлены через админку Django. Также можно управлять порядком отображения услуг, их описанием, стоимостью и продолжительностью.
- **Управление cookie**: Реализовано уведомление о использовании cookie с возможностью принятия и просмотра подробной информации. Настройки сохраняются в localStorage браузера.

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


### 3. Активация виртуального окружения poetry
```bash
eval $(poetry env activate)
```

### 4. Компиляция SASS/SCSS файлов
```bash
cd massaz72
python manage.py compilescss
```

### 5. Сбор статических файлов
```
python manage.py collectstatic --noinput
```

### 6. Применение миграций
После запуска контейнеров примените миграции:
```bash
python manage.py migrate
```

### 7. Создание суперпользователя
Для доступа к админке создайте суперпользователя:
```bash
python manage.py createsuperuser
```

### 8. Запуск проекта через Docker Compose
```bash
docker-compose up -d --build
```
Проект будет доступен по адресу: [http://localhost:8000](http://localhost:8000).


---

## Модели

### Massage
Модель `Massage` предназначена для хранения информации о различных типах массажа. Она включает в себя следующие поля:

- **Название массажа**: Название конкретного массажа.
- **Стоимость**: Цена массажа, представляемая в виде десятичного числа.
- **Описание**: Текстовое поле для описания массажа (может быть пустым).
- **Минимальная продолжительность**: Минимальная продолжительность массажа в минутах.
- **Максимальная продолжительность**: Максимальная продолжительность массажа в минутах.
- **Тип массажа**: Выбор между взрослыми и детскими массажами (по умолчанию — детский).
- **Очередность**: Числовое поле, определяющее порядок отображения массажей.
- **Категория**: Связь с моделью `Category`, указывающая на категорию массажа (может быть пустой).
- **Изображение**: Загружаемое изображение, связанное с массажем (может быть пустым).
- **Дата создания**: Дата и время создания записи.
- **Дата последнего обновления**: Дата и время последнего обновления записи.

### About
Модель `About` предназначена для хранения информации о массажисте. Она включает в себя следующие поля:

- **Имя массажиста**: Полное имя массажиста.
- **Фото массажиста**: Загружаемое изображение профессионального фото массажиста.
- **Описание**: Текстовое поле для описания опыта, специализации и подхода к работе массажиста.
- **Дата начала работы**: Дата, с которой массажист начал свою деятельность.
- **Активный массажист**: Булевое поле, указывающее, активно ли массажист принимает клиентов.
- **Порядок сортировки**: Числовое поле, определяющее порядок отображения массажистов на сайте (меньшее число — выше в списке).
- **Дата создания**: Дата и время создания записи.
- **Дата обновления**: Дата и время последнего обновления записи.

### Certificate
Модель `Certificate` используется для хранения сертификатов массажиста. Она включает в себя следующие поля:

- **О массажисте**: Связь с моделью `About`, указывающая на массажиста, которому принадлежит сертификат.
- **Название**: Название сертификата.
- **Изображение сертификата**: Загружаемое изображение сертификата.
- **Дата получения**: Дата, когда сертификат был получен.
- **Порядок отображения**: Числовое поле, определяющее порядок отображения сертификатов.
- **Дата создания**: Дата и время создания записи.
- **В архиве**: Булевое поле, указывающее, находится ли сертификат в архиве.

### SiteSettings
Модель `SiteSettings` предназначена для хранения основных настроек сайта. Она включает в себя следующие поля:

- **Head Title**: Заголовок для мета-тегов страницы
- **Главный заголовок**: Основной заголовок сайта
- **Главный подзаголовок**: Подзаголовок на главной странице
- **Meta description**: Описание страницы сайта
- **Meta keywords**: Ключевые слова для поисковых систем
- **Детский массаж**: Заголовок раздела детского массажа
- **Массаж**: Заголовок раздела взрослого массажа
- **Обо мне**: Заголовок раздела о массажисте
- **Контакты**: Заголовок раздела контактов
- **Год начала практики массажа**: Год начала работы массажистом
- **Фоновое изображение**: Изображение для фона секции заголовка и подзаголовка

## Добавленная функциональность
- Возможность загружать фотографии массажистов и их сертификаты.
- Добавление описания о массажисте, даты начала работы и отметка "активного" массажиста.
- Сортировка массажистов по порядку отображения.


---

## Планируемые доработки

- **Отзывы**: Добавление функционала для оставления отзывов о массажах.
- **Календарь**: Отображение свободного времени для записи на массаж.
- **Телеграм бот**: Разработка бота для записи на массаж, уведомлений и подтверждения записей.
- **Уведомления**: Уведомление клиентов за сутки до начала массажа.
- **Онлайн**: Онлайн запись на массаж. 

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