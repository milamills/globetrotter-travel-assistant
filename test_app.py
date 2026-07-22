"""
Test suite for the GlobeTrotter Phase 1 Monolith.
Run with: pytest test_app.py -v

Each test resets the JSON "database" to a known seed state first, since a
monolith backed by a shared file has no per-test isolation for free — another
one of the Phase 1 "gotchas" worth noticing.
"""
import json
import os
import shutil
import pytest

import app as globetrotter_app

DB_PATH = globetrotter_app.DB_PATH
SEED_PATH = os.path.join(os.path.dirname(DB_PATH), "db_seed_backup.json")


@pytest.fixture(autouse=True)
def reset_db():
    # Back up the real seed once, then always restore a clean copy before each test.
    if not os.path.exists(SEED_PATH):
        shutil.copy(DB_PATH, SEED_PATH)
    shutil.copy(SEED_PATH, DB_PATH)
    yield
    shutil.copy(SEED_PATH, DB_PATH)


@pytest.fixture
def client():
    globetrotter_app.app.config["TESTING"] = True
    with globetrotter_app.app.test_client() as c:
        yield c


def register_and_login(client, username="fonkeng", password="s3cret", preferences=None):
    client.post("/register", json={
        "username": username, "password": password,
        "preferences": preferences or ["beach", "nature"]
    })
    resp = client.post("/login", json={"username": username, "password": password})
    return resp.get_json()["token"]


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["architecture"] == "monolith"


def test_register_new_user(client):
    resp = client.post("/register", json={
        "username": "endora", "password": "pw12345", "preferences": ["hiking", "culture"]
    })
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["user"]["username"] == "endora"


def test_register_duplicate_username_rejected(client):
    client.post("/register", json={"username": "dupe", "password": "pw"})
    resp = client.post("/register", json={"username": "dupe", "password": "pw2"})
    assert resp.status_code == 409


def test_register_missing_fields(client):
    resp = client.post("/register", json={"username": "onlyname"})
    assert resp.status_code == 400


def test_login_success(client):
    client.post("/register", json={"username": "u1", "password": "pw"})
    resp = client.post("/login", json={"username": "u1", "password": "pw"})
    assert resp.status_code == 200
    assert "token" in resp.get_json()


def test_login_wrong_password(client):
    client.post("/register", json={"username": "u2", "password": "correct"})
    resp = client.post("/login", json={"username": "u2", "password": "wrong"})
    assert resp.status_code == 401


def test_get_destinations_all(client):
    resp = client.get("/destinations")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["count"] == 15
    names = [d["name"] for d in body["destinations"]]
    assert "Douala" in names and "Kribi" in names


def test_get_destinations_filter_by_region(client):
    resp = client.get("/destinations?region=Southwest")
    body = resp.get_json()
    names = {d["name"] for d in body["destinations"]}
    assert names == {"Limbe", "Buea"}


def test_get_destinations_filter_by_tag(client):
    resp = client.get("/destinations?tag=beach")
    body = resp.get_json()
    names = {d["name"] for d in body["destinations"]}
    assert "Kribi" in names and "Limbe" in names


def test_get_destinations_search_query(client):
    resp = client.get("/destinations?q=Mount Cameroon")
    body = resp.get_json()
    names = {d["name"] for d in body["destinations"]}
    assert "Buea" in names


def test_recommendations_requires_auth(client):
    resp = client.get("/recommendations")
    assert resp.status_code == 401


def test_recommendations_matches_preferences(client):
    token = register_and_login(client, "beachlover", preferences=["beach", "relaxation"])
    resp = client.get("/recommendations", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    top_names = [d["name"] for d in resp.get_json()["recommendations"]]
    # Kribi is tagged beach + relaxation, should rank highly
    assert "Kribi" in top_names


def test_create_itinerary_requires_auth(client):
    resp = client.post("/itineraries", json={"destination_id": "dst004"})
    assert resp.status_code == 401


def test_create_itinerary_success(client):
    token = register_and_login(client)
    resp = client.post("/itineraries", headers={"Authorization": f"Bearer {token}"}, json={
        "destination_id": "dst004", "start_date": "2026-08-01", "end_date": "2026-08-05",
        "notes": "Family trip to Kribi"
    })
    assert resp.status_code == 201
    body = resp.get_json()["itinerary"]
    assert body["destination_name"] == "Kribi"


def test_create_itinerary_unknown_destination(client):
    token = register_and_login(client)
    resp = client.post("/itineraries", headers={"Authorization": f"Bearer {token}"}, json={
        "destination_id": "does-not-exist", "start_date": "2026-08-01", "end_date": "2026-08-05"
    })
    assert resp.status_code == 404


def test_get_itineraries_returns_only_mine(client):
    token1 = register_and_login(client, "userA")
    token2 = register_and_login(client, "userB")

    client.post("/itineraries", headers={"Authorization": f"Bearer {token1}"}, json={
        "destination_id": "dst001", "start_date": "2026-09-01", "end_date": "2026-09-03"
    })
    client.post("/itineraries", headers={"Authorization": f"Bearer {token2}"}, json={
        "destination_id": "dst002", "start_date": "2026-09-10", "end_date": "2026-09-12"
    })

    resp = client.get("/itineraries", headers={"Authorization": f"Bearer {token1}"})
    body = resp.get_json()
    assert body["count"] == 1
    assert body["itineraries"][0]["destination_name"] == "Yaoundé"


def test_share_itinerary(client):
    token1 = register_and_login(client, "sharer")
    register_and_login(client, "receiver")

    create_resp = client.post("/itineraries", headers={"Authorization": f"Bearer {token1}"}, json={
        "destination_id": "dst003", "start_date": "2026-10-01", "end_date": "2026-10-04"
    })
    itin_id = create_resp.get_json()["itinerary"]["id"]

    resp = client.post(f"/itineraries/{itin_id}/share",
                        headers={"Authorization": f"Bearer {token1}"},
                        json={"username": "receiver"})
    assert resp.status_code == 200
    assert "receiver" in resp.get_json()["itinerary"]["shared_with"]


def test_recommendations_excludes_already_booked(client):
    token = register_and_login(client, "repeatvisitor", preferences=["beach"])
    client.post("/itineraries", headers={"Authorization": f"Bearer {token}"}, json={
        "destination_id": "dst004", "start_date": "2026-08-01", "end_date": "2026-08-05"
    })
    resp = client.get("/recommendations", headers={"Authorization": f"Bearer {token}"})
    names = [d["name"] for d in resp.get_json()["recommendations"]]
    assert "Kribi" not in names
