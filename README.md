# Campus Skill Exchange

A student-to-student skill sharing web application for a college minor project. Students list what they can teach and want to learn, get transparent complementary-skill matches, exchange requests, schedule sessions, and leave feedback.

## Four course components

| Component | Language / technology | Demonstration |
| --- | --- | --- |
| DAA (Design and Analysis of Algorithms) | C++ | Stable merge sort ranks match records by descending score and then name. `01_DAA/merge_sort.cpp` has `O(n log n)` time and `O(n)` auxiliary-space complexity. |
| AIP (Artificial Intelligence Programming) | Python | Explainable content-based recommendation compares teach/learn skill sets. `02_AIP/recommendation_demo.py` runs sample recommendations. This is a rule-based recommender, not a trained ML model. |
| PL/SQL | Oracle PL/SQL | `03_PL_SQL/campus_skill_exchange.sql` creates Oracle tables, constraints, indexes, and a stored package for matching. |
| Application | Python, Flask, SQLAlchemy | `04_Python/` contains the web application. It runs locally with SQLite by default and can connect to MySQL through `DATABASE_URL`. |

DAA and AIP name academic subjects rather than specific programming languages; this project uses C++ for the DAA algorithm demonstration and Python for AIP.

## Features

- Student registration, secure password hashing, login/logout, private routes, profiles, and profile editing.
- Rich profile preferences for learning format, campus location, languages, and scheduling notes.
- Skill directory with categories, teach/learn lists, proficiency levels, and duplicate prevention.
- Student and skill discovery filters for skill, student name, college, category, and proficiency, plus sorting and profile previews.
- Suggested matches with a defined score: `50 points` if the student teaches something the peer wants to learn, plus `50 points` if the peer teaches something the student wants to learn. Scores are `0`, `50`, or `100`; the signed-in student is excluded.
- Skill suggestions explain related profile categories and how many active students teach each suggested skill.
- Private student conversations, unread message counts, notifications, and saved student/skill lists.
- Owned exchange requests with receiver accept/reject and sender cancellation.
- Shared availability slots, an upcoming 30-day calendar, accepted-request scheduling, and participant-approved rescheduling. Conflicting times are rejected. Online meeting links are not generated.
- In-app notifications with read state and reviews for completed sessions (one review per participant per session, rating 1–5).
- Server-checked administrator area for usage statistics, popular skills, student account enable/disable, skill/category additions, request monitoring, and reports.
- CSRF protection, environment-based secrets, parameterized SQL through SQLAlchemy, server-side ownership checks, and no public built-in admin password.

The new tables for these additions are created automatically on the next application startup with `db.create_all()`; existing user, skill, request, session, and review records are retained. If applying the schema manually, run the updated MySQL or Oracle script in the appropriate database.

## Deploy a shareable Railway website

Railway generates the public `*.up.railway.app` link only after you deploy the project from your own Railway account. This workspace is not linked to your account, so no public URL exists yet. The deployment uses Railway's MySQL service; the local SQLite database is excluded and is not uploaded.

1. Create or sign in to a [Railway account](https://railway.com/). Review its current plan and usage charges before deploying. Install Node.js 16+ if it is not already available, then install and sign in to the Railway CLI in PowerShell:

   ```powershell
   npm install -g @railway/cli
   railway login
   ```

2. From this project directory (`D:\projects of python\CampusSkillExchange`), initialize a Railway project:

   ```powershell
   Set-Location 'D:\projects of python\CampusSkillExchange'
   railway init
   ```

   Follow the prompts to create a project. In its Railway dashboard, add a **MySQL** database service (`+ New` → `Database` → `MySQL`). Keep the database private; the Flask app connects inside the Railway project.

3. Add an application service variable reference, replacing `MySQL` with the exact name of the database service if you renamed it:

   ```text
   DATABASE_URL=${{MySQL.MYSQL_URL}}
   ```

   On the application service, add `SECRET_KEY` with a new random value generated locally (do not put it in source control):

   ```powershell
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   Also set `COOKIE_SECURE=1` and `FLASK_DEBUG=0`. Add these as service variables in Railway, not to a committed file. Do not import the placeholder values from `.env.example`.

4. Deploy this folder using the CLI:

   ```powershell
   railway up
   ```

   The included [Procfile](./Procfile) starts Gunicorn on Railway's `$PORT`; the `/healthz` endpoint checks database connectivity. The app initializes its schema and skill directory at startup.

5. When the deployment is healthy, select the app service in Railway → **Settings** → **Networking** → **Generate Domain**. Railway will create an HTTPS `*.up.railway.app` URL. Open that URL and test registration and the main features before sending it on WhatsApp. This is the public link; `http://127.0.0.1:5000` remains local-only.

6. The deployed app has a new, empty MySQL database. Local student accounts are deliberately not copied. Create a fresh student account on the public site. If you need the admin area, add `ADMIN_NAME`, `ADMIN_EMAIL`, and a private `ADMIN_PASSWORD` (at least 12 characters) to the app service variables, deploy those changes, and create the first admin once from the app container:

   ```powershell
   railway ssh --service <APP_SERVICE_NAME>
   ```

   In the remote shell:

   ```sh
   cd /app/04_Python
   flask --app run:app create-admin
   ```

   Remove `ADMIN_PASSWORD` (and the other one-time bootstrap variables if desired) from Railway's service variables and redeploy. The command refuses to create a second administrator.

**Public-demo caution:** public registration currently checks email format but does not verify college membership. Use fictional/demo profile information during a public presentation; do not collect sensitive personal information. Use the Railway-generated HTTPS URL only after reviewing who can register and your host's usage/cost settings.

## Project structure

```text
CampusSkillExchange/
├── 01_DAA/
│   └── merge_sort.cpp
├── 02_AIP/
│   └── recommendation_demo.py
├── 03_PL_SQL/
│   └── campus_skill_exchange.sql
├── 04_Python/
│   ├── run.py
│   ├── mysql_schema.sql
│   └── skill_exchange/
│       ├── app.py
│       ├── matching.py
│       ├── models.py
│       ├── static/css/style.css
│       └── templates/
├── tests/test_app.py
├── .env.example
├── requirements.txt
└── README.md
```

## Run locally on Windows

1. Install Python 3.10+ and (optionally) a C++ compiler. For MySQL, install MySQL 8.0.16+ and create an empty database.
2. Open PowerShell in this project folder. Create and activate a virtual environment, then install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

3. Edit `.env`. Generate a private secret key (for example, `python -c "import secrets; print(secrets.token_hex(32))"`) and set `SECRET_KEY`. The default database is local SQLite. To use MySQL instead, set a URL such as:

   ```text
   DATABASE_URL=mysql+pymysql://cse_user:your-local-password@localhost/campus_skill_exchange
   ```

   Create the database and local user in MySQL first. SQLAlchemy initializes application tables at startup; the complete schema can also be run/reviewed in `04_Python/mysql_schema.sql`.

4. Initialize the schema and start the application. In PowerShell:

   ```powershell
   Set-Location .\04_Python
   flask --app run:app init-db
   python run.py
   ```

   Visit `http://127.0.0.1:5000`. The skill directory is seeded automatically. No demonstration accounts or passwords are created.

5. Leave the app running and open a second PowerShell terminal in `CampusSkillExchange\04_Python`. To create the administrator, set these environment variables in that terminal and use Flask's CLI. Use a unique password of at least 12 characters; do not commit it:

   ```powershell
   $env:ADMIN_NAME = "Project Administrator"
   $env:ADMIN_EMAIL = "admin@your-college.example"
   $env:ADMIN_PASSWORD = "use-a-long-private-password"
   flask --app run:app create-admin
   Remove-Item Env:ADMIN_PASSWORD
   ```

   Then sign in with that email and password. All `/admin` actions verify the role on the server.

6. Register two ordinary student accounts, list complementary skills, send a request, accept it from the receiving account, schedule a future session, mark it completed, and submit a review from each participant.

For a local presentation, SQLite is the quickest option and needs no separate database service. The Oracle PL/SQL script is a separate course deliverable and runs in an Oracle schema; it is not the backend database driver for the Flask app.

## Run the course demonstrations

### AIP — Python recommender

```powershell
python .\02_AIP\recommendation_demo.py
```

The score is explicitly based on complementary directions rather than ML confidence: `50` points for a peer who can teach one of your learning goals and `50` for a peer who wants to learn one of your teaching skills. A stable sort orders equal scores by student name.

### DAA — C++ merge sort

With `g++` installed:

```powershell
g++ .\01_DAA\merge_sort.cpp -o .\01_DAA\merge_sort.exe
.\01_DAA\merge_sort.exe
```

The example sorts sample match results highest-score-first, then alphabetically. Its sorting algorithm runs in `O(n log n)` time and uses `O(n)` temporary storage.

### PL/SQL — Oracle

Open `03_PL_SQL/campus_skill_exchange.sql` in Oracle SQL Developer and run it as a script (F5) in a new schema. To call the example package after adding users and skills:

```sql
SET SERVEROUTPUT ON
EXEC cse_match_pkg.recommend_for(1);
```

Oracle identity columns require a supported modern Oracle version. Do not run the schema script a second time on top of its already-created tables without first dropping the prior demonstration schema objects.

## Tests

Run from the project root after installing dependencies:

```powershell
python -m unittest discover -s tests -v
```

Tests exercise protected routes, password hashing, matching, profile preferences, discovery filters, private messaging, saved items, availability-slot scheduling, rescheduling approval, admin tools, request ownership, and review deduplication.

## Configuration and safety notes

- `.env` is for local values only and is excluded from version control; `.env.example` contains placeholders, not credentials.
- The administrator is created explicitly with `flask create-admin`; registration never accepts a role field.
- For a public deployment, use HTTPS, set `COOKIE_SECURE=1`, use a strong secret, apply database backups, and configure production server/error logging.
- The included `COOKIE_SECURE` option is off for localhost HTTP. Do not use debug mode on a public server.
- Demo profiles are not preloaded, so all visible student accounts are created by the person running the application.
