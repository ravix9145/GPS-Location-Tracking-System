import re
import tempfile
import unittest
from pathlib import Path

from app import create_app


class GPSTrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = str(Path(self.temp_dir.name) / "test.db")
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-secret-key", "DATABASE": db_path})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def csrf_from(self, response):
        match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', response.data)
        self.assertIsNotNone(match, "CSRF meta token should be present")
        return match.group(1).decode()

    def register_and_login(self):
        page = self.client.get("/register")
        token = self.csrf_from(page)
        response = self.client.post("/register", data={
            "_csrf_token": token,
            "full_name": "Test User",
            "email": "test@example.com",
            "password": "safe-password-123",
            "confirm_password": "safe-password-123",
        }, follow_redirects=True)
        self.assertIn(b"Account created", response.data)
        login_page = self.client.get("/login")
        token = self.csrf_from(login_page)
        response = self.client.post("/login", data={
            "_csrf_token": token,
            "email": "test@example.com",
            "password": "safe-password-123",
        }, follow_redirects=True)
        self.assertIn(b"Welcome", response.data)
        return self.csrf_from(response)

    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)

    def test_register_login_and_seed_devices(self):
        self.register_and_login()
        response = self.client.get("/api/devices")
        self.assertEqual(response.status_code, 200)
        devices = response.get_json()["devices"]
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0]["device_type"], "Vehicle")

    def test_duplicate_email_is_rejected(self):
        page = self.client.get("/register")
        token = self.csrf_from(page)
        data = {"_csrf_token": token, "full_name": "Test User", "email": "dup@example.com",
                "password": "safe-password-123", "confirm_password": "safe-password-123"}
        self.client.post("/register", data=data)
        page = self.client.get("/register")
        data["_csrf_token"] = self.csrf_from(page)
        response = self.client.post("/register", data=data, follow_redirects=True)
        self.assertIn(b"already exists", response.data)

    def test_distance_endpoint(self):
        self.register_and_login()
        response = self.client.post("/api/distance", json={"lat1": 17.3850, "lon1": 78.4867,
                                                            "lat2": 17.3860, "lon2": 78.4875},
                                    headers={"X-CSRF-Token": self.csrf_from(self.client.get("/dashboard"))})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.get_json()["distance_km"], 0)

    def test_complete_simulation_persists_location_history(self):
        self.register_and_login()
        token = self.csrf_from(self.client.get("/dashboard"))
        devices = self.client.get("/api/devices").get_json()["devices"]
        device_id = devices[0]["id"]
        started = self.client.post("/api/simulations/start", json={"device_id": device_id},
                                   headers={"X-CSRF-Token": token})
        self.assertEqual(started.status_code, 200)
        sim_id = started.get_json()["simulation_id"]
        last = None
        for _ in range(15):
            tick = self.client.post(f"/api/simulations/{sim_id}/tick", json={},
                                    headers={"X-CSRF-Token": token})
            if tick.status_code == 409:
                break
            self.assertEqual(tick.status_code, 200)
            last = tick.get_json()
            if last.get("completed"):
                break
        self.assertTrue(last["completed"])
        self.assertEqual(last["status"], "Completed")
        history = self.client.get(f"/api/locations?device_id={device_id}")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.get_json()["locations"]), 12)

    def test_user_cannot_access_other_users_device(self):
        self.register_and_login()
        token = self.csrf_from(self.client.get("/dashboard"))
        first_device_id = self.client.get("/api/devices").get_json()["devices"][0]["id"]
        # Create a second account through a clean browser session, then return to the first account.
        self.client.post("/logout", data={"_csrf_token": token})
        page = self.client.get("/register")
        new_token = self.csrf_from(page)
        self.client.post("/register", data={"_csrf_token": new_token, "full_name": "Other User",
                                            "email": "other@example.com", "password": "other-password-123",
                                            "confirm_password": "other-password-123"})
        page = self.client.get("/login")
        new_token = self.csrf_from(page)
        self.client.post("/login", data={"_csrf_token": new_token, "email": "other@example.com",
                                         "password": "other-password-123"})
        response = self.client.get(f"/api/locations?device_id={first_device_id}")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
