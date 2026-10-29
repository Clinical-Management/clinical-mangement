# Clinical Management

Role-based clinic management app for **Admins**, **Doctors**, **Receptionists** and **Patients**, with ML/DL-powered features.

| Layer    | Stack                                  | Deploy |
| -------- | -------------------------------------- | ------ |
| Frontend | React 19 (Vite), Tailwind CSS v4, React Router | Vercel |
| Backend  | FastAPI, PyMongo (async), JWT auth     | Render |
| Database | MongoDB                                | MongoDB Atlas |
| ML / DL  | scikit-learn, ONNX Runtime (served by FastAPI) | Render (with backend) |

## Project layout

```
clinical-mangement/
├── frontend/                 React app (Vercel)
│   ├── src/
│   │   ├── api/              axios client + per-domain API calls
│   │   ├── components/       shared UI pieces
│   │   ├── context/          AuthContext (current user, login/logout)
│   │   ├── layouts/          DashboardLayout (sidebar + header)
│   │   ├── pages/            auth/, admin/, doctor/, patient/
│   │   └── routes/           ProtectedRoute + role config (home paths, nav links)
│   └── vercel.json           SPA rewrites
├── backend/                  FastAPI app (Render)
│   ├── app/
│   │   ├── main.py           app factory, CORS, lifespan (Mongo connect)
│   │   ├── core/             config, security (JWT/bcrypt), deps (auth & roles)
│   │   ├── db/               Mongo client + indexes
│   │   ├── schemas/          Pydantic request/response models
│   │   ├── services/         business logic / DB access
│   │   ├── api/v1/routes/    auth, admin, doctor, receptionist, patient, patients, ml
│   │   └── ml/               model registry, predictors, artifacts
│   ├── scripts/create_admin.py
│   └── tests/
├── ml/                       training workspace (notebooks, scripts, data)
└── render.yaml               Render blueprint
```

## Roles & auth

- **Patient**: self-registers at `/register`.
- **Doctor** / **Receptionist**: created by an admin (`POST /api/v1/admin/users` with `"role": "doctor"` or `"receptionist"`).
- **Admin**: first one is created with `scripts/create_admin.py`.

Login returns a JWT; the frontend stores it and sends `Authorization: Bearer <token>`.
Backend routes are guarded with `Depends(require_roles(Role.X))`; frontend routes with `<ProtectedRoute roles={[...]}>`.

## Local development

Prereqs: Node 20+, Python 3.11, a MongoDB instance (local or a free Atlas cluster).

**Backend**

```bash
cd backend
py -3.11 -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # then edit MONGODB_URI / JWT_SECRET
python -m scripts.create_admin admin@clinic.com "Admin" StrongPass123
uvicorn app.main:app --reload   # http://localhost:8000/docs
```

To populate a non-production database with synthetic demo data, run this instead of creating the first admin:

```bash
python -m scripts.seed_demo                 # add --no-staff-mfa to let demo staff sign in with a password only
```

All demo accounts use `DemoPass123!`:

| Role | Email | Name |
| --- | --- | --- |
| Admin | `admin@demo.clinic` | Demo Admin |
| Doctor (General Medicine) | `doctor@demo.clinic` | Dr. Asha Rao |I al
| Doctor (Paediatrics) | `pediatrician@demo.clinic` | Dr. Vikram Iyer |
| Receptionist | `receptionist@demo.clinic` | Neha Kulkarni |
| Patient | `patient@demo.clinic` | Priya Deshmukh (manages her son Aarav and father Suresh) |

The script also sets up the clinic letterhead (only if none is saved yet), both doctors' hours, fees and registration details, a holiday and a doctor's leave, nine patients, and about three months of visits run through the normal flow: vitals, examination notes, ICD-10 diagnoses, finalized prescriptions, bills with receipts (one part-paid, one due), a no-show and a cancellation. Today gets a live queue (waiting, in consultation, completed, booked for the evening), and there are upcoming bookings, automatically booked follow-ups and medicine reminders. Demo patients receive messages in the app inbox only.

Each run rebuilds the demo visits, so rerun it on the morning of a demo to get a fresh queue for that day. It resets the demo accounts to the listed password and clears their login lockouts; it refuses to overwrite accounts it did not create and will not run when `APP_ENV` is `production` or `prod`. Without `--no-staff-mfa`, staff accounts may be asked to set up an authenticator app on first sign-in. It adds only synthetic sample information; do not use these credentials for a real clinic.

**Frontend**

```bash
cd frontend
npm install
copy .env.example .env
npm run dev                     # http://localhost:5173
```

## Deployment

1. **MongoDB Atlas**: create a cluster, a DB user, and allow access from `0.0.0.0/0` (Render IPs are dynamic). Copy the connection string.
2. **Render (backend)**: New, then Blueprint, then pick this repo (uses `render.yaml`). Set `MONGODB_URI` and `CORS_ORIGINS` (your Vercel URL).
3. **Vercel (frontend)**: import the repo, set **Root Directory** to `frontend`, and add env var `VITE_API_URL=https://<your-render-service>.onrender.com/api/v1`.

Note: Render's free tier sleeps after inactivity (the first request takes about 30–60 s) and has 512 MB RAM, so serve DL models as ONNX.
