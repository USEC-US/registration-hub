## Local development

Copy `.env.example` to `.env`, then adjust database settings for your local environment.

Useful commands:

```powershell
uv run python manage.py migrate
uv run python manage.py bootstrap_organizers
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run python manage.py test -v 2
uv run ruff check .
```

API documentation is mounted at `/api/docs/`. It is public while `DEBUG=True` and staff-only while `DEBUG=False`.
