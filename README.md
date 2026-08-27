# RAWA-RENT

### Property, Tenant & Rental Management System

**RAWA-RENT** is a Django-based property and rental management platform designed to help property managers and real-estate agencies manage properties, units, tenants, rent charges, payments, deposits, receipts, audit trails, and tenant self-service from a centralized system.

The project is built around a strong focus on **financial integrity, role-based access, auditability, and reliable rental accounting** rather than treating rent management as simple CRUD operations.

> **Project status:** Active development / portfolio project

## Overview

Managing rental properties manually can lead to duplicated records, payment-entry errors, unclear tenant balances, weak accountability, and difficulty tracking changes across properties and staff members.

RAWA-RENT aims to provide a structured digital workflow for the complete rental lifecycle:

**Property → Unit → Tenancy → Charges → Payment Claim → Verification → Allocation → Ledger → Receipt**

The system separates operational records from financial posting so that a payment is not treated as money received simply because a staff member entered a transaction reference.

## Key Features

### 🏢 Property & Unit Management

- Manage multiple properties within an organization
- Manage individual rental units
- Define and manage house/property types
- Track unit occupancy and availability
- Associate tenants with specific tenancies and units

### 👤 Tenant & Tenancy Management

- Tenant records and profiles
- Active tenancy management
- Tenancy status tracking
- Tenant-to-unit relationships
- Rental billing information
- Support for tenancy changes and transfers

### 💰 Rental Finance & Ledger

- Generate rental charges
- Track outstanding balances and arrears
- Maintain tenant financial statements
- Separate deposits from rental income
- Allocate verified payments against outstanding charges
- Calculate balances from financial transactions rather than relying on manually maintained totals

### 📱 Payment Verification Workflow

One of the core design principles of RAWA-RENT is that **entering a payment reference does not automatically make the payment verified**.

The payment lifecycle is:

```text
CLAIM
  ↓
PENDING VERIFICATION
  ↓
VERIFY / REJECT
  ↓
LEDGER POSTING
  ↓
ALLOCATION
```

A staff member can record a payment claim, but an authorized user must verify it before it affects the ledger. The verification workflow also prevents the same user who created the claim from verifying it and requires a financial PIN for verification.

This is designed to provide **segregation of duties and reduce internal financial fraud**.

### 🧾 Receipts & Documents

- Generate rental/payment receipts
- PDF/document generation support
- Tenant-facing financial documents
- Printable transaction records

### 🔐 Authentication & Access Control

- Django authentication
- Organization-aware application structure
- Role/permission-oriented architecture
- Protected financial operations
- Financial PIN verification for sensitive payment actions

### 📝 Audit Trail

Important financial operations are audit logged, including payment claims, verification, rejection, and ledger-related actions.

This creates a traceable history of who performed sensitive operations and when they occurred.

### 📥 Data Migration

The project includes a migration wizard for bringing existing rental/property data into the system, helping agencies transition from spreadsheets or legacy records into a structured database.

### 🔔 Notifications

A dedicated notifications application provides a foundation for communicating important system events to users and tenants.

## Architecture

RAWA-RENT is organized into Django applications around business domains rather than placing the entire system inside one application.

```text
RAWA-RENT/
├── accounts/              # Authentication and user-related functionality
├── audit/                 # Audit logging and accountability
├── core/                  # Shared/core business functionality
├── finance/               # Charges, ledger and financial services
├── migration_wizard/     # Data import/migration workflows
├── notifications/        # Application notifications
├── organizations/        # Organization/business management
├── payments/             # Payment-related workflows
├── portal/                # Tenant/user portal functionality
├── properties/            # Properties, units and property types
├── receipts/              # Receipt/document generation
├── rawarent/              # Django project configuration
├── static/                # Static assets
├── manage.py
└── requirements.txt
```

The repository is currently organized into dedicated Django applications including accounts, audit, core, finance, migration_wizard, notifications, organizations, payments, portal, properties, and receipts.

## Financial Integrity Design

Financial correctness is a major architectural concern in RAWA-RENT.

The payment service implements a controlled lifecycle in which:

1. A staff member records a payment claim.
2. The payment remains pending verification.
3. The transaction reference is checked for duplication.
4. A different authorized user verifies the payment.
5. The verifier must provide a valid financial PIN.
6. Only after successful verification is the payment posted to the ledger.
7. The verified amount can then be allocated to deposits and outstanding charges.
8. The operation is recorded in the audit trail.

This approach helps prevent a user from simply typing an M-Pesa transaction code and immediately increasing a tenant's account balance.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming language |
| Django 5.2 | Web application framework |
| Django REST Framework | API capabilities |
| MySQL | Relational database |
| HTML5 | Application interface |
| CSS3 | Styling |
| Bootstrap | Responsive UI components |
| JavaScript | Client-side interactions |
| WhiteNoise | Static file serving |
| WeasyPrint | PDF/document generation |
| Pandas | Data processing and migration |
| OpenPyXL | Excel import/export workflows |
| Pillow | Image processing |
| django-cors-headers | Cross-origin request support |

The dependency configuration includes Django 5.2, Django REST Framework, MySQL client support, WhiteNoise, WeasyPrint, Pandas, OpenPyXL, Pillow, and related packages. fileciteturn1file0L2-L2

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Jeffmuturi45/RAWA-RENT.git
cd RAWA-RENT
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

On Linux/macOS:

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file and configure the database and other environment-specific settings required by the project.

Example structure:

```env
SECRET_KEY=your-secret-key
DEBUG=True
DB_NAME=rawarent
DB_USER=your-database-user
DB_PASSWORD=your-database-password
DB_HOST=127.0.0.1
DB_PORT=3306
```

Do not commit real credentials, production secrets, passwords, or private keys to GitHub.

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Create an administrator

```bash
python manage.py createsuperuser
```

### 7. Start the development server

```bash
python manage.py runserver
```

Then open:

```text
http://127.0.0.1:8000/
```

## Database

RAWA-RENT is configured as a relational Django application and includes MySQL client support in its dependency set.

For local development, create a MySQL database and configure the corresponding credentials through environment variables rather than hard-coding them in source code.

## Security Principles

The project follows several security-oriented principles:

- Sensitive financial operations require authorization.
- Payment references are checked for duplicates.
- Payment claims and verification are separate operations.
- The payment creator cannot verify their own payment claim.
- Financial verification requires a financial PIN.
- Financial operations use database transactions where atomicity is important.
- Important state changes are audit logged.
- Secrets should be supplied through environment variables.

## Project Goals

RAWA-RENT is being developed to demonstrate how a real-world rental management platform can go beyond basic CRUD functionality and implement business rules that matter in production environments.

The primary goals are:

- Reduce manual rental administration
- Improve visibility into property occupancy
- Maintain accurate tenant balances
- Reduce payment-entry fraud
- Provide traceable financial operations
- Simplify property and tenant administration
- Provide tenants with access to their rental information
- Support migration from existing rental records

## Current Development Focus

The project is under active development. Areas being refined include:

- Tenant portal workflows
- Property and tenancy lifecycle management
- Financial allocation rules
- Deposit handling during tenancy changes
- Payment verification and audit controls
- Data migration workflows
- Notifications
- Production deployment hardening

## Future Improvements

Potential future enhancements include:

- Automated M-Pesa statement reconciliation
- M-Pesa/API integrations
- SMS and email notifications
- Advanced financial reporting
- Owner/property-owner portals
- Automated recurring rent reminders
- Role-specific dashboards
- Cloud deployment and monitoring
- Automated testing and CI/CD

## Why RAWA-RENT?

RAWA-RENT is not intended to be only a property listing application. It is designed around the operational and financial processes that property managers deal with every day.

The project demonstrates practical backend engineering concepts including:

- Domain-based Django architecture
- Authentication and authorization
- Relational data modeling
- Transactional financial operations
- State-machine-style payment workflows
- Audit logging
- Data migration
- Document generation
- Business-rule enforcement
- Separation of financial claim and verification responsibilities

## Author

**Jeff Muturi**

ICT / Web Developer

- GitHub: https://github.com/Jeffmuturi45

## License

This project is currently presented as a portfolio and development project. Licensing terms can be added when the project is prepared for public distribution or commercial use.

---

**RAWA-RENT — Building reliable digital workflows for modern property management.**