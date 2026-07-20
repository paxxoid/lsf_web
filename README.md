# Loot and Some Fun — Django starter

This is a local-development starter for the guild-site concept. It includes:

- Homepage matching the supplied dark blue/gold EverQuest concept
- Guild roster
- Raid calendar
- Loot history
- Guild news
- Screenshot uploads
- Membership applications
- Django Admin management
- Scoped API keys and a starter CRUD API
- VS Code debugger configuration

## Use this as a new project

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py makemigrations guild
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo_data
python manage.py runserver
```

Open:

- Website: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/
- API docs: http://127.0.0.1:8000/api/docs
- API health: http://127.0.0.1:8000/api/health

## Copy into the project you already created

Your existing project uses `config` and `guild`, so you can copy these folders/files over it after backing up any work:

- `config/`
- `guild/`
- `static/`
- `templates/`
- `.vscode/launch.json`
- `requirements.txt`

Then run:

```powershell
python -m pip install -r requirements.txt
python manage.py makemigrations guild
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```

## Create an API key

```powershell
python manage.py create_api_key "Discord Bot" `
  --permission members:read `
  --permission raids:read `
  --permission loot:read `
  --permission loot:create
```

The command shows the raw key once. Send it as:

```http
X-API-Key: lasf_your_generated_key
```

Available starter permissions:

- `members:read`
- `raids:read`
- `loot:read`
- `loot:create`
- `loot:update`
- `loot:delete`
- `admin`

## Example API call

```powershell
curl.exe -H "X-API-Key: YOUR_KEY" http://127.0.0.1:8000/api/v1/loot
```

## Next recommended steps

1. Replace demo member names and raid information through Django Admin.
2. Add your Discord URL and contact information in `guild/templates/guild/base.html`.
3. Decide whether guild applications should send officer email/Discord notifications.
4. Switch local development from SQLite to MariaDB before writing database-specific integrations.
5. Add officer-only website pages for editing data without using Django Admin.

The supplied full-page concept image is saved under `docs/design-reference.png`. The banner crop used by the homepage is under `static/guild/images/hero-banner.png`.
