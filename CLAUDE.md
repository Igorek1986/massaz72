# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Django website for a massage therapist business (Russian-language, single therapist). Located at `massaz72/` subdirectory within the repo root.

**Key rule from .cursorrules:** When writing code, be 100% sure you are not breaking existing functionality.

## Environments

- **Production:** `massaz72.ru`
- **Testing / staging:** `beta.massaz72.ru`

## Git Conventions & Workflow

- Do NOT add `Co-Authored-By` or any AI/Claude authorship trailer to commit messages.
- Development is done on the **`dev`** branch. Commit and push feature work to `dev`.
- **Do NOT merge into `master` automatically.** Merge `dev` → `master` ONLY when a feature is finished AND the user explicitly asks for a release. `master` = production releases.

## Development Commands

All commands run from `massaz72/` directory:

```bash
# Run dev server
python manage.py runserver

# Run all tests
python manage.py test

# Run tests for a specific app
python manage.py test main
python manage.py test services

# Run a single test class
python manage.py test main.tests.test_models.AboutModelTest

# Compile SCSS
python manage.py compilescss

# Collect static files
python manage.py collectstatic --noinput

# Apply migrations
python manage.py migrate

# Run the Telegram bot in polling mode (token/admins configured in admin)
python manage.py runbot
# Register / remove the webhook (webhook mode)
python manage.py set_webhook
python manage.py delete_webhook
```

SCSS linting (from repo root):
```bash
npm install
npx stylelint "**/*.scss"
```

Docker:
```bash
docker-compose up -d --build
# Migrations run automatically on container start (entrypoint.sh calls migrate --noinput).
# No need to run migrate manually after build.

# Telegram bot in polling mode runs as a separate service behind the "polling" profile.
# Not needed in webhook mode (the app container serves the webhook URL).
docker compose --profile polling up -d
```

## Architecture

### Apps

**`main`** — Site-wide content and therapist info
- `SiteSettings` — singleton model for page titles, meta tags, contact info (Telegram, WhatsApp, MAX messenger), career start year
- `About` — therapist profile (name, photo, description, start_date); computed `experience` and `experience_text` properties with Russian grammar
- `Certificate` — therapist certifications with FK to About; auto-deletes image file on deletion via pre_delete signal

**`services`** — Massage service catalog
- `Massage` — service listings with name, price, duration_min/max, location, massage_type (ADULT | CHILD), slug, image, is_archived
- Slug-based detail URLs; XML sitemap generated via `sitemaps.py`

**`tgbot`** — Telegram bot (pyTelegramBotAPI, synchronous). Clients message the bot; messages are forwarded to admins, who reply via Telegram's Reply to answer the client.
- `BotSettings` — singleton: token, mode (polling | webhook), public_url, auto-generated `secret_path`/`secret_token`, welcome/prompt texts. Configured in admin.
- `BotAdmin` — admin Telegram IDs that receive client messages (managed in admin).
- `TelegramUser` / `DialogMessage` / `AdminForward` — clients, conversation history, and the `admin_message_id → client` mapping used to route admin replies.
- `tgbot/bot.py` builds the bot and registers handlers (shared by polling and webhook). Buttons: «💰 Услуги и цены» (lists non-archived `Massage` with prices), «📝 Записаться».
- Webhook: `views.webhook` at `tg/webhook/<secret_path>/`, validates `secret_path` + `X-Telegram-Bot-Api-Secret-Token`. Polling: `manage.py runbot`.
- Set/remove webhook via admin actions on BotSettings or `manage.py set_webhook` / `delete_webhook`.

### URL Structure

```
/                         → homepage (child + adult massages, about, certificates)
/cookies/                 → cookie policy
/services/<slug>/         → massage detail page
/sitemap.xml              → SEO sitemap
/admin/                   → Django admin
```

### Context Processors

Two custom context processors inject data into all templates:
- `main.context_processors.common_context` — therapist (About), contact details (Telegram, WhatsApp, MAX), current year, messaging preference
- `main.context_processors.site_settings` — SiteSettings instance

### File Handling

`massaz72/utils.py` has `get_file_path()` which auto-transliterates Russian filenames to Latin slugs and organizes uploads by model type. File size validated against `MAX_UPLOAD_SIZE_MB` env var (default 5MB).

### Settings / Environment

Copy `.env.template` to `.env`. Key variables:
- `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` (PostgreSQL)
- `TELEGRAM_USERNAME`, `WHATSAPP_NUMBER`, `MAX_MESSANGER` — contact info shown on site
- `MAX_UPLOAD_SIZE_MB`, `LOGFILE_NAME`, `LOGFILE_SIZE`, `LOGFILE_COUNT`

### Stack

- Python 3.13, Django 5.1+, PostgreSQL (psycopg2)
- SASS/SCSS via django-sass-processor + libsass
- django-stubs for type hints
- Gunicorn for production (Docker)
- Language/locale: Russian (ru-ru)

## Styling

**Always write styles in SCSS**, never plain CSS. Place new component styles in `static/css/components/` or in the app's own `static/<app>/css/` directory as `.scss` files. Reference SCSS files in templates via `{% sass_src %}` (triggers compilation) and load the compiled `.css` via `{% static %}`.
