Running locally with Docker

1. Build and start (Docker Compose)
   docker compose up --build

   The site will be available at: http://localhost:5000
   The JSON DB is persisted to ./data/db.json thanks to the bind mount in docker-compose.yml.

2. One-off docker run (without compose)
   docker build -t globetrotter .
   docker run -p 5000:5000 -v "$(pwd)/data:/app/data" -e GLOBETROTTER_SECRET=change-me globetrotter

Notes:
- The app expects data/db.json to exist (the repo already includes a seeded db.json). The docker compose volume mounts your local ./data directory into the container so itineraries you create will persist.
- Change GLOBETROTTER_SECRET in production to a strong secret.
- For production deployments you may want to increase gunicorn workers and add proper logging, TLS termination, and a process supervisor.
