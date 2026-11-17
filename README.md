# GPS Location Tracking Simulation System — Full Application

A full-stack Software Engineering project based on the submitted project specification. It uses **Python Flask + SQLite + HTML/CSS/JavaScript + Leaflet/OpenStreetMap**.

The application uses sample, simulated GPS coordinates only. It does not secretly track real people or physical devices.

## Implemented modules

- User registration, login and logout; password hashes, server-side sessions and CSRF checks for POST requests.
- User/admin roles, protected admin console and interactive role management.
- SQLite persistence for users, devices, simulation sessions, location records and predictions.
- Per-account demo device creation and additional device registration.
- Start, pause, resume and stop simulated routes; automatic coordinate updates from predefined sample paths.
- Leaflet map with current marker, route line and predicted marker; OpenStreetMap tiles.
- Location history with device and date filters, plus CSV export.
- Haversine distance calculator.
- Simple straight-line next-coordinate extrapolation and movement labels.
- Reports, statistics, movement classification rules and responsive dark/light themes.

## Requirements

- Windows 10/11
- Python 3.10 or later
- Visual Studio Code
- Internet connection for external fonts, Leaflet library and OpenStreetMap map tiles. The Flask application and SQLite data run locally.

## Quick start (Windows PowerShell)

For an easier launch, you can double-click `start.bat`; it creates the virtual environment if needed, installs dependencies and starts the local server. The first run needs internet access to install Python packages.

1. Extract this ZIP.
2. Open the extracted `GPS_Location_Tracking_System_Full` folder in VS Code.
3. Open **Terminal → New Terminal** and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this in the current terminal only, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Install the packages:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create a persistent local secret key (optional for a quick demo, recommended):

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the generated value into `.env` as the value of `SECRET_KEY=`. Do not share or commit `.env`.

Start the application:

```powershell
python app.py
```

Open **http://127.0.0.1:5000** in your browser. Register a normal user account. Two sample devices are automatically created for each new account.

Stop the local server with `Ctrl+C` in the terminal. When you return later, open the project folder, activate `.venv`, and run `python app.py` again.

## Administrator account

There is intentionally no hard-coded default administrator password. Create an admin account from the VS Code terminal:

```powershell
flask --app app create-admin
```

Enter an administrator name, email and password when prompted. Then sign in using that account. The admin menu will appear in the top navigation. Do not use a weak or shared password.

## How to demonstrate the application

1. Register and sign in. Show the user dashboard and both theme modes.
2. Choose `City Demo Vehicle` or `Campus Demo Tracker`.
3. Click **Start simulation**. The marker moves along sample points automatically; pause, resume and stop are available.
4. Watch latitude, longitude, simulated speed, movement classification and route progress update.
5. Click **Estimate next position** to demonstrate the basic prediction logic.
6. Open **History**, choose the device, optionally filter dates, and load the saved GPS records.
7. Open **Reports** and calculate distance between two coordinates. Export the location history as CSV.
8. Create/sign in as an admin to show user roles and the admin console.

## Project structure

```text
GPS_Location_Tracking_System_Full/
├── app.py
├── requirements.txt
├── start.bat
├── .env.example
├── .gitignore
├── README.md
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── history.html
│   ├── reports.html
│   ├── admin.html
│   └── error.html
├── static/
│   ├── css/style.css
│   └── js/
│       ├── app.js
│       ├── dashboard.js
│       ├── history.js
│       └── reports.js
└── tests/test_app.py
```

The `gps_tracker.db` file is generated automatically in the project folder on first run. Keep it if you want to retain registered accounts and simulation history. Delete it only when you intentionally want to reset the local demo database.

## Test suite

Install dependencies first, then run:

```powershell
python -m unittest discover -s tests -v
```

The tests use a temporary SQLite database and do not modify your normal demo database.

## Design and implementation notes

- Simulation route points and the example GPS dataset are deliberately sample coordinates. `17.3850, 78.4867` is included from the submitted project document; a second illustrative campus route is included to make the demonstration more useful.
- Simulated speeds are scenario values, not measured vehicle speed.
- Movement labels use these example rules: Stationary below 1 km/h; Slow Movement from 1 to below 20; Moving from 20 to below 40; Fast Movement at 40 or above; Route Completed at the final sample point.
- The prediction is a basic straight-line extrapolation from the last two stored coordinates. It is not a trained ML model or a guarantee of a future physical position.
- Distance uses the Haversine great-circle calculation.
- Leaflet and OpenStreetMap require internet access for map library/tiles. If the map area is blank, verify internet access; the API, authentication and database can still run locally.
- This is a student/demo application. Before public deployment, add production-grade rate limiting, HTTPS, stronger operational controls, database backups, logging, security review and a production WSGI server. Do not run Flask's debug server on the public internet.

## Scope coverage from the project report

| Report requirement | Implemented location |
|---|---|
| Registration, login and logout | `/register`, `/login`, `/logout` |
| GPS sample data and simulated movement | Dashboard simulation controls and `/api/simulations/*` |
| Map display and route | Leaflet on Dashboard |
| Location history | `/history` and `/api/locations` |
| Distance calculation | Reports page and `/api/distance` |
| Movement classification | Simulation engine and Reports page |
| Basic prediction | Dashboard and `/api/predict/<device_id>` |
| Admin dashboard | `/admin` (admin role only) |
| Database records | SQLite tables: users, devices, simulations, locations, predictions |
| Reports | `/reports` and CSV export |
