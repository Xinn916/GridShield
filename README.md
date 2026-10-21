# GridShield

GridShield was formerly named PrivGrid-Agent. Some internal identifiers and documentation still use the previous name.

> Database deployment: The local demo uses SQLite to store control-plane metadata, while raw energy data at each park remain in read-only Parquet files. See [docs/production-database.md](docs/production-database.md) for the optional production PostgreSQL configuration, concurrency limits, and features that are not yet implemented.

A platform for secure multi-party collaboration and privacy-preserving analysis in trusted energy data spaces.

The system consists of three data providers, two non-colluding computing nodes, a control plane, and a frontend service. It supports multi-party aggregate queries, secret sharing, distributed differential privacy, privacy budget management, audit trails, and a natural-language query agent.

## 1. System Components

Docker Compose starts seven containers:

| Service | Container name | Role | Host port |
|---|---|---|---:|
| frontend | `privgrid-frontend` | Web interface and Nginx reverse proxy | 8080 |
| control-plane | `privgrid-control` | Task scheduling, budget management, auditing, agent services, and result aggregation | 8000 |
| party-a | `privgrid-party-a` | Data processing node for ORG_A | 8101 |
| party-b | `privgrid-party-b` | Data processing node for ORG_B | 8102 |
| party-c | `privgrid-party-c` | Data processing node for ORG_C | 8103 |
| compute-s1 | `privgrid-compute-s1` | Computing node for the first secret share | 8201 |
| compute-s2 | `privgrid-compute-s2` | Computing node for the second secret share | 8202 |

Request flow:

```text
Browser
  ↓
frontend
  ↓
control-plane
  ↓
party-a / party-b / party-c
  ↓
compute-s1 / compute-s2
  ↓
control-plane aggregates the results
  ↓
frontend displays the results
```

## 2. Requirements

Docker is the recommended way to run the system.

Install the following:

- Windows 10/11
- Docker Desktop
- Docker Compose
- Git

Check that Docker is available:

```powershell
docker version
docker compose version
```

The output of `docker version` should include both `Client` and `Server`.

## 3. Initial Startup

### 3.1 Open the Project Directory

```powershell
cd D:\Program\ChallengeCup
```

### 3.2 Create the Docker Environment File

The project root should contain:

```text
.env.docker.example
```

Copy it to `.env.docker`:

```powershell
Copy-Item .env.docker.example .env.docker
```

Edit `.env.docker` to suit your environment. For example:

```env
APP_ENV=development
DEEPSEEK_API_KEY=YOUR_API_KEY
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_TIMEOUT_SECONDS=20
DEFAULT_TOTAL_EPSILON=20
```

`APP_ENV` accepts only `development`, `testing`, or `production`. The control plane exposes this value to the frontend through a safe public configuration endpoint. The environment badge in the interface cannot be changed manually.

Important:

- Do not include a real API key in `README.md`.
- Do not commit `.env.docker`.
- Ensure that `.env.docker` is ignored by `.gitignore`.

Check the ignore settings:

```powershell
git check-ignore .env.docker
git ls-files .env.docker
```

The second command should produce no output.

### 3.3 Validate the Compose Configuration

```powershell
docker compose config -q
```

Successful validation normally produces no output.

Do not use the following command without the `-q` option:

```powershell
docker compose config
```

It may print resolved environment variable values.

### 3.4 Load the Offline Images Provided with the Competition Materials

```powershell
docker load -i ..\..\02-部署镜像\privgrid-backend-v4.tar
docker load -i ..\..\02-部署镜像\privgrid-frontend-v5.tar
```

These archives load two local images:

```text
privgrid-backend:v4
privgrid-frontend:v5
```

### 3.5 Start All Services

```powershell
docker compose up -d
```

### 3.6 Check Service Status

```powershell
docker compose ps
```

All seven services should show a status similar to:

```text
Up ... (healthy)
```

### 3.7 Open the Application

Open the following address in a browser:

```text
http://localhost:8080
```

The control-plane health endpoint is:

```text
http://localhost:8000/health
```

## 4. Routine Startup

If the images have already been built, run:

```powershell
cd D:\Program\ChallengeCup
docker compose up -d
docker compose ps
```

Then open:

```text
http://localhost:8080
```

## 5. Restarting After Code Changes

After changing backend or frontend code, run:

```powershell
docker load -i ..\..\02-部署镜像\privgrid-backend-v4.tar
docker load -i ..\..\02-部署镜像\privgrid-frontend-v5.tar
docker compose up -d
docker compose ps
```

Alternatively, run:

```powershell
docker compose up -d
```

If only environment variables in `compose.yaml` have changed, rebuilding the images is generally unnecessary:

```powershell
docker compose up -d --force-recreate
docker compose ps
```

## 6. Common Commands

Check service status:

```powershell
docker compose ps
```

View logs for all services:

```powershell
docker compose logs --tail=100
```

View logs for individual services:

```powershell
docker compose logs --tail=200 control-plane
docker compose logs --tail=200 party-a
docker compose logs --tail=200 compute-s1
```

Follow logs in real time:

```powershell
docker compose logs -f control-plane
```

Press `Ctrl+C` to stop following the logs. This does not stop the containers.

Restart all services:

```powershell
docker compose restart
docker compose ps
```

Stop and remove the containers while retaining the database volume:

```powershell
docker compose down
```

Start the services again:

```powershell
docker compose up -d
```

## 7. Data Persistence

The control-plane SQLite database is stored in the following Docker named volume:

```text
privgrid-control-data
```

It contains task, budget, and audit information.

Do not run:

```powershell
docker compose down -v
```

The `-v` option removes named volumes and may cause SQLite data loss.

Also avoid running the following command without carefully checking its effects:

```powershell
docker system prune -a
```

## 8. Data Isolation

Each of the three data providers mounts only its own data file in read-only mode:

```text
party-a → data_processed/party_a.parquet
party-b → data_processed/party_b.parquet
party-c → data_processed/party_c.parquet
```

Inspect the mounted files:

```powershell
docker compose exec party-a sh -c "find /app/data -maxdepth 1 -type f -print"
docker compose exec party-b sh -c "find /app/data -maxdepth 1 -type f -print"
docker compose exec party-c sh -c "find /app/data -maxdepth 1 -type f -print"
```

Each party should see only its own Parquet file.

## 9. Communication Between Data Providers and Computing Nodes

The three party containers must access S1 and S2 using Docker service names:

```env
COMPUTE_S1_URL=http://compute-s1:8201
COMPUTE_S2_URL=http://compute-s2:8202
```

Do not use the following addresses inside the containers:

```text
http://127.0.0.1:8201
http://127.0.0.1:8202
```

Inside a container, `127.0.0.1` refers to that container itself.

If a secret-sharing task returns HTTP 502, inspect the logs:

```powershell
docker compose logs --tail=200 party-a
docker compose logs --tail=200 compute-s1
docker compose logs --tail=200 compute-s2
docker compose logs --tail=200 control-plane
```

## 10. Functional Checks

Example aggregate query:

```text
Mode: DISTRIBUTED_DP
Query type: SUM
Parks: ORG_A, ORG_B, ORG_C
Start time: 2012-11-11 00:00
End time: 2012-11-12 00:00
epsilon: 1.0
```

Check that:

- The task status is `COMPLETED`.
- A noisy result is returned.
- The privacy budget is deducted once.
- An audit record is created.

Example time-series query:

```text
Mode: DISTRIBUTED_DP
Query type: TIME_SERIES
Parks: ORG_A, ORG_B, ORG_C
Start time: 2012-11-11 00:00
End time: 2012-11-12 00:00
group_by: 1h
epsilon: 1.0
```

Check that:

- The result contains 24 time bins.
- The line chart is displayed correctly.
- Epsilon is deducted only once for the entire series.
- The task status is `COMPLETED`.
- An audit record is created.

Example agent query:

```text
Query the hourly aggregate electricity load of the three parks
for the full day of 11 November 2012, with a privacy budget of 1.
```

The agent should only parse the request and populate the form. It should not submit the task automatically.

## 11. Local Tests

Backend:

```powershell
cd D:\Program\ChallengeCup
$env:PYTHONPATH="backend"
python -m pytest -c backend\pytest.ini
```

Frontend:

```powershell
cd D:\Program\ChallengeCup\frontend
npm test
npm run build
```

## 12. Troubleshooting

### Docker Command Not Found

Ensure that Docker Desktop is running, then reopen PowerShell or VS Code:

```powershell
where.exe docker
docker version
```

### Unhealthy Container

Run the following commands, replacing `SERVICE_NAME` with the affected service:

```powershell
docker compose ps
docker compose logs --tail=200 SERVICE_NAME
```

### Application Page Does Not Open

```powershell
docker compose ps
docker compose logs --tail=200 frontend
```

Open:

```text
http://localhost:8080
```

### Query Returns HTTP 502

Inspect the party and computing-node logs, then check the configured URLs:

```powershell
docker compose exec party-a python -c "import os; print(os.getenv('COMPUTE_S1_URL')); print(os.getenv('COMPUTE_S2_URL'))"
```

Expected output:

```text
http://compute-s1:8201
http://compute-s2:8202
```

### Page Does Not Change After Code Updates

```powershell
docker load -i ..\..\02-部署镜像\privgrid-frontend-v5.tar
docker compose up -d frontend
```

Force-refresh the browser:

```text
Ctrl + F5
```

## 13. Project Structure

```text
ChallengeCup/
├─ backend/
├─ frontend/
├─ data_processed/
├─ dataset/
├─ docs/
├─ compose.yaml
├─ compose.prod.yaml
├─ .env.docker.example
├─ .env.docker
├─ .dockerignore
├─ .gitignore
└─ README.md
```

## 14. Quick Command Reference

See [docs/data-imports.md](docs/data-imports.md) for instructions on importing complete park-level CSV snapshots, validating data, activating versions, and rolling back. The three baseline Parquet files remain read-only. Imported versions are stored in each party's own named volume, while the control database stores only safe metadata.

Initial startup:

```powershell
cd D:\Program\ChallengeCup
Copy-Item .env.docker.example .env.docker
docker compose config -q
docker load -i ..\..\02-部署镜像\privgrid-backend-v4.tar
docker load -i ..\..\02-部署镜像\privgrid-frontend-v5.tar
docker compose up -d
docker compose ps
```

Routine startup:

```powershell
cd D:\Program\ChallengeCup
docker compose up -d
docker compose ps
```

Stop the services:

```powershell
docker compose down
```

View logs:

```powershell
docker compose logs --tail=100
```

Open the application:

```text
http://localhost:8080
```

Startup:

```powershell
cd D:\Program\ChallengeCup
docker compose up -d
docker compose ps

docker compose up -d
```
