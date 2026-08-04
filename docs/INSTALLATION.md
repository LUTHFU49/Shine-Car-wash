# ShineHub — Installation Guide

## 1. Prerequisites

- Python 3.11+ (project built and tested against 3.12)
- MySQL 8.0+ (or MariaDB 10.6+)
- Redis (for Django Channels / real-time notifications)
- A Gmail account with an **App Password** (not your normal password)
- A Safaricom Daraja developer account (free, sandbox) for M-Pesa

## 2. Clone and set up the virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

If `pip install mysqlclient` fails with a build error, install the system
dev headers first:

```bash
# Ubuntu / Debian
sudo apt update
sudo apt install -y default-libmysqlclient-dev pkg-config build-essential

# macOS (Homebrew)
brew install mysql-client pkg-config
export PKG_CONFIG_PATH="/opt/homebrew/opt/mysql-client/lib/pkgconfig"

# Windows
# Easiest path: install via a precompiled wheel, e.g.
#   pip install mysqlclient --only-binary :all:
# or switch to PyMySQL (pure Python, no compiler needed) — see the note
# at the bottom of this file.
```

## 3. MySQL database setup

```sql
CREATE DATABASE shinehub_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'shinehub_user'@'localhost' IDENTIFIED BY 'a-strong-password-here';
GRANT ALL PRIVILEGES ON shinehub_db.* TO 'shinehub_user'@'localhost';
FLUSH PRIVILEGES;
```

## 4. Environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in:

- `DJANGO_SECRET_KEY` — generate one with:
  `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` — from step 3
- Leave `USE_SQLITE=False` for real MySQL use. Set it to `True` only if you
  want to try the project immediately without a MySQL server (fine for a
  quick look, not for the real system — MySQL is required per the brief).

## 5. Gmail SMTP setup

1. Turn on 2-Step Verification on the Google account you'll send from:
   `https://myaccount.google.com/security`
2. Create an App Password: `https://myaccount.google.com/apppasswords`
   (choose "Mail" as the app). Google gives you a 16-character password.
3. In `.env`:
   ```
   EMAIL_HOST_USER=your-business-email@gmail.com
   EMAIL_HOST_PASSWORD=the16charapppassword
   DEFAULT_FROM_EMAIL=ShineHub <your-business-email@gmail.com>
   ```

While `DJANGO_DEBUG=True` and no SMTP credentials are set, emails print to
the console instead of failing — useful for early development.

## 6. Safaricom Daraja sandbox setup

1. Create an account at `https://developer.safaricom.co.ke`
2. Create a new sandbox app → copy the **Consumer Key** and **Consumer
   Secret** into `.env`
3. The sandbox `DARAJA_SHORTCODE` (174379) and its test `DARAJA_PASSKEY` are
   published on the Daraja docs under "Lipa Na M-Pesa Online" — copy the
   passkey shown there into `.env`
4. `DARAJA_CALLBACK_URL` must be a **publicly reachable** HTTPS URL (Daraja
   cannot call `127.0.0.1`). For local development, use a tunnel, e.g.:
   ```bash
   ngrok http 8000
   ```
   then set `DARAJA_CALLBACK_URL` to the ngrok HTTPS URL + your callback
   path (this path is created in the Payments phase).

## 7. Redis (for real-time notifications)

```bash
# Ubuntu/Debian
sudo apt install -y redis-server
sudo systemctl enable --now redis-server

# macOS
brew install redis
brew services start redis
```

Defaults in `.env` (`REDIS_HOST=127.0.0.1`, `REDIS_PORT=6379`) work
out of the box with a local install.

## 8. Migrate and run

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py runserver
```

Visit `http://127.0.0.1:8000/`. Django admin is at `/admin/`.

## Optional: using PyMySQL instead of mysqlclient

If `mysqlclient` gives you build trouble on your machine:

```bash
pip install pymysql
```

Then at the very top of `shinehub/settings.py`, add:

```python
import pymysql
pymysql.install_as_MySQLdb()
```

Everything else in `DATABASES` stays the same.
