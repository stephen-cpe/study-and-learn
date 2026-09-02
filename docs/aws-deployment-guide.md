# AWS EC2 Deployment Guide
## For Ubuntu 26.04 LTS (t3.xlarge) + DuckDNS + Let's Encrypt SSL
### Complete Guide for Windows 11 Users

## Disclaimer
_This guide documents a temporary AWS EC2 deployment for testing and verification. The instance is intended to be decommissioned after confirming the application deploys and runs correctly._

---

## Overview

This guide walks you through deploying the Study-and-Learn Flask application to an AWS EC2 instance with:
-  **HTTPS/SSL** with Let's Encrypt
-  **Dynamic DNS** with DuckDNS
-  **Gunicorn** (gthread, 1 worker, 8 threads) + **Nginx** reverse proxy
-  **PostgreSQL** + **Chroma Cloud** + **Ollama Cloud** (all heavy AI offloaded)
-  **User Data** script for automated instance initialization
-  **Windows 11** compatible (uses Git Bash / PuTTY)

**Time Required:** 45-60 minutes (User Data script automates most of the server setup)
**Cost:** ~$0.17/hour (t3.xlarge, 4 vCPU / 16 GB RAM / 30 GB SSD) — decommission when done

> **Why gthread (1 worker, 8 threads) instead of multi-worker?**
> The app uses `cachelib.FileSystemCache` for Flask sessions (`data/flask_session/`) and progress tracking (`data/progress_cache/`). These are per-process filesystem caches. Multiple Gunicorn workers would split the cache and break session/progress consistency. A single worker with 8 threads keeps all caching in one process and trivially handles 3 concurrent users.

> **Instance sizing note:** The t3.xlarge (4 vCPU / 16 GB RAM / 30 GB SSD) tier is more than sufficient because heavy AI inference runs on Ollama Cloud (`AI_BACKEND=cloud`) and vector storage on Chroma Cloud (`CHROMA_DB=cloud`). The instance only runs Flask/Gunicorn, Nginx, and PostgreSQL. The extra RAM (16 GB vs the 8 GB on DigitalOcean) gives headroom for the OCR pipeline if you enable `OCR_FULL=true`.

---

## Prerequisites

### What You Need:
1. **AWS Account** - https://aws.amazon.com
2. **GitHub Account** - https://github.com
3. **DuckDNS Account** - https://duckdns.org (free)
4. **Git for Windows** - https://git-scm.com/download/win (includes Git Bash)
5. **Ollama Cloud API Key** - https://ollama.com (for `AI_BACKEND=cloud`)
6. **Chroma Cloud Credentials** - https://chromadb.com (API key, tenant ID, collection name)

---

## Step 1: Launch EC2 Instance with User Data

1. Log in to the AWS Console at https://console.aws.amazon.com
2. Navigate to **EC2** → **Instances** → **Launch instance**
3. Configure the instance:
   - **Name**: `study-and-learn`
   - **AMI**: Ubuntu Server 26.04 LTS (64-bit x86)
   - **Instance type**: `t3.xlarge` (4 vCPU, 16 GB RAM)
   - **Key pair**: Create new key pair (`study-and-learn.pem`) or use existing
   - **Storage**: 30 GB GP3 SSD

4. **Network settings** — configure the Security Group with inbound rules:
   - **Allow SSH traffic** from your IP (Port 22)
   - **Allow HTTP traffic from the internet** (Port 80, 0.0.0.0/0, ::/0)
   - **Allow HTTPS traffic from the internet** (Port 443, 0.0.0.0/0, ::/0)
   - Ensure **Auto-assign public IP** is enabled

5. **Advanced details** → **User data** — paste the initialization script below:

### Initialization Script (User Data)

Copy this script to the User data field during launch. It installs all system packages (Python, PostgreSQL, Nginx, Certbot, Poppler), configures the firewall, clones the repository, creates the virtual environment, and installs Python dependencies. The remaining steps (database setup, Ollama, service configs) are done manually after connecting — they involve service-user permissions and readiness checks that are fragile in an automated script.

```bash
#!/bin/bash
# ── Install system packages ─────────────────────────────────────────────────
apt update -y
apt install -y python3 python3-venv python3-pip python3-dev \
    build-essential libssl-dev \
    nginx certbot python3-certbot-nginx \
    postgresql postgresql-contrib \
    poppler-utils curl git ufw

# ── Configure firewall ──────────────────────────────────────────────────────
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

# ── Clone repository and install dependencies ───────────────────────────────
cd /home/ubuntu
git clone https://github.com/stephen-cpe/study-and-learn.git
cd study-and-learn

python3 -m venv venv
/home/ubuntu/study-and-learn/venv/bin/pip install --upgrade pip
/home/ubuntu/study-and-learn/venv/bin/pip install --no-cache-dir -r requirements.txt

# ── Install Ollama (the service starts automatically after install) ─────────
curl -fsSL https://ollama.com/install.sh | sh
systemctl enable ollama
systemctl start ollama

# ── Create logs and data directories ─────────────────────────────────────────
mkdir -p /home/ubuntu/study-and-learn/logs
touch /home/ubuntu/study-and-learn/logs/access.log /home/ubuntu/study-and-learn/logs/error.log
mkdir -p /home/ubuntu/study-and-learn/data/flask_session \
         /home/ubuntu/study-and-learn/data/progress_cache \
         /home/ubuntu/study-and-learn/data/uploads \
         /home/ubuntu/study-and-learn/data/tts \
         /home/ubuntu/study-and-learn/data/chroma_db

# ── Write systemd service file ──────────────────────────────────────────────
# The repo's deploy/study-and-learn.service uses User=root and
# WorkingDirectory=/home/study-and-learn. On AWS the app lives at
# /home/ubuntu/study-and-learn and runs as ubuntu. We write a corrected
# service file directly instead of copying the repo version.
cat > /etc/systemd/system/study-and-learn.service << 'SERVICE'
[Unit]
Description=Study-and-Learn Flask Application (Gunicorn)
After=network.target postgresql.service

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/study-and-learn
Environment="PATH=/home/ubuntu/study-and-learn/venv/bin"
EnvironmentFile=-/home/ubuntu/study-and-learn/.env
ExecStart=/home/ubuntu/study-and-learn/venv/bin/gunicorn -c gunicorn.conf.py app:app
Restart=on-failure
RestartSec=10

NoNewPrivileges=true
PrivateTmp=true
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SERVICE

# ── Write gunicorn.conf.py with AWS-correct paths ────────────────────────────
cat > /home/ubuntu/study-and-learn/gunicorn.conf.py << 'GUNICORN'
bind = "127.0.0.1:5000"
workers = 1
worker_class = "gthread"
threads = 8
timeout = 7200

accesslog = "/home/ubuntu/study-and-learn/logs/access.log"
errorlog = "/home/ubuntu/study-and-learn/logs/error.log"
loglevel = "info"
proc_name = "study-and-learn"
daemon = False
pidfile = "/tmp/study-and-learn.pid"
GUNICORN

# ── Write Nginx config ──────────────────────────────────────────────────────
cat > /etc/nginx/sites-available/study-and-learn << 'NGINX'
server {
    listen 80;
    listen [::]:80;
    server_name studyandlearn.duckdns.org;

    client_max_body_size 50M;

    access_log /var/log/nginx/study-and-learn-access.log;
    error_log /var/log/nginx/study-and-learn-error.log;

    location /static/ {
        alias /home/ubuntu/study-and-learn/src/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 300s;
        proxy_send_timeout 7200s;
        proxy_read_timeout 7200s;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/study-and-learn /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# ── Fix ownership and permissions ──────────────────────────────────────────
chown -R ubuntu:ubuntu /home/ubuntu/study-and-learn
# Make /home/ubuntu traversable by Nginx (www-data) and PostgreSQL (postgres).
# On AWS, /home/ubuntu defaults to 700 (only ubuntu can access). Nginx needs
# to read static files and PostgreSQL needs to read init_db.sql. chmod 755
# allows traversal without making files writable by others.
chmod 755 /home/ubuntu
```

6. Click **Launch instance**.
7. Wait 3-5 minutes for the User Data script to finish.
8. Note the **Public IPv4 address** from the EC2 instance details (e.g., `3.123.45.67`).

> **What the User Data script does:**
> - Installs all system packages (Python, PostgreSQL, Nginx, Certbot, Poppler, Ollama)
> - Configures the firewall (SSH + HTTP/HTTPS)
> - Clones the repository and creates the virtual environment with all dependencies
> - Creates data/log directories
> - Writes the systemd service file, gunicorn config, and Nginx config (with AWS-correct paths)
>
> **What the User Data script does NOT do:**
> - It does NOT create the PostgreSQL database/user (done manually in Step 3 — needs `postgres` user permissions)
> - It does NOT run `init_db.sql` (done manually in Step 3 — `postgres` user can't read files in `/home/ubuntu/`)
> - It does NOT pull the Ollama embedding model (done manually in Step 3 — needs the `ollama` service to be fully started)
> - It does NOT create the `.env` file (done manually in Step 3 — contains API keys)
> - It does NOT start the Gunicorn or Nginx services (done after the `.env` file exists)

---

## Step 2: Configure DuckDNS

1. Go to https://duckdns.org
2. Sign in with GitHub/Google
3. In the domain field, type: `studyandlearn` (without .duckdns.org)
4. Click **Add Domain**
5. Update the IP address:
   - Enter your EC2 instance's **Public IPv4 address**
   - Click **Update IP**
6. Note your **DuckDNS Token** (click "token" link) - you'll need this later

**Keep this page open** or save:
- Domain: `studyandlearn.duckdns.org`
- Token: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- IP: `3.123.45.67` (example)

> **Note:** If you stop/start the EC2 instance, the public IP changes unless you allocate an Elastic IP (free under AWS Free Tier). If the IP changes, update DuckDNS and re-run Certbot (Step 6).

---

## Step 3: Connect and Create the .env File

### Connect via SSH (using Git Bash on Windows):

```bash
ssh -i "study-and-learn.pem" ubuntu@YOUR_EC2_PUBLIC_IP
```

**First time?** You'll see:
```
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```
Type `yes` and press Enter.

> **Tip:** If you get `Permission denied`, check that your `.pem` file has the correct permissions:
> ```bash
> chmod 400 study-and-learn.pem
> ```
> (Run this in Git Bash on your local machine.)

### Verify the User Data script completed successfully:

```bash
# Check the app code was cloned
ls /home/ubuntu/study-and-learn/app.py

# Check the venv was created
ls /home/ubuntu/study-and-learn/venv/bin/gunicorn
```

Both commands should return file paths (no errors). The User Data script installs packages, clones the repo, creates the venv, and writes the service configs — but it does NOT set up the database or pull the Ollama model (those are the next steps).

### Step 3.1: Set Up PostgreSQL Database

The app requires PostgreSQL (it refuses to start with any other database). These commands must be run manually because the `postgres` system user needs to run `psql` and read `init_db.sql`.

```bash
# Create the database user and database
sudo -u postgres psql << 'EOF'
CREATE USER study_user WITH PASSWORD 'study_pass';
CREATE DATABASE study_and_learn OWNER study_user;
GRANT CREATE ON SCHEMA public TO study_user;
EOF
```

```bash
# Copy init_db.sql to /tmp so the postgres user can read it
# (the postgres user cannot traverse /home/ubuntu/ due to its permissions)
sudo cp /home/ubuntu/study-and-learn/init_db.sql /tmp/init_db.sql

# Initialize the database schema (tables, indexes, seed users)
sudo -u postgres psql -d study_and_learn -f /tmp/init_db.sql

# Clean up (file is owned by root since we used sudo cp)
sudo rm /tmp/init_db.sql
```

> **Why `sudo -u postgres`?** On Ubuntu, PostgreSQL uses *peer authentication* for local socket connections — the OS user running `psql` must match the database username. The `postgres` OS user is the PostgreSQL superuser.

Verify the tables were created:

```bash
sudo -u postgres psql -d study_and_learn -c "\dt"
```

You should see: `users`, `study_paths`, `content_registry`, `lesson_progress`, `alembic_version`

This creates three seed accounts for testing:

| Username | Password       | Role  | Can generate lessons |
|----------|---------------|-------|----------------------|
| admin    | ADMINpassword | ADMIN | Yes                  |
| bob      | BOBpassword   | USER  | Yes                  |
| alice    | ALICEpassword | USER  | Yes                  |

### Step 3.2: Pull the Ollama Embedding Model

The User Data script installed Ollama, but the embedding model must be pulled manually (the `ollama pull` command needs the Ollama service to be fully started, which can take 10-15 seconds after install).

```bash
# Pull the embedding model (tiny, ~600 MB, CPU-only)
ollama pull qwen3-embedding:0.6b

# Verify it's available
curl http://localhost:11434/api/tags
```

**Expected output:**
```json
{"models":[{"name":"qwen3-embedding:0.6b", ...}]}
```

> **Why a local Ollama for embeddings?** Ollama Cloud's API only supports the OpenAI-compatible `/v1/chat/completions` endpoint. The `langchain_ollama.OllamaEmbeddings` class uses the native Ollama `/api/embed` endpoint, which is not exposed by Ollama Cloud. So embedding calls must go to a local Ollama instance.

### Step 3.3: Create the .env file

```bash
cd /home/ubuntu/study-and-learn
nano .env
```

Add your production configuration:

```bash
# ── Flask Core ──────────────────────────────────────────────────────────────
# Generate a strong random key: python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=REPLACE_WITH_GENERATED_SECRET_KEY

# ── Database ────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn

# ── AI / Ollama Cloud ───────────────────────────────────────────────────────
AI_MOCK=false
AI_BACKEND=cloud
OLLAMA_CLOUD_API_KEY=your-ollama-cloud-api-key-here
OLLAMA_CLOUD_BASE_URL=https://ollama.com
OLLAMA_MODEL=gemma4:cloud

# ── Vector Store / Chroma Cloud ─────────────────────────────────────────────
CHROMA_DB=cloud
CHROMA_CLOUD_API_KEY=your-chroma-cloud-api-key-here
CHROMA_CLOUD_CONNECTION_STRING=your-chroma-tenant-id-here
CHROMA_COLLECTION_NAME=study-and-learn-chromadb

# ── OCR (disabled by default to avoid memory pressure) ───────────────────────
# OCR_FULL=false still runs GLM-OCR text-mode on image uploads (.png/.jpg/.jpeg).
# Setting OCR_FULL=true enables text+table+figure OCR on every PDF/DOCX/PPTX page
# (3 local Ollama calls/page). The t3.xlarge has 16 GB RAM, so this is safe to enable.
OCR_FULL=false
# OCR_FIGURE_DESCRIPTION=true adds a glm-5.3-flash:cloud call per page (Ollama Cloud).
OCR_FIGURE_DESCRIPTION=false

# ── CI / Testing (set to false in production) ───────────────────────────────
CI=false
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

```bash
# Secure the file (only ubuntu can read it)
chmod 600 .env
```

> **Why `AI_BACKEND=cloud` and `CHROMA_DB=cloud`?**
> Running local AI models (e.g., a 27B parameter LLM) on the EC2 instance would consume all RAM. Ollama Cloud offloads all LLM inference to Ollama's hosted infrastructure. Chroma Cloud offloads vector storage and similarity search. The instance only orchestrates HTTP requests, DB reads/writes, and the background TTS worker thread — all lightweight CPU work.

### Step 3.4: Verify the app loads

```bash
cd /home/ubuntu/study-and-learn
source venv/bin/activate

# Quick smoke test — import the app without running the dev server
python3 -c "from app import app; print('App loaded successfully'); print(app.config.get('SQLALCHEMY_DATABASE_URI', 'NO DB URI'))"
```

**Expected output:**
```
App loaded successfully
postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn
```

> If you see `RuntimeError: SECRET_KEY is set to the insecure default`, generate a strong key and update `.env`:
> ```bash
> python3 -c "import secrets; print(secrets.token_hex(32))"
> ```
> Paste the output into the `SECRET_KEY=` line in `.env`.

---

## Step 4: Start the Application Service

The User Data script already copied the systemd service file and Nginx config into place. You just need to start them.

### Step 4.1: Start Gunicorn

```bash
sudo systemctl daemon-reload
sudo systemctl enable study-and-learn
sudo systemctl start study-and-learn
sudo systemctl status study-and-learn
```

**Expected output:**
```
● study-and-learn.service - Study-and-Learn Flask Application (Gunicorn)
     Active: active (running)
```

Press `q` to exit status view.

### Step 4.2: Verify Application

```bash
curl http://127.0.0.1:5000/health
```

**Expected response:**
```json
{"status":"healthy"}
```

```bash
# Check logs if something went wrong
sudo journalctl -u study-and-learn -n 50 --no-pager
```

**If you see the JSON health response, the app is running!**

---

## Step 5: Start Nginx (Reverse Proxy)

The User Data script already copied the Nginx config and enabled the site. You just need to start Nginx.

```bash
# Test configuration
sudo nginx -t

# Start Nginx
sudo systemctl start nginx
sudo systemctl enable nginx
```

**Expected output of `nginx -t`:**
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### Update the server_name (if needed)

If your DuckDNS domain differs from `studyandlearn.duckdns.org`, update the `server_name` line:

```bash
sudo nano /etc/nginx/sites-available/study-and-learn
```

Change the `server_name` line to match your DuckDNS domain, then restart Nginx:

```bash
sudo systemctl restart nginx
```

### Test without SSL first

Open your browser and go to: `http://studyandlearn.duckdns.org`

**You should see the Study-and-Learn login page!**

If not, check:
```bash
sudo systemctl status study-and-learn
sudo systemctl status nginx
sudo journalctl -u study-and-learn -n 50 --no-pager
sudo tail -20 /var/log/nginx/study-and-learn-error.log
```

---

## Step 6: Obtain SSL Certificate (Let's Encrypt)

```bash
# First run WITHOUT --redirect (obtains the certificate)
sudo certbot --nginx -d studyandlearn.duckdns.org --email your-email@example.com --agree-tos

# Then run WITH --redirect (forces all HTTP → HTTPS)
sudo certbot --nginx -d studyandlearn.duckdns.org --email your-email@example.com --agree-tos --redirect
```

**Replace `your-email@example.com`** with your actual email.

Test auto-renewal:

```bash
sudo certbot renew --dry-run
```

Enable the auto-renewal timer:

```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

### Verify HTTPS

Open browser and go to: `https://studyandlearn.duckdns.org`

**You should see the login page with the padlock icon!**

Log in with the seed credentials (`admin` / `ADMINpassword`) and verify you can navigate the app.

> **⚠️ WARNING: The Nginx config from the User Data script is HTTP-only (port 80).** Certbot adds the SSL directives (`listen 443 ssl`, certificate paths, and the HTTP→HTTPS redirect) automatically. If you ever overwrite the Nginx config (e.g., by re-copying from the repo), you **MUST re-run the Certbot commands above** to restore the SSL block.

---

## Step 7: Configure DuckDNS Automatic Updates

Your EC2 public IP might change if you stop/start the instance. DuckDNS keeps your domain updated.

### Step 7.1: Create DuckDNS Script

```bash
mkdir -p ~/duckdns
cd ~/duckdns
nano duck.sh
```

**Paste this** (replace YOUR_TOKEN and YOUR_DOMAIN):

```bash
#!/bin/bash
TOKEN="your-duckdns-token-here"
DOMAIN="studyandlearn"
echo url="https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=" | curl -k -o ~/duckdns/duck.log -K -
```

**Save and exit** (`Ctrl+O`, Enter, `Ctrl+X`)

### Step 7.2: Make Executable and Test

```bash
chmod 700 duck.sh
./duck.sh
cat duck.log
```

**Expected output:** `OK`

### Step 7.3: Set Up Cron Job

```bash
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -
```

**Verify:**
```bash
crontab -l
```

Should show: `*/5 * * * * /home/ubuntu/duckdns/duck.sh >/dev/null 2>&1`

---

## Step 8: Verify the Full Deployment

### Step 8.1: Check All Services

```bash
sudo systemctl status study-and-learn nginx postgresql ollama
```

All should show `active (running)`.

### Step 8.2: Check Health Endpoint

```bash
curl http://127.0.0.1:5000/health
```

**Expected response:**
```json
{"status":"healthy"}
```

### Step 8.3: Test in Browser

Visit: `https://studyandlearn.duckdns.org`

- Log in as `admin` / `ADMINpassword`
- Upload a small PDF and click **Process My Learning Materials**
- Verify the progress page loads and the mascot animates
- Verify the results page shows a summary and study path
- Click **Generate Interactive Lessons** and verify modules appear

> **Note:** Lesson generation with cloud AI (default model `gemma4:cloud`, override via `OLLAMA_MODEL`) and 3+ modules can take 45-90 minutes. The progress page will show the mascot animating during this time. This is expected behavior.

---

## Troubleshooting

### App Won't Start

**Error:** `RuntimeError: DATABASE_URL environment variable is required`

**Fix:**
1. Verify `.env` exists: `ls -la /home/ubuntu/study-and-learn/.env`
2. Verify it has `DATABASE_URL=postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn`
3. Verify permissions: `chmod 600 .env`
4. Restart: `sudo systemctl restart study-and-learn`
5. Check logs: `sudo journalctl -u study-and-learn -n 50 --no-pager`

### App Won't Start

**Error:** `RuntimeError: DATABASE_URL must use PostgreSQL`

**Fix:** The `DATABASE_URL` must start with `postgresql`. Check for typos in `.env`.

### App Won't Start

**Error:** `RuntimeError: SECRET_KEY is set to the insecure default`

**Fix:** Generate a strong secret key and update `.env`:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Paste the output into the `SECRET_KEY=` line in `.env`, then restart:
```bash
sudo systemctl restart study-and-learn
```

### Database Connection Failed

**Error:** `psycopg2.OperationalError: could not connect to server`

**Fix:**
1. Verify PostgreSQL is running: `sudo systemctl status postgresql`
2. Verify the database exists: `sudo -u postgres psql -l | grep study_and_learn`
3. If the User Data script didn't complete, initialize manually:
   ```bash
   sudo -u postgres psql
   CREATE USER study_user WITH PASSWORD 'study_pass';
   CREATE DATABASE study_and_learn OWNER study_user;
   GRANT CREATE ON SCHEMA public TO study_user;
   \q
   sudo cp /home/ubuntu/study-and-learn/init_db.sql /tmp/init_db.sql
   sudo -u postgres psql -d study_and_learn -f /tmp/init_db.sql
   sudo rm /tmp/init_db.sql
   ```

### Gunicorn 502 Bad Gateway

**Error:** Nginx returns `502 Bad Gateway`

**Fix:**
1. Check if Gunicorn is running: `sudo systemctl status study-and-learn`
2. If failed, check logs: `sudo journalctl -u study-and-learn -n 50 --no-pager`
3. Check if port 5000 is listening: `curl http://127.0.0.1:5000/health`
4. Restart both services:
   ```bash
   sudo systemctl restart study-and-learn
   sudo systemctl restart nginx
   ```

### SSL Certificate Issues

**Error:** Certbot fails to verify domain

**Fix:**
1. Verify DuckDNS is pointing to your EC2 instance: `ping studyandlearn.duckdns.org`
2. Verify Nginx is running and port 80 is open: `sudo ufw status`
3. Wait 5 minutes for DNS propagation, then retry certbot
4. If the EC2 public IP changed, update DuckDNS first, then re-run Certbot

### Ollama Not Running

**Error:** `curl http://localhost:11434/api/tags` returns nothing

**Fix:**
```bash
sudo systemctl start ollama
sudo systemctl enable ollama
ollama pull qwen3-embedding:0.6b
curl http://localhost:11434/api/tags
```

### User Data Script Didn't Complete

**Symptom:** Missing app files or venv after connecting.

**Fix:** Check the log:
```bash
cat /var/log/cloud-init-output.log
```

The most common cause is a transient `apt` lock during the initial boot — wait a few minutes and retry. If the repo clone or `pip install` failed, re-run manually:
```bash
cd /home/ubuntu
git clone https://github.com/stephen-cpe/study-and-learn.git
cd study-and-learn
python3 -m venv venv
/home/ubuntu/study-and-learn/venv/bin/pip install --upgrade pip
/home/ubuntu/study-and-learn/venv/bin/pip install --no-cache-dir -r requirements.txt
```

### "View Sources" Button Missing

**Symptom:** The "View Sources" button does not appear in the lesson deck.

**Root Cause:** The ChromaDB vector store uses `langchain_ollama.OllamaEmbeddings` to embed query text during RAG retrieval. This class calls the **local Ollama** API (`http://localhost:11434/api/embed`), NOT the Ollama Cloud endpoint. If Ollama is not running (or the `qwen3-embedding:0.6b` model is not pulled), the embedding call fails, ChromaDB returns empty context and empty sources, and lessons are generated without document-grounded context.

**Diagnosis:**
```bash
# 1. Check if Ollama is running
curl http://localhost:11434/api/tags

# 2. Check for embedding/retrieval errors in the logs
sudo journalctl -u study-and-learn --since "60 min ago" --no-pager | grep -i "chroma\|retriev\|embed\|source\|ollama"

# 3. Check if sources are empty in the lesson dict
sudo -u postgres psql -d study_and_learn -c "SELECT content_data::jsonb->0->>'sources' FROM study_paths ORDER BY created_at DESC LIMIT 1;"
# If this returns [], sources were not populated
```

**Fix:**
```bash
# Ensure Ollama is running and the model is available
sudo systemctl restart ollama
ollama pull qwen3-embedding:0.6b
sudo systemctl restart study-and-learn
```

### DuckDNS IP Changed After EC2 Restart

If you stop/start the EC2 instance and get a new public IP:

1. Go to DuckDNS.org and update the IP to the new public IPv4 address.
2. Re-run Certbot to update the SSL certificate:
   ```bash
   sudo certbot --nginx -d studyandlearn.duckdns.org --email your-email@example.com --agree-tos --redirect
   ```

For a stable IP, use an Elastic IP (free under AWS Free Tier):
1. EC2 Console → **Elastic IPs** → **Allocate Elastic IP address**
2. **Associate** it with your running instance
3. Update DuckDNS with the new (static) Elastic IP
4. Re-run Certbot

### Lesson Generation Hangs

**Symptom:** Progress page stays at "Building lesson..." for a long time

**This is expected with cloud AI.** Full generation with the default cloud chat model (`gemma4:cloud`, override via `OLLAMA_MODEL`) and 3+ modules can take 45-90 minutes. The JS hard-timeout is 2 hours and will show a "still working" message without redirecting. Check:

1. Is Ollama Cloud reachable? `curl -H "Authorization: Bearer $OLLAMA_CLOUD_API_KEY" https://ollama.com/api/tags`
2. Check app logs: `tail -50 /home/ubuntu/study-and-learn/logs/error.log`
3. Check the DB column: `sudo -u postgres psql -d study_and_learn -c "SELECT id, generation_completed_at FROM study_paths ORDER BY created_at DESC LIMIT 5;"`
4. If `generation_completed_at` is NULL after 2 hours, the TTS worker may have crashed — check logs for `tts-` thread errors.

### TTS Generation Fails (Errno 24: Too many open files)

**Symptom:** Error log shows `OSError: [Errno 24] Too many open files` during TTS-enabled generation.

**Fix:**
1. Verify `LimitNOFILE=65536` is in the systemd unit: `grep LimitNOFILE /etc/systemd/system/study-and-learn.service`
2. Verify the running process has the limit: `cat /proc/$(pgrep -f gunicorn | head -1)/limits | grep "Max open files"` — should show `65536`
3. If the limit is still 1024, reload and restart:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart study-and-learn
   ```

---

## Service Management

```bash
# Check status of all services
sudo systemctl status study-and-learn nginx postgresql ollama

# Restart individual services
sudo systemctl restart study-and-learn
sudo systemctl restart nginx
sudo systemctl restart ollama

# View logs
sudo journalctl -u study-and-learn -f
sudo journalctl -u study-and-learn -n 50 --no-pager
sudo tail -f /home/ubuntu/study-and-learn/logs/error.log
sudo tail -f /var/log/nginx/study-and-learn-error.log
```

---

## Decommission

When you're done testing, terminate the EC2 instance to stop incurring charges:

1. EC2 Console → **Instances** → select your instance
2. **Instance state** → **Terminate instance**

> **If you allocated an Elastic IP**, release it too (Elastic IPs incur charges when not associated with a running instance):
> EC2 Console → **Elastic IPs** → select → **Release Elastic IP address**

---

## Architecture Summary

```
Internet
    |
    v
[Nginx :80/:443] -- SSL via Certbot/Let's Encrypt
    |
    +-- /static/ --> /home/ubuntu/study-and-learn/src/static/ (served by Nginx)
    |
    +-- / --> 127.0.0.1:5000 (Flask + Gunicorn, 1 worker, 8 threads)
                 |
                 +-- PostgreSQL (study_and_learn database)
                 +-- Local Ollama :11434 (qwen3-embedding:0.6b for RAG embeddings)
                 +-- Ollama Cloud (chat LLM: gemma4:cloud)
                 +-- Chroma Cloud (vector storage)
                 +-- Edge-TTS (neural text-to-speech, background worker thread)
```

Two systemd services:
- `study-and-learn.service` - Flask + Gunicorn (port 5000)
- `ollama.service` - Local Ollama (port 11434, auto-installed)

---