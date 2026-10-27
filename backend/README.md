# Backend

Run the API from this directory with:

```powershell
$env:SECRET_KEY = (.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
.\venv\Scripts\python.exe -m uvicorn main:app --reload
```

The API requires a unique `SECRET_KEY` environment variable for signing access
tokens. Generate a new value for local development as shown above and configure
a stable secret through your deployment platform in production. Never commit
the secret to the repository. The database accepts either a `DATABASE_URL`
connection string or the individual `DB_USER`, `DB_PASSWORD`, `DB_HOST`,
`DB_PORT`, and `DB_NAME` variables.

## Public registration

Public sign-up is available at `/signup` and creates CITIZEN accounts through
`POST /register`. Worker accounts require an assigned area and must be created
by an administrator; ADMIN and MONITOR roles are never accepted through public
registration.

Apply the nullable phone-number migration to an existing database before
starting the updated API:

```powershell
psql -h HOSTNAME -p PORT -U USERNAME -d DATABASE_NAME -f migrations/003_add_user_phone_number.sql
```

The new column stays nullable for existing accounts. Newly registered phone
numbers are stored in normalized format. Passwords use the existing bcrypt
hashing configuration, and registration responses omit both the password and
its hash.

## Team zone migration

Before using the Monitor **Teams** page, apply `migrations/001_create_teams.sql` once to the configured PostgreSQL database. From this directory, run:

```powershell
psql -h HOSTNAME -p PORT -U USERNAME -d DATABASE_NAME -f migrations/001_create_teams.sql
```

If `001_create_teams.sql` was already applied, apply `migrations/002_allow_shared_team_vehicles.sql` to remove any single-vehicle team uniqueness constraint without changing team or vehicle rows:

```powershell
psql -h HOSTNAME -p PORT -U USERNAME -d DATABASE_NAME -f migrations/002_allow_shared_team_vehicles.sql
```

The same `002` migration should be applied immediately after `001` when setting up a new database. Vehicles in `MAINTENANCE`, `OFFLINE`, or legacy `INACTIVE` status cannot be assigned to a team; vehicles in `ACTIVE`, `AVAILABLE`, `ASSIGNED`, or `IN_SERVICE` status may be shared by teams in different areas.

Team boundaries are stored as the four outermost coordinates. They are recalculated from the area's coordinates, its waste report coordinates, and the latest GPS point for each vehicle assigned to a worker in that area or directly assigned to one of its teams. New waste reports and vehicle GPS updates refresh the stored bounds for every affected team, and reading the team list recalculates them to capture other area-location changes.

## Bhopal development data

From this directory, run the deterministic development seeder with:

```powershell
.\venv\Scripts\python.exe seed_data.py
```

It uses random seed `42`, the existing municipal ward polygons and ward
populations as demand priors, and inserts 1,000 citizens, 50 workers, 2,000 waste
reports, 200 complaints, 10 vehicles, and 2,000 GPS records by default. The
`0.45 kg/person/day` baseline is only a development-data assumption. Ward 44's
population remains `NULL`; it receives a neutral median-population sampling
weight only.

Generated citizens are mapped to wards in the seeder-managed
`development_seed_citizen_wards` table using demand-weighted allocation; their
generated reports and complaints are aligned to that ward. When extending an
existing registered dataset, the seeder adds missing citizens and workers
without deleting or regenerating waste reports. Additional workers are selected
from unstaffed report-bearing areas using demand, observed waste volume, and
unassigned collection workload.

The script preserves the 85 municipal wards and all existing areas, including
the four Chhola areas. It creates exactly one clearly labelled provisional,
ward-polygon-backed operational area for each ward with no existing area; these
areas are not represented as official locality boundaries. It does not split
any ward. Workers are assigned to one demand-prioritized area and each belongs
to one generated team. Collection requests are only made for reports in areas
with a matching assigned worker, so the approximately 80% request rate applies
to staffed-area reports, not all ward reports. Unstaffed-area reports remain
available for later staffing/area analysis.

Generated account emails use `seed.citizen...@example.com` and
`seed.worker...@example.com`; the development password is `BhopalDev123!`.
The seed registry makes repeated runs idempotent. To remove only records
registered as created by this seeder, run:

```powershell
.\venv\Scripts\python.exe seed_data.py --reset-generated
```

Reset preserves municipal wards, their geometry, and pre-existing areas. It
refuses to remove generated records if non-seed application data references
them. The seeder validates foreign-key relationships and report/GPS containment
in both operational-area and municipal-ward geometry, then prints ward-level
waste, collection, segregation, and complaint summaries. ETL includes the
citizen-to-ward mapping in its citizen dimension; EDA exports per-ward citizen
counts to `citizen_home_ward_distribution.csv`.

### Development operations login

The seeder can create one ADMIN account only when no ADMIN or MONITOR account
already exists. Configure the credentials in the backend process environment
(or the backend-only `db.env` file), never in frontend environment variables:

```powershell
$env:MONITOR_ADMIN_EMAIL = "admin@example.test"
$env:MONITOR_ADMIN_PASSWORD = "<choose-a-unique-password-of-12-to-72-bytes>"
$env:MONITOR_ADMIN_ROLE = "ADMIN" # Optional: ADMIN (default) or MONITOR
.\venv\Scripts\python.exe seed_data.py --ensure-operations-account
```

This command changes only the `users` table if it needs to create the account;
it does not regenerate or delete sample data. The password is bcrypt-hashed.
The command will not replace or promote an existing user. Log in at
`/monitor-login` with the configured email; workers may use `W:<worker_id>` on
the regular sign-in form, and a user ID may be prefixed with `U:` to disambiguate it.

## Analytics and Power BI

The read-only ETL and EDA workflow, output catalog, Power BI model guidance,
development priority-score caveats, and SQL business questions are documented
in [`analytics/README.md`](analytics/README.md). Run both workflows from this
directory:

```powershell
.\venv\Scripts\python.exe etl\run_etl.py
.\venv\Scripts\python.exe eda.py
```

ETL snapshots and analytics exports are written under `data\`; EDA reports and
charts are written under `eda_output\`. These workflows do not write to
PostgreSQL.

## Collection monitoring

The Monitor workspace's **Monitoring** page polls the read-only
`GET /monitor/monitoring` endpoint every 45 seconds. It reports collection
statuses, current vehicle GPS positions, pending requests, prioritized alerts,
ward attention indicators, and map markers from stored coordinates. The
endpoint uses the existing PostgreSQL tables and does not require a schema
migration.

## Analytics-readiness acceptance tests

Run the 20-test read-only acceptance suite from this directory after refreshing
the ETL snapshot:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_analytics_readiness -v
```

The tests open PostgreSQL in a read-only transaction and do not invoke the
seeder or modify source tables. Seeder idempotency is checked by confirming the
seed registry already contains the requested generated records, so a rerun
would require zero new rows.
