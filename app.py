"""
GlobeTrotter Travel Assistant — Phase 1: The Monolith
CS 4122 — Distributed Systems (Engr. Daniel Moune, ICT-U)

A single Flask process handling ALL requests, backed by a single JSON file
(data/db.json). No database, no service separation, no horizontal scaling.
This is intentional: Phase 1 exists to let us FEEL the limitations of a
monolithic, file-backed architecture before we decompose it in Phase 2.

Destinations are seeded with real Cameroonian towns (Yaoundé, Douala,
Limbe, Kribi, Bamenda, Buea, etc.) so the recommendation logic has
something meaningful to reason about.

Run:
    python app.py
Test:
    pytest test_app.py -v
"""

import json
import os
import uuid
import datetime
import threading

import jwt
from flask import Flask, request, jsonify, render_template
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "db.json")
JWT_SECRET = os.environ.get("GLOBETROTTER_SECRET", "dev-secret-change-me")
JWT_ALGO = "HS256"
JWT_EXP_HOURS = 12

# templates/ holds the Jinja pages, static/ holds js/css. Both are served by
# THIS SAME Flask process that serves the JSON API — one origin, no CORS
# setup needed. That's another thing Phase 1 gets to skip that a decoupled
# frontend (Phase 2/3, served from its own host) would require.
app = Flask(__name__)

# A single process-wide lock. This is the crudest possible way to protect a
# JSON file from concurrent writes — and that's the point. It works for one
# process on one machine. It is USELESS the moment we run two instances of
# this app behind a load balancer (Phase 3), because each process would have
# its own lock and both could still corrupt the file. That is exactly the
# "Data Storage" challenge the course slides call out.
_db_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Data Access Layer ("Data Access" box in the architecture diagram)
# ---------------------------------------------------------------------------
def read_db():
    with _db_lock:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)


def write_db(data):
    with _db_lock:
        tmp_path = DB_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, DB_PATH)  # atomic-ish swap on POSIX


def find_user(db, username):
    return next((u for u in db["users"] if u["username"] == username), None)


def find_user_by_id(db, user_id):
    return next((u for u in db["users"] if u["id"] == user_id), None)


# ---------------------------------------------------------------------------
# Auth helpers ("Authentication" box in the architecture diagram)
# ---------------------------------------------------------------------------
def generate_token(user_id, username):
    payload = {
        "sub": user_id,
        "username": username,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=JWT_EXP_HOURS),
        "iat": datetime.datetime.now(datetime.timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_auth(f):
    """Decorator: reject the request unless a valid Bearer token is present."""
    from functools import wraps

    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or malformed Authorization header"}), 401
        token = auth_header.split(" ", 1)[1]
        payload = decode_token(token)
        if payload is None:
            return jsonify({"error": "Invalid or expired token"}), 401
        request.user_id = payload["sub"]
        request.username = payload["username"]
        return f(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Business Logic Layer ("Business Logic" box in the architecture diagram)
# ---------------------------------------------------------------------------
def score_destination(dest, user):
    """
    Very simple recommendation scoring:
      +3  for each tag overlap with the user's stated preferences
      +2  for each tag overlap with tags from the user's PAST itineraries
      +popularity / 20  as a general tie-breaker (popular places rank higher)
    This is intentionally simple for Phase 1 — a single function inside a
    single process. In Phase 4 this is exactly the kind of logic that
    benefits from caching, because recomputing it per-request over millions
    of users is expensive.
    """
    prefs = set(user.get("preferences", []))
    score = sum(3 for tag in dest["tags"] if tag in prefs)

    past_tags = set()
    for it in user.get("_past_tags", []):
        past_tags.add(it)
    score += sum(2 for tag in dest["tags"] if tag in past_tags)

    score += dest["popularity"] / 20.0
    return score


def get_user_past_tags(db, user_id):
    """Collect tags from destinations the user has already booked itineraries to."""
    dest_by_id = {d["id"]: d for d in db["destinations"]}
    tags = []
    for it in db["itineraries"]:
        if it["user_id"] == user_id:
            dest = dest_by_id.get(it["destination_id"])
            if dest:
                tags.extend(dest["tags"])
    return tags


# ---------------------------------------------------------------------------
# API Layer ("API" box in the architecture diagram) — the 6 required endpoints
# ---------------------------------------------------------------------------
@app.route("/register", methods=["POST"])
def register():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    preferences = body.get("preferences", [])

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400
    if not isinstance(preferences, list):
        return jsonify({"error": "preferences must be a list of tags, e.g. ['beach', 'nature']"}), 400

    db = read_db()
    if find_user(db, username):
        return jsonify({"error": "username already taken"}), 409

    user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": generate_password_hash(password),
        "preferences": preferences,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    db["users"].append(user)
    write_db(db)

    return jsonify({
        "message": "user registered",
        "user": {"id": user["id"], "username": user["username"], "preferences": user["preferences"]}
    }), 201


@app.route("/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    db = read_db()
    user = find_user(db, username)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "invalid username or password"}), 401

    token = generate_token(user["id"], user["username"])
    return jsonify({"token": token, "expires_in_hours": JWT_EXP_HOURS}), 200


@app.route("/destinations", methods=["GET"])
def get_destinations():
    """
    Search Cameroonian destinations.
    Query params (all optional, combinable):
      q       - free text match against name/description
      region  - exact region match, e.g. Littoral, Southwest, West
      tag     - filter by a single tag, e.g. beach, hiking, culture
    """
    db = read_db()
    results = db["destinations"]

    q = request.args.get("q", "").strip().lower()
    region = request.args.get("region", "").strip().lower()
    tag = request.args.get("tag", "").strip().lower()

    if q:
        results = [d for d in results if q in d["name"].lower() or q in d["description"].lower()]
    if region:
        results = [d for d in results if d["region"].lower() == region]
    if tag:
        results = [d for d in results if tag in [t.lower() for t in d["tags"]]]

    results = sorted(results, key=lambda d: d["popularity"], reverse=True)
    return jsonify({"count": len(results), "destinations": results}), 200


@app.route("/recommendations", methods=["GET"])
@require_auth
def get_recommendations():
    """Personalized recommendations based on stated preferences + past itineraries."""
    db = read_db()
    user = find_user_by_id(db, request.user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    user_view = dict(user)
    user_view["_past_tags"] = get_user_past_tags(db, user["id"])

    visited_ids = {it["destination_id"] for it in db["itineraries"] if it["user_id"] == user["id"]}
    candidates = [d for d in db["destinations"] if d["id"] not in visited_ids]

    scored = [(score_destination(d, user_view), d) for d in candidates]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    limit = int(request.args.get("limit", 5))
    top = [{"score": round(s, 2), **d} for s, d in scored[:limit]]

    return jsonify({
        "based_on_preferences": user.get("preferences", []),
        "based_on_past_trips": sorted(set(user_view["_past_tags"])),
        "recommendations": top
    }), 200


@app.route("/itineraries", methods=["POST"])
@require_auth
def create_itinerary():
    body = request.get_json(silent=True) or {}
    destination_id = body.get("destination_id")
    start_date = body.get("start_date")
    end_date = body.get("end_date")
    notes = body.get("notes", "")

    if not destination_id or not start_date or not end_date:
        return jsonify({"error": "destination_id, start_date, and end_date are required"}), 400

    db = read_db()
    dest = next((d for d in db["destinations"] if d["id"] == destination_id), None)
    if not dest:
        return jsonify({"error": f"unknown destination_id '{destination_id}'"}), 404

    itinerary = {
        "id": str(uuid.uuid4()),
        "user_id": request.user_id,
        "destination_id": destination_id,
        "destination_name": dest["name"],
        "start_date": start_date,
        "end_date": end_date,
        "notes": notes,
        "shared_with": [],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    db["itineraries"].append(itinerary)
    write_db(db)

    return jsonify({"message": "itinerary created", "itinerary": itinerary}), 201


@app.route("/itineraries", methods=["GET"])
@require_auth
def get_itineraries():
    db = read_db()
    mine = [it for it in db["itineraries"] if it["user_id"] == request.user_id]
    mine.sort(key=lambda it: it["start_date"])
    return jsonify({"count": len(mine), "itineraries": mine}), 200


# ---------------------------------------------------------------------------
# Bonus endpoint (not in the required 6, but needed for "share with friends"
# business requirement) — kept intentionally tiny for Phase 1.
# ---------------------------------------------------------------------------
@app.route("/itineraries/<itinerary_id>/share", methods=["POST"])
@require_auth
def share_itinerary(itinerary_id):
    body = request.get_json(silent=True) or {}
    share_with_username = (body.get("username") or "").strip()
    if not share_with_username:
        return jsonify({"error": "username is required"}), 400

    db = read_db()
    itinerary = next((it for it in db["itineraries"] if it["id"] == itinerary_id), None)
    if not itinerary or itinerary["user_id"] != request.user_id:
        return jsonify({"error": "itinerary not found"}), 404

    target = find_user(db, share_with_username)
    if not target:
        return jsonify({"error": f"no such user '{share_with_username}'"}), 404

    if share_with_username not in itinerary["shared_with"]:
        itinerary["shared_with"].append(share_with_username)
        write_db(db)

    return jsonify({"message": f"itinerary shared with {share_with_username}", "itinerary": itinerary}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "architecture": "monolith", "phase": 1}), 200


# ---------------------------------------------------------------------------
# Frontend — server-rendered pages, live in the SAME process as the API.
# These pages call the JSON endpoints above via same-origin fetch() (see
# static/js/main.js). Page routes are namespaced under /app/... where they'd
# otherwise collide with a JSON endpoint of the same name (e.g. GET
# /destinations already returns JSON, so the page lives at /app/destinations).
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def page_home():
    return render_template("index.html")


@app.route("/login", methods=["GET"])
def page_login():
    return render_template("login.html")


@app.route("/register", methods=["GET"])
def page_register():
    return render_template("register.html")


@app.route("/app/destinations", methods=["GET"])
def page_destinations():
    return render_template("destinations.html")


@app.route("/app/recommendations", methods=["GET"])
def page_recommendations():
    return render_template("recommendations.html")


@app.route("/app/itineraries", methods=["GET"])
def page_itineraries():
    return render_template("itineraries.html")


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
