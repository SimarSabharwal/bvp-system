# BVP Academic ERP & Smart Timetable System

> **Real-Time Academic Resource Management Platform with Dynamic Lecture Reallocation**

A modern, production-ready Academic ERP built with Python, Flask, SQLAlchemy, PostgreSQL, and WebSockets. Designed to eliminate wasted classroom hours by dynamically reorganizing timetables during faculty unavailability while keeping students, faculty, and administrators updated in real time.

---

## 🌟 Key Highlights & Core Differentiators

* **Intelligent Lecture Reallocation (No Generic Substitution):** When a teacher is absent, the system does not place an unqualified substitute. Instead, it inspects the curriculum requirements of the affected section and pulls forward an upcoming lecture in another required subject taught by an available faculty member in their own discipline. Missed lectures are tracked as *Pending Reallocation* and rescheduled within valid slots.
* **Real-Time Event Bus & Instant Alerts:** Leverages WebSockets (`Flask-Sock`) and a transactional outbox pattern to broadcast schedule updates, room changes, and urgent notifications to connected clients within 3 seconds.
* **Smart Timetable Generator & Multi-Draft Lifecycle:** Automatically generates conflict-free schedules satisfying faculty workload limits, classroom capacities, section shift constraints (morning/afternoon), and break intervals. Supports multi-version draft staging and one-click publishing.
* **Role-Based Access Control (RBAC):** Hardened server-side authorization partitioned across Student, Teacher, and Administrator roles with session security, rate limiting, and CSRF protection.
* **Master Data & Academic Catalog Management:** Full management of Academic Years, Courses (e.g., BCA, BBA), Sections, Semesters, Rooms/Labs, Teacher Qualifications, and Teaching Assignments.
* **Curriculum & Attendance Analytics:** Real-time tracking of planned vs. delivered lecture hours, syllabus completion rates, and individual/section-wise attendance reporting.

---

## 🏗️ Architecture & Technology Stack

| Layer | Technologies |
|---|---|
| **Backend Framework** | [Flask](https://flask.palletsprojects.com/) (3.1+), [Werkzeug](https://werkzeug.palletsprojects.com/), [Pydantic](https://docs.pydantic.dev/) v2 |
| **Database & ORM** | [PostgreSQL](https://www.postgresql.org/), [SQLAlchemy](https://www.sqlalchemy.org/) 2.0, [psycopg3](https://www.psycopg.org/psycopg3/) |
| **Migrations** | [Alembic](https://alembic.sqlalchemy.org/) |
| **Realtime / Sockets** | [Flask-Sock](https://github.com/miguelgrinberg/flask-sock) (WebSocket), Transactional Outbox Pattern |
| **WSGI Server** | [Gunicorn](https://gunicorn.org/) / Werkzeug development server |
| **Frontend UI** | Responsive Single-Page Application (SPA) with modern Glassmorphic styling, modular components, and native WebSocket synchronization |
| **API Contract** | OpenAPI 3.0 specification (`openapi.yaml`) |

---

## 📁 Repository Structure

```text
├── app/                        # Application source code
│   ├── api/                    # REST API route blueprints
│   │   ├── auth.py             # Authentication & session endpoints
│   │   ├── communications.py   # Notifications, announcements, broadcast
│   │   ├── health.py           # Liveness & readiness health checks
│   │   ├── master_data.py      # CRUD for courses, sections, rooms, teachers
│   │   ├── mock_data.py        # Seed & synthetic catalog endpoints
│   │   ├── reallocation.py     # Dynamic reallocation algorithm & engine
│   │   ├── reports.py          # Attendance & utilization reporting
│   │   ├── scheduling.py       # Published schedule & calendar APIs
│   │   └── smart_timetable.py  # Timetable generator & draft workflows
│   ├── models/                 # SQLAlchemy 2.0 database models
│   ├── static/                 # Glassmorphic UI CSS, JavaScript modules
│   │   ├── css/                # glassmorphism.css
│   │   └── js/                 # SPA components (admin, teacher, student)
│   ├── templates/              # Jinja2 template entrypoints (index.html)
│   ├── config.py               # Environment configuration loader
│   ├── extensions.py           # SQLAlchemy, Migrations, and Socket extensions
│   └── realtime.py             # WebSocket connection manager & event dispatcher
├── data/                       # Initial data catalogs and seed definitions
├── migrations/                 # Alembic database migration revisions
├── scripts/                    # Automation and management scripts
│   ├── benchmark_phase9.py     # Concurrency & load benchmark suite
│   ├── create_admin.py         # CLI utility to provision admin accounts
│   ├── dispatch_outbox.py      # Background worker for notification outbox
│   └── seed_dev.py             # Development database seeder
├── openapi.yaml                # Complete OpenAPI 3.0 API definition
├── wsgi.py                     # WSGI application entrypoint
├── requirements.txt            # Python dependencies
└── docs/                       # Architectural documentation (PRD, TRD, DB Design)
```

---

## 🚀 Getting Started

### Prerequisites

* **Python:** 3.12 or 3.14 recommended
* **PostgreSQL:** 16+ or 18
* **Git**

### 1. Clone the Repository

```bash
git clone https://github.com/SimarSabharwal/bvp-system.git
cd bvp-system
```

### 2. Set Up Virtual Environment

```bash
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Configure your database connection string and secret keys:

```dotenv
FLASK_ENV=development
SECRET_KEY=your-secure-random-secret-key
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/bvp_academic_db
PORT=5050
```

### 5. Run Database Migrations

Apply the database schema using Alembic:

```bash
alembic upgrade head
```

### 6. Create Initial Administrator / Seed Data

```bash
# Create an administrator account
python scripts/create_admin.py --username admin --email admin@bvp.edu --password SecurePassword123!

# (Optional) Seed development dataset
python scripts/seed_dev.py
```

### 7. Launch the Application

```bash
# Development mode
flask --app wsgi run --host 127.0.0.1 --port 5050

# Production mode
gunicorn -w 4 -k gthread --threads 4 -b 0.0.0.0:5050 wsgi:app
```

Navigate to `http://127.0.0.1:5050` in your web browser.

---

## 📖 In-Depth Documentation

For architectural deep-dives, database schemas, and operational instructions, see the bundled documentation:

* [Product Requirements Document (PRD.md)](file:///c:/Users/ssima/OneDrive/Desktop/Student%20System/PRD.md)
* [Database Design & Schema (DATABASE_DESIGN.md)](file:///c:/Users/ssima/OneDrive/Desktop/Student%20System/DATABASE_DESIGN.md)
* [Technical Architecture & TRD (TECH_STACK_TRD.md)](file:///c:/Users/ssima/OneDrive/Desktop/Student%20System/TECH_STACK_TRD.md)
* [Role & Access Control Matrix (ROLE_ACCESS_MATRIX.md)](file:///c:/Users/ssima/OneDrive/Desktop/Student%20System/ROLE_ACCESS_MATRIX.md)
* [Demo Guide & Test Credentials (DEMO_GUIDE.md)](file:///c:/Users/ssima/OneDrive/Desktop/Student%20System/DEMO_GUIDE.md)
* [Operations & Runbook (OPERATIONS.md)](file:///c:/Users/ssima/OneDrive/Desktop/Student%20System/OPERATIONS.md)
* [OpenAPI 3.0 Specification (openapi.yaml)](file:///c:/Users/ssima/OneDrive/Desktop/Student%20System/openapi.yaml)

---

## 🔒 Security & Best Practices

* Passwords hashed using industry-standard password derivation (`argon2id` / `scrypt`).
* Session cookies secured with `HttpOnly`, `SameSite=Lax`, and `Secure` attributes in production.
* Strict input validation using Pydantic schemas.
* Transactional outbox pattern prevents dual-write anomalies during real-time event broadcasting.

---

## 📄 License

This project is developed for academic resource scheduling and administration. All rights reserved.
