# main-backend

This repository is a small FastAPI + SQLAlchemy service for authentication (users).

## Development setup (macOS / zsh)

1. Create and activate a virtual environment

```bash
# create a venv in the project root
python3 -m venv .venv

# activate it (zsh)
source .venv/bin/activate
```

2. Install Python dependencies

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

3. Database notes and setup

- The project uses PostgreSQL. The default connection URL is in `Auth/database.py`:

```
postgresql://postgres:password@localhost/fastapi_db
```

- DB name used by the project: `fastapi_db`.

- Create the database locally (requires PostgreSQL installed). Example using `psql`:

```bash
# open psql as the postgres user
psql -U postgres

# inside psql create the database (run these in the psql prompt):
CREATE DATABASE fastapi_db;
\q
```

If your Postgres user/password or host are different, update the `SQLALCHEMY_DATABASE_URL` in `Auth/database.py` or set environment variables and modify the code accordingly.

4. Run the FastAPI server

```bash
# from the project root (Auth folder contains main.py)
cd Auth
uvicorn main:app --reload
```

5. Quick checks

- Verify the server is running at http://127.0.0.1:8000.
- Open the interactive API docs at http://127.0.0.1:8000/docs.
- To verify the DB connection using psql after creating the DB:

```bash
psql -U postgres -d fastapi_db
\dt   # list tables (empty until you create users via the API)
\q
```

6. Common troubleshooting

- If `ModuleNotFoundError: No module named 'sqlalchemy'` or similar occurs, make sure the virtualenv is activated and dependencies are installed.
- If you get authentication/connection errors for Postgres, double-check credentials and that the Postgres server is running (e.g. `brew services start postgresql` or your system's service manager).

7. (Optional) Expose `models.Base`

If you prefer to reference `models.Base` instead of `database.Base`, there's an `Auth/models/__init__.py` that exports `Base` and `User`.

---

Follow these steps and you should be able to run and test the service locally.
