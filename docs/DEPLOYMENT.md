# ShineHub — Linux Deployment Guide (through Phase 15)

Covers deploying through Phase 11, plus the Phase 15 (enterprise
security) additions appended at the end of this document -- see
"Phase 15 additions" below for what changed. The ASGI/WebSocket steps
below were written proactively back in Phase 1 -- they don't change
shape once a phase actually lands, only app code does -- and Phase 11
(real-time notifications) is exactly the phase that now uses them:
`apps/notifications/consumers.py` is what `shinehub-ws.service` runs,
and `/ws/notifications/` is what the Nginx block below routes to it.
(The ASGI server behind that service is Uvicorn -- see section 7 --
Daphne has been removed from the project.)

## 1. Server prep (Ubuntu 22.04/24.04 example)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-venv python3-dev build-essential \
    default-libmysqlclient-dev pkg-config mysql-server redis-server nginx
```

## 2. App user and code

```bash
sudo adduser --system --group shinehub
sudo mkdir -p /opt/shinehub
sudo chown shinehub:shinehub /opt/shinehub
# copy the project into /opt/shinehub (git clone, scp, or unzip the delivered archive)
```

## 3. Virtualenv + dependencies

```bash
cd /opt/shinehub
sudo -u shinehub python3 -m venv venv
sudo -u shinehub venv/bin/pip install -r requirements.txt
```

## 4. Environment file

Copy `.env.example` to `.env`, fill in production values (`DJANGO_DEBUG=False`,
real MySQL credentials, real Gmail SMTP, real Daraja production/sandbox
keys, `DJANGO_ALLOWED_HOSTS=yourdomain.com`), then lock it down:

```bash
sudo chmod 600 /opt/shinehub/.env
sudo chown shinehub:shinehub /opt/shinehub/.env
```

## 5. Migrate and collect static files

```bash
cd /opt/shinehub
sudo -u shinehub venv/bin/python manage.py migrate
sudo -u shinehub venv/bin/python manage.py createsuperuser
sudo -u shinehub venv/bin/python manage.py collectstatic --noinput
```

## 6. systemd service — Gunicorn (HTTP)

`/etc/systemd/system/shinehub-web.service`:

```ini
[Unit]
Description=ShineHub Gunicorn
After=network.target mysql.service redis-server.service

[Service]
User=shinehub
Group=shinehub
WorkingDirectory=/opt/shinehub
EnvironmentFile=/opt/shinehub/.env
ExecStart=/opt/shinehub/venv/bin/gunicorn shinehub.wsgi:application \
    --workers 3 --bind unix:/opt/shinehub/shinehub.sock
Restart=always

[Install]
WantedBy=multi-user.target
```

## 7. systemd service — Uvicorn (WebSockets, for real-time notifications)

Daphne has been removed from this project. Uvicorn serves the same
`shinehub.asgi:application` in its place -- same role (a dedicated ASGI
process that Nginx routes `/ws/` to, alongside Gunicorn for plain HTTP),
just a different, more actively-maintained ASGI server.

`/etc/systemd/system/shinehub-ws.service`:

```ini
[Unit]
Description=ShineHub Uvicorn (Channels/WebSockets)
After=network.target redis-server.service

[Service]
User=shinehub
Group=shinehub
WorkingDirectory=/opt/shinehub
EnvironmentFile=/opt/shinehub/.env
ExecStart=/opt/shinehub/venv/bin/uvicorn shinehub.asgi:application \
    --host 127.0.0.1 --port 8001
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable both:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now shinehub-web shinehub-ws
```

## 8. Nginx site config

`/etc/nginx/sites-available/shinehub`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location /static/ {
        alias /opt/shinehub/staticfiles/;
    }
    location /media/ {
        alias /opt/shinehub/media/;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location / {
        proxy_pass http://unix:/opt/shinehub/shinehub.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/shinehub /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 9. HTTPS (required for Daraja callbacks in production)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

Update `DARAJA_CALLBACK_URL` in `.env` to the HTTPS domain, then restart:

```bash
sudo systemctl restart shinehub-web shinehub-ws
```

## 10. Scheduled task — booking reminder emails

There's no Celery/background task runner in this stack, so the daily
"remind customers about tomorrow's booking" job is a management command
(`send_booking_reminders`) meant to be triggered by the OS scheduler.

`/etc/systemd/system/shinehub-reminders.service`:

```ini
[Unit]
Description=ShineHub booking reminder emails

[Service]
Type=oneshot
User=shinehub
WorkingDirectory=/opt/shinehub
EnvironmentFile=/opt/shinehub/.env
ExecStart=/opt/shinehub/venv/bin/python manage.py send_booking_reminders
```

`/etc/systemd/system/shinehub-reminders.timer`:

```ini
[Unit]
Description=Run ShineHub booking reminders daily

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now shinehub-reminders.timer
```

A plain cron entry works just as well if you'd rather not use systemd timers:

```
0 8 * * * cd /opt/shinehub && venv/bin/python manage.py send_booking_reminders >> logs/reminders.log 2>&1
```

## 11. Ongoing deploys

```bash
cd /opt/shinehub
sudo -u shinehub git pull            # or copy up the new release
sudo -u shinehub venv/bin/pip install -r requirements.txt
sudo -u shinehub venv/bin/python manage.py migrate
sudo -u shinehub venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart shinehub-web shinehub-ws
```

## 12. Phase 15 additions (enterprise security)

Everything below is new since Phase 11 and needs attention at deploy time.

### New dependencies

```bash
sudo -u shinehub venv/bin/pip install -r requirements.txt
```

Adds `django-ratelimit` and `django-redis` (rate limiting, backed by
the same Redis server Channels already uses — a different logical DB,
so a flush of one never touches the other).

### New required `.env` entries

See `.env.example` for the full, current list with defaults. The ones
that matter most at go-live:

- `REDIS_CACHE_DB` — logical Redis DB for the rate-limit cache (default `1`; Channels already uses its own, separate from this).
- `RATELIMIT_ENABLE` and the per-endpoint `RATELIMIT_*` thresholds — sane defaults ship in `.env.example`; retune under real traffic without a redeploy.
- `SESSION_INACTIVITY_TIMEOUT_MINUTES` — sliding idle-session timeout, independent of the 7-day "remember me" cookie ceiling.
- `PASSWORD_HISTORY_COUNT` — how many previous passwords are blocked from reuse.
- `MPESA_CALLBACK_ALLOWED_IPS` — **get this from Safaricom at go-live**, not before. Leave empty for sandbox testing; a wrong hardcoded list would silently break real payments, so this intentionally has no baked-in default.

### New migrations

```bash
sudo -u shinehub venv/bin/python manage.py migrate
```

Adds `UserSession`, `PasswordHistory`, and `User.must_change_password` (all in the `accounts` app).

### Redis is no longer optional for correctness

Rate limiting is backed by Redis (`REDIS_CACHE_DB`). If Redis is down,
rate limiting fails open per Django's cache-backend behavior rather
than blocking requests — but limits then only apply per-process, not
across Gunicorn workers. Keep `USE_INMEMORY_CHANNEL_LAYER=False` and
Redis running in production, exactly as already required for Channels.

## 13. Deployment checklist

Run through this before every production deploy, not just the first one.

- [ ] `.env` has a real `DJANGO_SECRET_KEY` (long, random, not the `django-insecure-` default) and `DJANGO_DEBUG=False`
- [ ] `DJANGO_ALLOWED_HOSTS` set to the real domain(s), not a wildcard
- [ ] `DARAJA_ENV`, `DARAJA_CONSUMER_KEY/SECRET`, `DARAJA_SHORTCODE`, `DARAJA_PASSKEY`, `DARAJA_CALLBACK_URL` all point at production Daraja, not sandbox
- [ ] `MPESA_CALLBACK_ALLOWED_IPS` populated with Safaricom's current published range
- [ ] Gmail SMTP credentials are a real App Password, not a personal account password
- [ ] Redis and MySQL are both running and reachable before starting the app services
- [ ] `venv/bin/pip install -r requirements.txt` run inside the target venv
- [ ] `manage.py migrate` run and exits clean
- [ ] `manage.py collectstatic --noinput` run and Nginx's `/static/` alias points at the same `staticfiles` directory
- [ ] `manage.py check --deploy` run with `DJANGO_DEBUG=False` and returns no issues
- [ ] `shinehub-web` (Gunicorn) and `shinehub-ws` (Uvicorn) both restarted, and `systemctl status` shows both active
- [ ] Nginx config test passes (`nginx -t`) and is reloaded
- [ ] TLS certificate is valid and auto-renewal (certbot timer) is active

## 14. Post-deployment verification checklist

Run through this immediately after every deploy, before considering it done.

- [ ] Landing page loads over HTTPS, and HTTP redirects to HTTPS
- [ ] Response headers include `Content-Security-Policy`, `Permissions-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security`
- [ ] Login works for at least one account in each role (Super Admin, Manager, Cashier, Employee, Customer)
- [ ] A deliberately wrong password 11 times in a row from the same session gets a 429, not a 500
- [ ] Django Admin is reachable only to staff accounts, and the Audit Log / Active Sessions lists are visible there
- [ ] A real booking can be created, confirmed, and paid (cash) end-to-end, and its invoice reflects the payment
- [ ] A real M-Pesa STK push reaches a test phone and completes (or is deliberately cancelled) and the callback updates the payment correctly, exactly once
- [ ] Booking confirmation / welcome / password-reset emails actually arrive (check spam folder too) with correct branding
- [ ] WebSocket notifications appear in the topbar without a page refresh
- [ ] CSV and Excel exports for at least one module open cleanly in Excel/LibreOffice with no formula warnings on cells containing customer-entered text
- [ ] `logs/shinehub.log` is being written to and rotating, not silently missing
- [ ] `systemctl status shinehub-web shinehub-ws shinehub-reminders.timer` all show active/enabled
