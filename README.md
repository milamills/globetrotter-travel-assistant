![Kamer Trails](branding/kamer-trails-lockup.png)

# GlobeTrotter Travel Assistant — Phase 1: The Monolith
*(brand identity: "Kamer Trails")*

**Course:** CS 4122 — Distributed Systems (Engr. Daniel Moune, ICT-U)
**Deliverable:** Phase 1 — a working monolithic API with at least 5 endpoints, deployed on a single server,
now with a full website on top of it.

This implementation targets **Cameroonian destinations** end to end — Yaoundé, Douala, Limbe, Kribi,
Bamenda, Buea, Dschang, Bafoussam, Garoua, Maroua, Ngaoundéré, Ebolowa, Foumban, Bertoua — so every
functionality (search, recommendations, itineraries, sharing) operates on real, locally meaningful data.

## 1. Architecture (matches the slide diagram exactly)

```
        Browser
          │
          ▼
    ┌───────────┐
    │    API    │   ← Flask routes: JSON endpoints + server-rendered pages, same process
    └─────┬─────┘
          ▼
    ┌───────────┐
    │ Business  │   ← recommendation scoring, itinerary rules
    │  Logic    │
    └─────┬─────┘
          ▼
    ┌───────────┐
    │   Data    │   ← reads/writes a single JSON file (data/db.json)
    │  Access   │
    └───────────┘
```

One Python process serves the API **and** the website. No database, no separate frontend server, no
CORS configuration needed — everything is same-origin. That's deliberate: Phase 1 exists so you feel
the walls of this design (and notice how much it lets you skip) before Phase 2 breaks it apart.

## 2. Tech stack used

| Slide requirement | What this project uses |
|---|---|
| Backend: Python (Flask/FastAPI) or Node (Express) | **Flask**, with Jinja2 templates for pages |
| Data: JSON file storage | `data/db.json` (users, destinations, itineraries) |
| Testing: pytest or Jest | **pytest** — 18 tests, all passing |
| Version control | Git (run `git init` before submitting) |
| Authentication | JWT (`PyJWT`), passwords hashed with Werkzeug's `generate_password_hash` |
| Frontend | Server-rendered HTML (Jinja) + vanilla JS calling the JSON API via `fetch()`, styled with hand-written CSS variables (no framework, no build step) |

## 3. The 6 required API endpoints (all implemented)

| Method | Path | Auth? | Purpose |
|---|---|---|---|
| POST | `/register` | No | Register a user with a username, password, and travel preference tags |
| POST | `/login` | No | Authenticate, returns a JWT valid for 12 hours |
| GET | `/destinations` | No | Search Cameroonian destinations by `q`, `region`, or `tag` |
| GET | `/recommendations` | **Yes** | Personalized picks based on preferences + past itineraries |
| POST | `/itineraries` | **Yes** | Create a new itinerary against a destination |
| GET | `/itineraries` | **Yes** | List the logged-in user's itineraries |

**Bonus:** `POST /itineraries/<id>/share` (needed for the "share with friends" business requirement).

## 4. Destinations seed data

15 real Cameroonian towns are seeded in `data/db.json`, each tagged by activity (`beach`, `hiking`,
`culture`, `nightlife`, `wildlife`, `nature`, `history`, etc.) and given a popularity score — so the
recommendation engine has something meaningful to reason about. Someone who prefers `beach` +
`relaxation` gets Kribi and Limbe ranked highly; someone who prefers `hiking` gets Buea, Bamenda,
and Dschang.

## 5. Recommendation logic (Business Logic layer)

```
score = 3 × (tags matching stated preferences)
      + 2 × (tags matching destinations from past itineraries)
      + popularity ÷ 20
```

Already-booked destinations are excluded from future recommendations. This is intentionally simple,
synchronous, in-process logic — recomputing it per request over millions of users is exactly the cost
that motivates the **caching** you'll add in Phase 4.

## 6. The website

A full multi-page site, served by the **same Flask process** as the API — one deployment unit, no
separate frontend server, exactly in keeping with "monolith."

| Page | Route | Auth? | What it does |
|---|---|---|---|
| Home | `/` | No | Hero + top 3 popular destinations, pulled live from `/destinations` |
| Log in | `/login` | No | Posts to `/login`, stores the JWT, redirects back to where you came from |
| Sign up | `/register` | No | Tag-picker for preferences, posts to `/register`, then auto-logs in |
| Destinations | `/app/destinations` | No (booking requires login) | Live search/filter against `/destinations`; "Plan a trip here" opens a modal that posts to `/itineraries` |
| Recommendations | `/app/recommendations` | **Yes** | Calls `/recommendations`, shows a match score per destination |
| My Trips | `/app/itineraries` | **Yes** | Calls `/itineraries`, renders a route-line timeline; share button posts to `/itineraries/<id>/share` |

Page routes live under `/app/...` where they'd otherwise collide with a same-named JSON endpoint
(e.g. `GET /destinations` already returns JSON, so the page is `/app/destinations`).

**Design:** ivory background (`#FAFAF9`), forest-green primary (`#0F6B4C`), savanna-gold accent
(`#D9A441`), *Space Grotesk* for headings + *Inter* for body text. The signature visual device is
functional, not decorative: every destination card has a left-edge stripe colored by its Cameroon
region (10 regions → 10 hues, see `regionColor()` in `static/js/main.js`), and My Trips renders
itineraries as a dotted vertical route line — a visual echo of an actual travel route.

**Client-side auth:** `static/js/main.js` stores the JWT in `localStorage` after login/register and
attaches it as `Authorization: Bearer <token>` on calls to auth-gated endpoints. `GT.requireAuth()`
bounces visitors without a token from `/app/recommendations` or `/app/itineraries` to
`/login?next=...` and returns them there after signing in.

## 7. Running the whole thing

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000 — frontend and API together, one process, one port.
```

Or exercise the API directly:
```bash
curl -X POST http://localhost:5000/register -H "Content-Type: application/json" \
  -d '{"username":"fonkeng","password":"pass123","preferences":["beach","hiking"]}'

curl -X POST http://localhost:5000/login -H "Content-Type: application/json" \
  -d '{"username":"fonkeng","password":"pass123"}'
# copy the token, then:

curl http://localhost:5000/recommendations -H "Authorization: Bearer <TOKEN>"
```

## 8. Testing

```bash
pytest test_app.py -v
```
18 tests covering registration, duplicate-username rejection, login failure, destination search/filter,
auth-gated recommendations, itinerary creation against invalid destinations, per-user itinerary
isolation, and sharing. (Backend/API tests only — the pages are exercised manually via the routes above.)

## 9. Challenges experienced first-hand (per the slide's "Challenges of the Monolith" table)

- **Scalability** — the app only scales vertically; running two instances isn't safe because of point 2.
- **Data storage / concurrency** — `data/db.json` is protected only by an in-process `threading.Lock`,
  invisible to a second process. Run two copies of `app.py` and they *will* race and corrupt the file —
  demonstrated deliberately, not hidden.
- **Failure isolation** — a bug in the recommendation scorer can take down `/login` too, since everything
  (API and website) shares one Flask process and one Python interpreter.
- **Deployment risk** — any change, even a typo fix on a page, requires redeploying and restarting the
  entire app, briefly taking every page and endpoint offline together.
- **Testing granularity** — `test_app.py` can't test `/recommendations` without also exercising the
  data-access and auth layers, because nothing is decoupled yet.

These are exactly the pain points Phase 2 (microservices) is designed to solve.

## 10. Project structure

```
globetrotter-monolith/
├── app.py                       # Flask app — API + page routes, business logic, data access, auth
├── templates/
│   ├── base.html                  # shared layout, nav, design tokens (CSS variables)
│   ├── index.html                 # home page
│   ├── login.html
│   ├── register.html
│   ├── destinations.html          # search/filter + "plan a trip" modal
│   ├── recommendations.html
│   └── itineraries.html           # route-line timeline + share modal
├── static/
│   └── js/
│       └── main.js                # GT.api() fetch wrapper, auth/session helpers, region colors
├── data/
│   └── db.json                    # users, 15 Cameroonian destinations, itineraries
├── requirements.txt
├── test_app.py                    # pytest suite (18 tests)
└── README.md
```
