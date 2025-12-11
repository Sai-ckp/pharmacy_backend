# How to Delete All Data from Azure Database

## ⚠️ WARNING
**This will permanently delete ALL data from your database. Make sure you have backups if needed!**

## Method 1: Using Django Flush Command (Recommended)

### Via Azure App Service Console:
1. Go to Azure Portal → Your App Service
2. Navigate to **Console** or **SSH**
3. Run:
```bash
cd /home/site/wwwroot
python manage.py flush --noinput
python manage.py migrate
```

### Via Local Machine (if connected to Azure DB):
```bash
# Set Azure DATABASE_URL in your environment
export DATABASE_URL="postgres://user:password@host:5432/dbname?sslmode=require"

# Run flush
python manage.py flush --noinput

# Re-run migrations if needed
python manage.py migrate
```

## Method 2: Using the Clear Script

Run the provided Python script:
```bash
# From your local machine (with Azure DB connection)
python clear_azure_db.py

# Or use direct SQL method
python clear_azure_db.py --sql
```

## Method 3: Using Azure Portal Query Editor

1. Go to **Azure Portal** → Your **PostgreSQL Flexible Server** (or Database)
2. Click on **Query editor** in the left menu
3. Connect to your database
4. Run this SQL:

```sql
-- Disable foreign key checks
SET session_replication_role = 'replica';

-- Truncate all tables
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') 
    LOOP
        EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;

-- Re-enable foreign key checks
SET session_replication_role = 'origin';
```

## Method 4: Using psql Command Line

### Connect via psql:
```bash
# Get connection string from Azure Portal → Connection strings
psql "host=your-host.postgres.database.azure.com port=5432 dbname=your-db user=your-user password=your-password sslmode=require"

# Once connected, run:
SET session_replication_role = 'replica';

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') 
    LOOP
        EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;

SET session_replication_role = 'origin';
```

## Method 5: Drop and Recreate Database (Nuclear Option)

⚠️ **This completely removes the database. You'll need to run all migrations again.**

### Via Azure Portal:
1. Go to Azure Portal → Your PostgreSQL Server
2. Find your database
3. Click **Delete**
4. Create a new database with the same name
5. Run migrations: `python manage.py migrate`

### Via psql:
```sql
-- Connect to postgres database (not your app database)
\c postgres

-- Drop your database
DROP DATABASE your_database_name;

-- Create new database
CREATE DATABASE your_database_name;

-- Reconnect and run migrations
\c your_database_name
```

Then run migrations from your app:
```bash
python manage.py migrate
```

## Recommended Approach

**For Azure App Service:**
1. Use **Method 1** (Django flush) via Azure Console or SSH
2. Or use **Method 3** (Azure Portal Query Editor) for a GUI approach

**For Local Development:**
- Use **Method 1** or **Method 2** (the Python script)

## After Clearing Data

1. **Run migrations** (if needed):
   ```bash
   python manage.py migrate
   ```

2. **Create superuser** (if needed):
   ```bash
   python manage.py createsuperuser
   ```

3. **Load initial data** (if you have fixtures):
   ```bash
   python manage.py loaddata initial_data.json
   ```

4. **Reconfigure settings** (business profile, locations, etc.) through the admin or your app's settings page.

