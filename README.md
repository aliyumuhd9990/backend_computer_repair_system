# Web-Based Computer Repair Service Management System — Backend

Backend API built with Django and Django REST Framework for the project described in the supplied abstract and Chapter One. The project source describes customer/device registration, repair requests, technician assignment, repair progress, payment records, and reports.

## Stack
- Python 3.11+
- Django 5.x
- Django REST Framework
- Simple JWT authentication
- django-filter
- SQLite for local development; configure PostgreSQL/MySQL for production if required.
- React + Bootstrap frontend will consume this REST API.

## Roles
- **Customer:** register, sign in, register own devices, submit repair requests, view own repairs/status history, cancel eligible requests, view own payment records and create a payment record.
- **Technician:** view assigned repairs and related devices, update status on assigned repairs.
- **Administrator:** manage records in Django Admin, assign technicians, update diagnosis/cost/status, record payments, and view system summary reports.
- **Superuser:** full Django administration access.

Public registration always creates a customer account. Create technicians/admin users from Django Admin or Django shell; never expose staff-role registration publicly.

## 1. Create and activate a virtual environment

Windows PowerShell:
```powershell
py -m venv .venv
.venv\\Scripts\\Activate.ps1
```

macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2. Install packages and configure environment
```bash
pip install -r requirements.txt
```
Copy `.env.example` to `.env` and change `DJANGO_SECRET_KEY`. The project settings currently use environment variables via the process environment; if you want `.env` auto-loading, add `load_dotenv()` from `python-dotenv` near the top of `settings.py`.

## 3. Create database tables and administrator
```bash
python manage.py makemigrations core
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
API root: `http://127.0.0.1:8000/api/`
Admin: `http://127.0.0.1:8000/admin/`

## 4. Create technician account
In Django Admin, create a User and set:
- username
- email
- password (set it through the user form or Django shell)
- role = `technician`
- is_active = True

Recommended safer shell method:
```bash
python manage.py shell
```
```python
from core.models import User
tech = User.objects.create_user(
    username="tech01",
    email="tech@example.com",
    password="ChangeThisPassword123!",
    first_name="Repair",
    last_name="Technician",
    role="technician",
    is_active=True,
)
```
To create a staff administrator, use Django Admin or create a superuser. Do not change a customer account to staff without reviewing access implications.

## Authentication
Login:
```http
POST /api/auth/login/
Content-Type: application/json

{"username": "customer1", "password": "YourPassword123!"}
```
Returns `access` and `refresh` JWT tokens. Send:
```http
Authorization: Bearer <access-token>
```
Refresh:
```http
POST /api/auth/refresh/
{"refresh": "<refresh-token>"}
```
Logout/blacklist refresh token:
```http
POST /api/auth/logout/
{"refresh": "<refresh-token>"}
```

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register/` | Register customer account |
| POST | `/api/auth/login/` | Obtain JWT tokens |
| POST | `/api/auth/refresh/` | Refresh access token |
| POST | `/api/auth/logout/` | Blacklist refresh token |
| GET/PATCH | `/api/auth/me/` | Read/update current profile |
| GET | `/api/dashboard/summary/` | Role-specific dashboard statistics |
| GET/POST | `/api/devices/` | List/create devices |
| GET/PATCH/PUT/DELETE | `/api/devices/{id}/` | Retrieve/update/delete device (owner/staff restrictions apply) |
| GET/POST | `/api/repairs/` | List own/assigned/all repairs; submit repair request |
| GET | `/api/repairs/{id}/` | Repair detail and status history |
| PATCH/PUT | `/api/repairs/{id}/` | Admin updates diagnosis, costs, assignment, status, notes |
| POST | `/api/repairs/{id}/update-status/` | Admin or assigned technician changes status |
| POST | `/api/repairs/{id}/assign-technician/` | Admin assigns technician |
| POST | `/api/repairs/{id}/cancel/` | Customer cancels eligible own request |
| GET/POST | `/api/payments/` | View own payments / create payment record |
| GET/PATCH/DELETE | `/api/payments/{id}/` | Admin payment record management |
| GET | `/api/technicians/` | Admin-only technician list |
| GET | `/api/status-history/` | Visible repair status history |

Most list endpoints support pagination. Filtering/search is enabled where configured, e.g. `/api/repairs/?status=in_progress`, `/api/repairs/?search=laptop`, `/api/devices/?device_type=laptop`.

## Example requests

### Register a customer
```json
POST /api/auth/register/
{
  "username": "customer1",
  "first_name": "Amina",
  "last_name": "Bello",
  "email": "amina@example.com",
  "phone": "08000000000",
  "address": "Kano, Nigeria",
  "password": "StrongPassword123!",
  "password_confirm": "StrongPassword123!"
}
```

### Register a device (authenticated customer)
```json
POST /api/devices/
{
  "device_type": "laptop",
  "brand": "HP",
  "model_name": "EliteBook",
  "serial_number": "HP-12345",
  "description": "Laptop powers on but screen stays black."
}
```

### Submit repair request
```json
POST /api/repairs/
{
  "device": 1,
  "problem_description": "Laptop does not display anything after power-on.",
  "priority": "normal"
}
```
Customer and status are assigned by the server. Do not send them from the frontend.

### Assign technician (administrator)
```json
POST /api/repairs/1/assign-technician/
{"technician_id": 2}
```

### Update repair status (administrator or assigned technician)
```json
POST /api/repairs/1/update-status/
{"status": "in_progress", "note": "Hardware diagnosis completed; repair started."}
```

### Record a payment
```json
POST /api/payments/
{
  "repair": 1,
  "amount": "15000.00",
  "method": "transfer",
  "status": "pending",
  "reference": "BANK-REF-123",
  "notes": "Initial payment"
}
```
**Important:** this starter backend records payment information; it does not charge a bank card or verify bank transfers automatically. In production, verify payments through a trusted payment provider or reconcile them manually before setting status to `paid`.

## Status values
`submitted`, `diagnosis`, `awaiting_approval`, `in_progress`, `waiting_parts`, `completed`, `ready_for_pickup`, `delivered`, `cancelled`.

## Security and production checklist
- Change `DJANGO_SECRET_KEY`; never commit secrets.
- Set `DJANGO_DEBUG=False`, configure `ALLOWED_HOSTS`, HTTPS, secure cookies, and trusted origins.
- Configure a production database and backups.
- Add automated tests for permissions, payment state transitions, and workflow rules.
- Add audit logging, email/SMS notifications, and payment-provider verification before a real commercial launch.
- Review data retention and privacy requirements.
- CORS origins are currently set for local Vite development; change them for deployment.
- This is a runnable starter implementation, not a security audit or payment processor.

## Project scope note
The uploaded project documents specify a web-based computer repair management system for customers, technicians, and administrators. The system manages records and workflow; it does not perform physical repairs or automated hardware diagnosis.
