# OTP-via-Telegram Login (Django + Bootstrap + Supabase)

Django app where users log in with username/password, then confirm with a
one-time code delivered to their own linked Telegram chat.

## How it works

1. User signs up (username + password).
2. User links Telegram: clicks a button → opens the bot in Telegram → sends
   `/start <token>` → bot's webhook saves their `chat_id` against their account.
3. On login: password is checked first, then a 6-digit OTP is generated,
   hashed and stored, and the raw code is sent to the user's Telegram chat.
4. User enters the code on the site within 5 minutes (5 attempts max) to
   complete login.

Supabase is used purely as the Postgres database — Django's own auth system
handles sessions and login logic, not Supabase Auth.

## 1. Local setup

```bash
cd otplogin
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in:
- `DJANGO_SECRET_KEY` — generate one: `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- `DATABASE_URL` — from Supabase dashboard → Project Settings → Database → Connection string (URI). Use the **Session pooler** connection string if you're on a serverless host; the direct connection string is fine for local dev / a normal server.
- `TELEGRAM_BOT_TOKEN` — message **@BotFather** on Telegram, run `/newbot`, follow the prompts, copy the token it gives you.
- `TELEGRAM_BOT_USERNAME` — the bot's username from BotFather, without the `@`.
- `SITE_URL` — your public HTTPS URL (see webhook section below for local dev).
- `TELEGRAM_WEBHOOK_SECRET` — any random string, e.g. `python -c "import secrets; print(secrets.token_urlsafe(16))"`.

## 2. Run migrations

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
```

## 3. Webhooks need HTTPS — local dev workaround

Telegram requires the webhook URL to be a public HTTPS address. Your laptop's
`localhost:8000` isn't reachable from Telegram's servers, so for local
development tunnel it with **ngrok**:

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok-free.app` URL it gives you into `SITE_URL` in
`.env`, then register the webhook:

```bash
python manage.py runserver   # in one terminal
python manage.py set_telegram_webhook   # in another, after editing .env
```

In production, set `SITE_URL` to your real domain (e.g.
`https://yourapp.com`) and re-run `set_telegram_webhook` once, after deploy.

## 4. Try it

1. Visit `/signup/`, create an account.
2. You'll land on `/link-telegram/` — tap "Open Telegram to link", hit
   **Start** in the Telegram app.
3. The page auto-redirects to the dashboard once linked.
4. Log out, log back in at `/login/` — you'll be sent to `/verify-otp/` and
   receive a code in Telegram.

## Project layout

```
otplogin/
├── manage.py
├── requirements.txt
├── .env.example
├── otplogin/          # project settings, root urls
└── core/              # the app: models, views, forms, templates, telegram.py
    ├── models.py      # Profile (telegram link), OTP
    ├── telegram.py    # thin Telegram Bot API wrapper
    ├── views.py       # signup/login/otp/link/webhook/dashboard
    ├── forms.py
    ├── urls.py
    ├── admin.py
    ├── management/commands/set_telegram_webhook.py
    └── templates/core/*.html
```

## Security notes already built in

- OTP codes are hashed (SHA-256) before storage — never stored in plain text.
- Constant-time comparison (`secrets.compare_digest`) when checking a code.
- Codes expire after 5 minutes (`OTP_VALID_MINUTES` in settings.py).
- Max 5 verification attempts per code.
- Login error message doesn't reveal whether a username exists.
- Telegram webhook is gated by a secret path segment.
- `.env` holds all secrets — never commit it (already covered by `.gitignore` you should add).

## Before you deploy

- Set `DJANGO_DEBUG=False`.
- Set `DJANGO_ALLOWED_HOSTS` to your real domain.
- Put a real `DJANGO_SECRET_KEY` in production env vars (not in `.env` committed to git).
- Add a rate limit on `/login/` (e.g. django-ratelimit) to slow down brute-force attempts on the password step.
- Consider adding HTTPS-only cookies (`SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`) once you're on HTTPS.
