import csv
import io
import os
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Demonstration-only routes. Coordinates are sample data, not live tracking.
ROUTES = {
    "hyderabad_demo": {
        "name": "City Demo Route",
        "points": [
            (17.3850, 78.4867, 0), (17.3855, 78.4871, 18),
            (17.3860, 78.4875, 24), (17.3866, 78.4880, 29),
            (17.3870, 78.4885, 32), (17.3875, 78.4890, 36),
            (17.3880, 78.4890, 42), (17.3885, 78.4895, 45),
            (17.3890, 78.4900, 38), (17.3894, 78.4906, 27),
            (17.3898, 78.4910, 16), (17.3900, 78.4915, 0),
        ],
    },
    "campus_demo": {
        "name": "Campus Demo Route",
        "points": [
            (16.2350, 80.0500, 0), (16.2354, 80.0504, 12),
            (16.2358, 80.0509, 18), (16.2362, 80.0515, 22),
            (16.2367, 80.0520, 28), (16.2372, 80.0525, 35),
            (16.2378, 80.0530, 42), (16.2382, 80.0536, 30),
            (16.2387, 80.0540, 18), (16.2390, 80.0545, 0),
        ],
    },
}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=str(BASE_DIR / "gps_tracker.db"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    app.get_db = get_db

    def init_db():
        db = sqlite3.connect(app.config["DATABASE"])
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_code TEXT NOT NULL UNIQUE,
            device_name TEXT NOT NULL,
            device_type TEXT NOT NULL DEFAULT 'Vehicle',
            owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            route_key TEXT NOT NULL DEFAULT 'hyderabad_demo',
            status TEXT NOT NULL DEFAULT 'Inactive',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            start_time TEXT NOT NULL,
            end_time TEXT,
            status TEXT NOT NULL DEFAULT 'Running',
            current_index INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            simulation_id INTEGER NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            recorded_at TEXT NOT NULL,
            speed REAL NOT NULL DEFAULT 0,
            movement_status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            simulation_id INTEGER REFERENCES simulations(id) ON DELETE SET NULL,
            predicted_latitude REAL NOT NULL,
            predicted_longitude REAL NOT NULL,
            classification TEXT NOT NULL,
            prediction_time TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_locations_device_time ON locations(device_id, recorded_at);
        CREATE INDEX IF NOT EXISTS idx_simulations_owner ON simulations(owner_id, status);
        """)
        db.commit()
        db.close()

    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    app.teardown_appcontext(close_db)

    def csrf_token():
        if "_csrf_token" not in session:
            session["_csrf_token"] = secrets.token_urlsafe(32)
        return session["_csrf_token"]

    @app.context_processor
    def inject_globals():
        return {"csrf_token": csrf_token(), "current_user": session.get("user_name"),
                "current_role": session.get("user_role")}

    @app.before_request
    def protect_post_requests():
        if request.method == "POST":
            expected = session.get("_csrf_token", "")
            supplied = request.headers.get("X-CSRF-Token") or request.form.get("_csrf_token", "")
            if not expected or not supplied or not secrets.compare_digest(expected, supplied):
                if request.path.startswith("/api/") or request.is_json:
                    return jsonify(error="Your session expired. Refresh the page and try again."), 400
                flash("Your form session expired. Please try again.", "warning")
                return redirect(request.referrer or url_for("login"))

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                if request.path.startswith("/api/"):
                    return jsonify(error="Authentication required."), 401
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    def admin_required(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if session.get("user_role") != "admin":
                abort(403)
            return view(*args, **kwargs)
        return wrapped

    def payload():
        return request.get_json(silent=True) or request.form

    def owned_device(device_id):
        if session.get("user_role") == "admin":
            row = get_db().execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
        else:
            row = get_db().execute("SELECT * FROM devices WHERE id=? AND owner_id=?",
                                   (device_id, session["user_id"])).fetchone()
        return row

    def haversine_km(lat1, lon1, lat2, lon2):
        from math import asin, cos, radians, sin, sqrt
        radius = 6371.0088
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return 2 * radius * asin(sqrt(a))

    def movement_label(speed):
        if speed < 1:
            return "Stationary"
        if speed < 20:
            return "Slow Movement"
        if speed < 40:
            return "Moving"
        return "Fast Movement"

    def user_devices_query():
        if session.get("user_role") == "admin":
            return "SELECT d.*, u.full_name AS owner_name FROM devices d JOIN users u ON u.id=d.owner_id ORDER BY d.id", ()
        return "SELECT d.*, u.full_name AS owner_name FROM devices d JOIN users u ON u.id=d.owner_id WHERE d.owner_id=? ORDER BY d.id", (session["user_id"],)

    @app.get("/")
    def index():
        return redirect(url_for("dashboard" if session.get("user_id") else "login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if session.get("user_id"):
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            if len(name) < 2 or len(name) > 80:
                flash("Name must be between 2 and 80 characters.", "error")
            elif "@" not in email or len(email) > 120:
                flash("Enter a valid email address.", "error")
            elif len(password) < 8:
                flash("Password must contain at least 8 characters.", "error")
            elif password != confirm:
                flash("Passwords do not match.", "error")
            else:
                db = get_db()
                try:
                    cur = db.execute("INSERT INTO users(full_name,email,password_hash) VALUES(?,?,?)",
                                     (name, email, generate_password_hash(password)))
                    user_id = cur.lastrowid
                    db.execute("INSERT INTO devices(device_code,device_name,device_type,owner_id,route_key) VALUES(?,?,?,?,?)",
                               (f"D{user_id:03d}-01", "City Demo Vehicle", "Vehicle", user_id, "hyderabad_demo"))
                    db.execute("INSERT INTO devices(device_code,device_name,device_type,owner_id,route_key) VALUES(?,?,?,?,?)",
                               (f"D{user_id:03d}-02", "Campus Demo Tracker", "Tracker", user_id, "campus_demo"))
                    db.commit()
                    flash("Account created. Two sample simulation devices were added to your workspace.", "success")
                    return redirect(url_for("login"))
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("An account with that email already exists.", "error")
        return render_template("register.html", page_title="Create account")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("user_id"):
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not user or not check_password_hash(user["password_hash"], password):
                flash("Incorrect email or password.", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                session["user_name"] = user["full_name"]
                session["user_email"] = user["email"]
                session["user_role"] = user["role"]
                session["_csrf_token"] = secrets.token_urlsafe(32)
                return redirect(url_for("dashboard"))
        return render_template("login.html", page_title="Sign in")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("login"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        user = get_db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        return render_template("dashboard.html", page_title="Dashboard", user=user)

    @app.get("/history")
    @login_required
    def history():
        sql, args = user_devices_query()
        devices = get_db().execute(sql, args).fetchall()
        return render_template("history.html", page_title="Location history", devices=devices)

    @app.get("/reports")
    @login_required
    def reports():
        db = get_db()
        if session.get("user_role") == "admin":
            owner_clause, args = "", ()
        else:
            owner_clause, args = " WHERE owner_id=?", (session["user_id"],)
        devices = db.execute("SELECT COUNT(*) FROM devices" + owner_clause, args).fetchone()[0]
        sims = db.execute("SELECT COUNT(*) FROM simulations" + owner_clause, args).fetchone()[0]
        completed = db.execute("SELECT COUNT(*) FROM simulations" + owner_clause + (" AND" if owner_clause else " WHERE") + " status='Completed'", args).fetchone()[0]
        loc_sql = "SELECT COUNT(*) FROM locations l JOIN devices d ON d.id=l.device_id" + (" WHERE d.owner_id=?" if session.get("user_role") != "admin" else "")
        loc_count = db.execute(loc_sql, args if session.get("user_role") != "admin" else ()).fetchone()[0]
        return render_template("reports.html", page_title="Reports", stats={"devices": devices, "simulations": sims, "completed": completed, "locations": loc_count})

    @app.get("/admin")
    @admin_required
    def admin():
        db = get_db()
        users = db.execute("SELECT id,full_name,email,role,created_at FROM users ORDER BY id DESC").fetchall()
        devices = db.execute("SELECT d.*,u.full_name AS owner_name FROM devices d JOIN users u ON u.id=d.owner_id ORDER BY d.id DESC").fetchall()
        return render_template("admin.html", page_title="Administration", users=users, devices=devices)

    @app.post("/admin/users/<int:user_id>/role")
    @admin_required
    def update_user_role(user_id):
        new_role = request.form.get("role")
        if new_role not in ("user", "admin"):
            abort(400)
        db = get_db()
        target = db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        if not target:
            abort(404)
        admin_count = db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
        if target["role"] == "admin" and new_role == "user" and admin_count <= 1:
            flash("The last administrator cannot be demoted.", "error")
        elif user_id == session["user_id"] and new_role != "admin":
            flash("You cannot remove your own administrator role.", "error")
        else:
            db.execute("UPDATE users SET role=? WHERE id=?", (new_role, user_id))
            db.commit()
            flash("User role updated.", "success")
        return redirect(url_for("admin"))

    @app.post("/admin/devices")
    @admin_required
    def admin_create_device():
        data = request.form
        try:
            owner_id = int(data.get("owner_id", ""))
        except ValueError:
            abort(400)
        name = data.get("device_name", "").strip()
        device_type = data.get("device_type", "Vehicle")
        route_key = data.get("route_key", "hyderabad_demo")
        db = get_db()
        owner = db.execute("SELECT id FROM users WHERE id=?", (owner_id,)).fetchone()
        if not owner or not 2 <= len(name) <= 60 or device_type not in ("Vehicle", "Tracker") or route_key not in ROUTES:
            flash("Check the device name, owner, type and route.", "error")
            return redirect(url_for("admin"))
        count = db.execute("SELECT COUNT(*) FROM devices WHERE owner_id=?", (owner_id,)).fetchone()[0]
        code = f"D{owner_id:03d}-{count+1:02d}"
        while db.execute("SELECT 1 FROM devices WHERE device_code=?", (code,)).fetchone():
            count += 1
            code = f"D{owner_id:03d}-{count+1:02d}"
        db.execute("INSERT INTO devices(device_code,device_name,device_type,owner_id,route_key) VALUES(?,?,?,?,?)",
                   (code, name, device_type, owner_id, route_key))
        db.commit()
        flash("Simulation device added to the selected account.", "success")
        return redirect(url_for("admin"))

    @app.post("/admin/devices/<int:device_id>/delete")
    @admin_required
    def admin_delete_device(device_id):
        db = get_db()
        active = db.execute("SELECT 1 FROM simulations WHERE device_id=? AND status IN ('Running','Paused')", (device_id,)).fetchone()
        if active:
            flash("Stop or finish the active simulation before deleting this device.", "error")
        else:
            db.execute("DELETE FROM devices WHERE id=?", (device_id,))
            db.commit()
            flash("Device and its related demo records were deleted.", "success")
        return redirect(url_for("admin"))

    @app.get("/api/me")
    @login_required
    def api_me():
        return jsonify(name=session["user_name"], role=session["user_role"])

    @app.get("/api/devices")
    @login_required
    def api_devices():
        sql, args = user_devices_query()
        rows = get_db().execute(sql, args).fetchall()
        return jsonify(devices=[dict(row) for row in rows])

    @app.post("/api/devices")
    @login_required
    def api_create_device():
        data = payload()
        name = str(data.get("device_name", "")).strip()
        device_type = str(data.get("device_type", "Vehicle")).strip()
        route_key = str(data.get("route_key", "hyderabad_demo"))
        if not 2 <= len(name) <= 60:
            return jsonify(error="Device name must be 2–60 characters."), 400
        if device_type not in ("Vehicle", "Tracker") or route_key not in ROUTES:
            return jsonify(error="Choose a valid device type and demo route."), 400
        db = get_db()
        owner_id = session["user_id"]
        count = db.execute("SELECT COUNT(*) FROM devices WHERE owner_id=?", (owner_id,)).fetchone()[0]
        code = f"D{owner_id:03d}-{count+1:02d}"
        db.execute("INSERT INTO devices(device_code,device_name,device_type,owner_id,route_key) VALUES(?,?,?,?,?)",
                   (code, name, device_type, owner_id, route_key))
        db.commit()
        return jsonify(message="Device created.", device_code=code), 201

    @app.get("/api/locations")
    @login_required
    def api_locations():
        device_id = request.args.get("device_id", type=int)
        if not device_id or not owned_device(device_id):
            return jsonify(error="Device not found or access denied."), 404
        limit = min(max(request.args.get("limit", 500, type=int), 1), 2000)
        date_from = request.args.get("from", "").strip()
        date_to = request.args.get("to", "").strip()
        query = "SELECT l.*,s.status AS simulation_status FROM locations l JOIN simulations s ON s.id=l.simulation_id WHERE l.device_id=?"
        args = [device_id]
        if date_from:
            query += " AND date(l.recorded_at) >= date(?)"
            args.append(date_from)
        if date_to:
            query += " AND date(l.recorded_at) <= date(?)"
            args.append(date_to)
        query += " ORDER BY l.id DESC LIMIT ?"
        args.append(limit)
        rows = get_db().execute(query, args).fetchall()
        return jsonify(locations=[dict(row) for row in reversed(rows)])

    @app.post("/api/simulations/start")
    @login_required
    def api_start_simulation():
        data = payload()
        device_id = data.get("device_id", type=int) if hasattr(data, "get") and not isinstance(data, dict) else data.get("device_id")
        try:
            device_id = int(device_id)
        except (TypeError, ValueError):
            return jsonify(error="Select a device first."), 400
        device = owned_device(device_id)
        if not device:
            return jsonify(error="Device not found or access denied."), 404
        db = get_db()
        active = db.execute("SELECT id FROM simulations WHERE device_id=? AND status IN ('Running','Paused')", (device_id,)).fetchone()
        if active:
            return jsonify(error="This device already has an active simulation.", simulation_id=active["id"]), 409
        point = ROUTES[device["route_key"]]["points"][0]
        now = datetime.now().isoformat(timespec="seconds")
        cur = db.execute("INSERT INTO simulations(device_id,owner_id,start_time,status,current_index) VALUES(?,?,?,'Running',0)", (device_id, session["user_id"], now))
        sim_id = cur.lastrowid
        db.execute("INSERT INTO locations(device_id,simulation_id,latitude,longitude,recorded_at,speed,movement_status) VALUES(?,?,?,?,?,?,?)",
                   (device_id, sim_id, point[0], point[1], now, point[2], movement_label(point[2])))
        db.execute("UPDATE devices SET status='Active' WHERE id=?", (device_id,))
        db.commit()
        return jsonify(message="Simulation started.", simulation_id=sim_id, latitude=point[0], longitude=point[1], speed=point[2], movement_status=movement_label(point[2]))

    @app.post("/api/simulations/<int:simulation_id>/tick")
    @login_required
    def api_tick(simulation_id):
        db = get_db()
        sim = db.execute("SELECT s.*,d.route_key FROM simulations s JOIN devices d ON d.id=s.device_id WHERE s.id=?", (simulation_id,)).fetchone()
        if not sim or (session.get("user_role") != "admin" and sim["owner_id"] != session["user_id"]):
            return jsonify(error="Simulation not found or access denied."), 404
        if sim["status"] != "Running":
            return jsonify(error=f"Simulation is {sim['status'].lower()}.", status=sim["status"], completed=sim["status"] == "Completed"), 409
        route = ROUTES[sim["route_key"]]["points"]
        next_index = sim["current_index"] + 1
        now = datetime.now().isoformat(timespec="seconds")
        if next_index >= len(route):
            db.execute("UPDATE simulations SET status='Completed',end_time=? WHERE id=?", (now, simulation_id))
            db.execute("UPDATE devices SET status='Inactive' WHERE id=?", (sim["device_id"],))
            db.commit()
            return jsonify(message="Route completed.", status="Completed", completed=True)
        lat, lng, speed = route[next_index]
        is_final = next_index == len(route) - 1
        label = "Route Completed" if is_final else movement_label(speed)
        db.execute("UPDATE simulations SET current_index=?, status=?, end_time=? WHERE id=?",
                   (next_index, "Completed" if is_final else "Running", now if is_final else None, simulation_id))
        db.execute("INSERT INTO locations(device_id,simulation_id,latitude,longitude,recorded_at,speed,movement_status) VALUES(?,?,?,?,?,?,?)",
                   (sim["device_id"], simulation_id, lat, lng, now, speed, label))
        if is_final:
            db.execute("UPDATE devices SET status='Inactive' WHERE id=?", (sim["device_id"],))
        db.commit()
        return jsonify(latitude=lat, longitude=lng, speed=speed, movement_status=label,
                       index=next_index, total=len(route), completed=is_final,
                       status="Completed" if is_final else "Running")

    def change_simulation_state(simulation_id, target):
        db = get_db()
        sim = db.execute("SELECT * FROM simulations WHERE id=?", (simulation_id,)).fetchone()
        if not sim or (session.get("user_role") != "admin" and sim["owner_id"] != session["user_id"]):
            return jsonify(error="Simulation not found or access denied."), 404
        allowed = {"pause": ("Running", "Paused"), "resume": ("Paused", "Running"), "stop": (("Running", "Paused"), "Stopped")}
        old, new = allowed[target]
        if isinstance(old, tuple):
            valid = sim["status"] in old
        else:
            valid = sim["status"] == old
        if not valid:
            return jsonify(error=f"Cannot {target} a simulation that is {sim['status'].lower()}."), 409
        if target == "stop":
            now = datetime.now().isoformat(timespec="seconds")
            db.execute("UPDATE simulations SET status=?,end_time=? WHERE id=?", (new, now, simulation_id))
            db.execute("UPDATE devices SET status='Inactive' WHERE id=?", (sim["device_id"],))
        else:
            db.execute("UPDATE simulations SET status=? WHERE id=?", (new, simulation_id))
        db.commit()
        return jsonify(message=f"Simulation {new.lower()}.", status=new)

    @app.post("/api/simulations/<int:simulation_id>/pause")
    @login_required
    def api_pause(simulation_id):
        return change_simulation_state(simulation_id, "pause")

    @app.post("/api/simulations/<int:simulation_id>/resume")
    @login_required
    def api_resume(simulation_id):
        return change_simulation_state(simulation_id, "resume")

    @app.post("/api/simulations/<int:simulation_id>/stop")
    @login_required
    def api_stop(simulation_id):
        return change_simulation_state(simulation_id, "stop")

    @app.post("/api/distance")
    @login_required
    def api_distance():
        data = payload()
        try:
            lat1, lon1, lat2, lon2 = [float(data[k]) for k in ("lat1", "lon1", "lat2", "lon2")]
        except (KeyError, TypeError, ValueError):
            return jsonify(error="Enter all four coordinate values."), 400
        if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90 and -180 <= lon1 <= 180 and -180 <= lon2 <= 180):
            return jsonify(error="Coordinates are outside valid latitude/longitude ranges."), 400
        km = haversine_km(lat1, lon1, lat2, lon2)
        return jsonify(distance_km=round(km, 3), distance_m=round(km * 1000, 1))

    @app.post("/api/predict/<int:device_id>")
    @login_required
    def api_predict(device_id):
        device = owned_device(device_id)
        if not device:
            return jsonify(error="Device not found or access denied."), 404
        db = get_db()
        latest = db.execute("SELECT * FROM locations WHERE device_id=? ORDER BY id DESC LIMIT 2", (device_id,)).fetchall()
        if not latest:
            return jsonify(error="Start a simulation before requesting a prediction."), 400
        newest = latest[0]
        if len(latest) >= 2:
            previous = latest[1]
            pred_lat = newest["latitude"] + (newest["latitude"] - previous["latitude"])
            pred_lng = newest["longitude"] + (newest["longitude"] - previous["longitude"])
        else:
            points = ROUTES[device["route_key"]]["points"]
            next_idx = 1
            pred_lat, pred_lng = points[next_idx][0], points[next_idx][1]
        pred_lat = max(-90.0, min(90.0, pred_lat))
        pred_lng = max(-180.0, min(180.0, pred_lng))
        label = "Estimated next position"
        cur = db.execute("SELECT id FROM simulations WHERE device_id=? ORDER BY id DESC LIMIT 1", (device_id,)).fetchone()
        db.execute("INSERT INTO predictions(device_id,simulation_id,predicted_latitude,predicted_longitude,classification,prediction_time) VALUES(?,?,?,?,?,?)",
                   (device_id, cur["id"] if cur else None, pred_lat, pred_lng, label, datetime.now().isoformat(timespec="seconds")))
        db.commit()
        return jsonify(latitude=round(pred_lat, 6), longitude=round(pred_lng, 6), classification=label,
                       note="A simple straight-line extrapolation from recent simulated coordinates; not a real-world navigation forecast.")

    @app.get("/api/stats")
    @login_required
    def api_stats():
        db = get_db()
        if session.get("user_role") == "admin":
            owner_filter, args = "", ()
        else:
            owner_filter, args = " WHERE owner_id=?", (session["user_id"],)
        devices = db.execute("SELECT COUNT(*) FROM devices" + owner_filter, args).fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM devices" + (" WHERE status='Active'" + (" AND owner_id=?" if owner_filter else "") if True else ""), ((session["user_id"],) if owner_filter else ())).fetchone()[0]
        simulations = db.execute("SELECT COUNT(*) FROM simulations" + owner_filter, args).fetchone()[0]
        if owner_filter:
            locs = db.execute("SELECT COUNT(*) FROM locations l JOIN devices d ON d.id=l.device_id WHERE d.owner_id=?", args).fetchone()[0]
        else:
            locs = db.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
        return jsonify(devices=devices, active_devices=active, simulations=simulations, location_points=locs)

    @app.get("/reports/export.csv")
    @login_required
    def export_csv():
        db = get_db()
        query = "SELECT d.device_code,d.device_name,l.latitude,l.longitude,l.recorded_at,l.speed,l.movement_status FROM locations l JOIN devices d ON d.id=l.device_id"
        args = ()
        if session.get("user_role") != "admin":
            query += " WHERE d.owner_id=?"
            args = (session["user_id"],)
        query += " ORDER BY l.recorded_at DESC"
        rows = db.execute(query, args).fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["device_code", "device_name", "latitude", "longitude", "recorded_at", "simulated_speed_kmh", "movement_status"])
        for row in rows:
            writer.writerow(list(row))
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=gps_simulation_report.csv"})

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", page_title="Access denied", code=403,
                               message="You do not have permission to access this page."), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", page_title="Not found", code=404,
                               message="The page or resource could not be found."), 404

    @app.cli.command("create-admin")
    def create_admin_command():
        """Create an administrator account interactively."""
        import click
        name = click.prompt("Administrator name")
        email = click.prompt("Administrator email").strip().lower()
        password = click.prompt("Password (minimum 8 characters)", hide_input=True, confirmation_prompt=True)
        if len(password) < 8:
            raise click.ClickException("Password must contain at least 8 characters.")
        db = get_db()
        try:
            cur = db.execute("INSERT INTO users(full_name,email,password_hash,role) VALUES(?,?,?,'admin')",
                             (name.strip(), email, generate_password_hash(password)))
            uid = cur.lastrowid
            db.execute("INSERT INTO devices(device_code,device_name,device_type,owner_id,route_key) VALUES(?,?,?,?,?)",
                       (f"D{uid:03d}-01", "Admin Demo Vehicle", "Vehicle", uid, "hyderabad_demo"))
            db.commit()
            click.echo("Administrator account created. Sign in through the application.")
        except sqlite3.IntegrityError:
            db.rollback()
            raise click.ClickException("That email address is already registered.")

    with app.app_context():
        init_db()
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("FLASK_DEBUG", "1") == "1")
