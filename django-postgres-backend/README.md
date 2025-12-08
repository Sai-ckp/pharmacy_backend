# Django PostgreSQL Backend

This project is a simple backend application built using Django and PostgreSQL. It serves as a foundation for developing web applications with a robust database backend.

## Project Structure

```
django-postgres-backend
├── manage.py
├── django_postgres_backend
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── core
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── tests.py
├── requirements.txt
├── .env
├── .gitignore
├── docker-compose.yml
└── Dockerfile
```

## Setup Instructions

1. **Clone the repository**:
   ```
   git clone <repository-url>
   cd django-postgres-backend
   ```

2. **Create a virtual environment**:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies**:
   ```
   pip install -r requirements.txt
   ```

4. **Configure the database**:
   Update the `.env` file with your PostgreSQL database credentials.

5. **Run migrations**:
   ```
   python manage.py migrate
   ```

6. **Run the development server**:
   ```
   python manage.py runserver
   ```

## Usage

You can access the application at `http://127.0.0.1:8000/`. Modify the `core/views.py` and `core/urls.py` files to customize the application functionality.

## Docker Support

This project includes a `Dockerfile` and `docker-compose.yml` for containerization. To build and run the application using Docker, execute:

```
docker-compose up --build
```

## License

This project is licensed under the MIT License. See the LICENSE file for more details.
## Scheduled Jobs

Use Django management commands and your system scheduler (cron) to run maintenance tasks.

Examples (crontab):

```
# Every night at 02:00 – expiry scan
0 2 * * * /usr/bin/python /path/to/django-postgres-backend/manage.py expiry_scan

# Every night at 02:15 – low stock scan
15 2 * * * /usr/bin/python /path/to/django-postgres-backend/manage.py low_stock_scan

# Every 15 minutes – dispatch notifications
*/15 * * * * /usr/bin/python /path/to/django-postgres-backend/manage.py dispatch_notifications

# Weekly on Sunday 03:00 – purge old logs per RetentionPolicy
0 3 * * 0 /usr/bin/python /path/to/django-postgres-backend/manage.py purge_logs

#medicine forms are renamed as the HSN code inside the catalog app
|_catalog(models)
