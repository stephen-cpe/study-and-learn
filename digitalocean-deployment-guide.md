# DigitalOcean Deployment Guide
## For $48/month Ubuntu 25.10 Droplet + DuckDNS + Let's Encrypt SSL
### Complete Guide for Windows 11 Users

## Disclaimer
_This guide is a work in progress. Use at your own risk. No warranties, guarantees, or support are provided._

---

## Overview

This guide walks you through deploying the Study-and-Learn Flask application to DigitalOcean with:
-  **Automated CI/CD** via GitHub Actions
-  **HTTPS/SSL** with Let's Encrypt
-  **Dynamic DNS** with DuckDNS
-  **Gunicorn** (gthread, 1 worker, 8 threads) + **Nginx** reverse proxy
-  **PostgreSQL** + **Chroma Cloud** + **Ollama Cloud** (all heavy AI offloaded)
-  **Windows 11** compatible (uses Git Bash)

**Time Required:** 60-90 minutes  
**Cost:** $48/month (DigitalOcean droplet, 4 vCPU / 8 GB RAM / 160 GB SSD)

> **Why gthread (1 worker, 8 threads) instead of multi-worker?**  
> The app uses `cachelib.FileSystemCache` for Flask sessions (`data/flask_session/`) and progress tracking (`data/progress_cache/`). These are per-process filesystem caches. Multiple Gunicorn workers would split the cache and break session/progress consistency. A single worker with 8 threads keeps all caching in one process and trivially handles 3 concurrent users.

> **Droplet sizing note:** The 4 vCPU / 8 GB RAM / 160 GB SSD tier ($48/month) is sufficient because heavy AI inference runs on Ollama Cloud (`AI_BACKEND=cloud`) and vector storage on Chroma Cloud (`CHROMA_DB=cloud`). The droplet only runs Flask/Gunicorn, Nginx, and PostgreSQL. If you later run local Ollama models, upgrade to the 8 vCPU / 16 GB RAM / 320 GB SSD tier ($96/month).

---

## Prerequisites

### What You Need:
1. **DigitalOcean Account** - https://digitalocean.com
2. **GitHub Account** - https://github.com
3. **DuckDNS Account** - https://duckdns.org (free)
4. **Git for Windows** - https://git-scm.com/download/win (includes Git Bash)
5. **Ollama Cloud API Key** - https://ollama.com (for `AI_BACKEND=cloud`)
6. **Chroma Cloud Credentials** - https://chromadb.com (API key, tenant ID, collection name)

---

## 1. Create a DigitalOcean Droplet

### Step-by-Step:

1. Log in to https://cloud.digitalocean.com
2. Click **Create** → **Droplets**
3. Choose the following configuration:
   - **Image**: Ubuntu 25.10
   - **Size**: 4 vCPU / 8 GB RAM / 160 GB SSD ($48/month)
   - **Authentication**: SSH key (recommended) or password
   - **SSH Key**: Add your existing SSH key or create a new one (see below)
4. (Optional) Add a hostname: `study-and-learn`
5. Click **Create Droplet**
6. Wait 1-2 minutes for provisioning
7. Note your droplet's **IP address** (shown in dashboard)

---

## 2. Configure DuckDNS

1. Go to https://duckdns.org
2. Sign in with GitHub/Google
3. In the domain field, type: `study-and-learn` (without .duckdns.org)
4. Click **Add Domain**
5. Update the IP address:
   - Enter your Droplet's IP address
   - Click **Update IP**
6. Note your **DuckDNS Token** (click "token" link) - you'll need this later

**Keep this page open** or save:
- Domain: `study-and-learn.duckdns.org`
- Token: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- IP: `134.209.11.38` (example)

---

## 3. Connect to Your Droplet

### Using Git Bash (Windows):

```bash
ssh -i ~/.ssh/digitalocean_key root@YOUR_DROPLET_IP
```

**First time?** You'll see:
```
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```
Type `yes` and press Enter.

**Using password?** If you didn't set up SSH key, use your droplet password.

### Using DigitalOcean Console (Alternative):

If SSH fails:
1. Go to DigitalOcean Dashboard → Droplets
2. Click your droplet
3. Click **Console** (top-right)
4. Log in with root password

---

## 4. Prepare the Server

**Once connected via SSH**, run these commands on the droplet:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3-full python3.13-venv python3.13-dev python3-pip python3-certbot-nginx build-essential libssl-dev nginx certbot curl git postgresql postgresql-contrib poppler-utils
```

> **Note:** `poppler-utils` provides `pdftoppm` which the OCR pipeline needs for PDF rendering. On Linux it is auto-detected — no `POPPLER_PATH` env var needed (unlike Windows).

---

### Step 5: Clone Your Repository

**For Public Repositories (this project is public — no deploy key needed):**

```bash
cd /home
git clone https://github.com/stephen-cpe/study-and-learn.git
```

> **If your repo were private**, you would need a GitHub deploy key (SSH key + `~/.ssh/config`). Since Study-and-Learn is public, HTTPS clone works directly.

---

## 6. Set Up the Application

### Step 6.1: Create Virtual Environment

**On the droplet:**

```bash
cd /home/study-and-learn

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies (gunicorn is already in requirements.txt)
pip install --no-cache-dir -r requirements.txt
```

### Step 6.2: Set Up PostgreSQL Database

The app requires PostgreSQL (it refuses to start with any other database).

```bash
# Switch to the postgres user
sudo -u postgres psql
```

Inside the `psql` prompt, run:

```sql
-- Create the application user (use a strong password in production!)
CREATE USER study_user WITH PASSWORD 'study_pass';

-- Create the database owned by study_user
CREATE DATABASE study_and_learn OWNER study_user;

-- Grant schema permissions
GRANT CREATE ON SCHEMA public TO study_user;

-- Exit psql
\q
```

Now initialize the schema (tables, indexes, foreign keys, alembic stamp, and seed users):

```bash
sudo -u postgres psql -d study_and_learn -f /home/study-and-learn/init_db.sql
```

> **Why `sudo -u postgres`?** On Ubuntu, PostgreSQL defaults to *peer authentication* for local socket connections — the OS user running `psql` must match the database username. Running `psql -U postgres` as `root` fails with `Peer authentication failed` because `root != postgres`. The fix is to run `psql` as the `postgres` OS user via `sudo -u postgres`. This is the same pattern used for the `CREATE USER` step above.

This creates three seed accounts for testing:

| Username | Password       | Role  | Can generate lessons |
|----------|---------------|-------|----------------------|
| admin    | ADMINpassword | ADMIN | Yes                  |
| bob      | BOBpassword   | USER  | Yes                  |
| alice    | ALICEpassword | USER  | Yes                  |

> **Security note:** Change these seed passwords or remove the seed users from `init_db.sql` before deploying to the public internet. For a 3-4 week temporary capstone demo, the seed accounts are fine for testing.

### Step 6.3: Create Environment File

```bash
cd /home/study-and-learn
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
OLLAMA_MODEL=gemma3:27b-cloud

# ── Vector Store / Chroma Cloud ─────────────────────────────────────────────
CHROMA_DB=cloud
CHROMA_CLOUD_API_KEY=your-chroma-cloud-api-key-here
CHROMA_CLOUD_CONNECTION_STRING=your-chroma-tenant-id-here
CHROMA_COLLECTION_NAME=study-and-learn-chromadb

# ── OCR (disabled for cloud deployment — no local GPU needed) ───────────────
OCR_FULL=false
OCR_FIGURE_DESCRIPTION=false

# ── CI / Testing (set to false in production) ───────────────────────────────
CI=false
```

Save: `Ctrl+O`, `Enter`, `Ctrl+X`

```bash
# Secure the file (only root can read it)
chmod 600 .env
```

> **Why `AI_BACKEND=cloud` and `CHROMA_DB=cloud`?**  
> Running local AI models (e.g., a 27B parameter LLM) on an 8 GB RAM droplet would cause OOM crashes. Ollama Cloud offloads all LLM inference to Ollama's hosted infrastructure. Chroma Cloud offloads vector storage and similarity search. The droplet only orchestrates HTTP requests, DB reads/writes, and the background TTS worker thread — all lightweight CPU work.

### Step 6.4: Create Logs and Data Directories

```bash
cd /home/study-and-learn
mkdir -p logs
touch logs/access.log logs/error.log
mkdir -p data/flask_session data/progress_cache data/uploads data/tts data/chroma_db
```

> These directories are created automatically by the app on startup, but creating them now avoids first-run permission issues.

### Step 6.5: Verify the App Starts

```bash
cd /home/study-and-learn
source venv/bin/activate

# Quick smoke test — import the app without running the dev server
python3 -c "from app import app; print('App loaded successfully'); print(app.config.get('SQLALCHEMY_DATABASE_URI', 'NO DB URI'))"
```

**Expected output:**
```
App loaded successfully
postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn
```

> If you see `RuntimeError: DATABASE_URL must use PostgreSQL`, check your `.env` file.  
> If you see `RuntimeError: DATABASE_URL environment variable is required`, run `source venv/bin/activate` again and ensure `.env` is in the project root.

---

## 7. Create Systemd Service (Gunicorn)

The repo includes versioned deployment configs in the `deploy/` directory and a standalone `gunicorn.conf.py` at the project root. Copy them into place instead of creating them from scratch.

### Step 7.1: Copy the Service File and Gunicorn Config

```bash
# Copy the systemd unit from the repo
sudo cp /home/study-and-learn/deploy/study-and-learn.service /etc/systemd/system/

# The gunicorn.conf.py is already in the project root (used by the service via -c flag)
# Verify it exists:
ls -la /home/study-and-learn/gunicorn.conf.py
```

**What's in these files:**

`deploy/study-and-learn.service` — the systemd unit:
```ini
[Unit]
Description=Study-and-Learn Flask Application (Gunicorn)
After=network.target postgresql.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/home/study-and-learn
Environment="PATH=/home/study-and-learn/venv/bin"
EnvironmentFile=-/home/study-and-learn/.env
ExecStart=/home/study-and-learn/venv/bin/gunicorn -c gunicorn.conf.py app:app
Restart=on-failure
RestartSec=10

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

`gunicorn.conf.py` — the Gunicorn config (extracted from the systemd unit for clarity):
```python
bind = "127.0.0.1:5000"
workers = 1
worker_class = "gthread"
threads = 8
timeout = 7200  # 2 hours — lesson generation with cloud AI can take 45-90 min
max_requests = 1000
max_requests_jitter = 100
accesslog = "/home/study-and-learn/logs/access.log"
errorlog = "/home/study-and-learn/logs/error.log"
loglevel = "info"
proc_name = "study-and-learn"
daemon = False
pidfile = "/tmp/study-and-learn.pid"
```

> **Why 1 worker + 8 threads (gthread)?**  
> The app uses `cachelib.FileSystemCache` for Flask sessions (`data/flask_session/`) and progress tracking (`data/progress_cache/`). These are per-process filesystem caches. Multiple Gunicorn workers would split the cache and break session/progress consistency. A single worker with 8 threads keeps all caching in one process and trivially handles 3 concurrent users.
>
> **Why `--timeout 7200` (2 hours)?**  
> Lesson generation with cloud AI (gemma3:27b-cloud) and 3+ modules can take 45-90 minutes end-to-end (lessons + checkpoints + quiz + narration script + edge-tts audio). The 2-hour timeout ensures Gunicorn doesn't kill long-running generation requests. The app's own JS hard-timeout is also 2 hours and stops polling without redirecting.
>
> **Why `--bind 127.0.0.1:5000`?**  
> Gunicorn binds to localhost only. Nginx (the public-facing reverse proxy) forwards external traffic to Gunicorn. This means port 5000 is never exposed to the internet directly.

### Step 7.2: Enable and Start Service

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

### Step 7.3: Verify Application

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

## 8. Configure Nginx (Reverse Proxy)

### Step 8.1: Copy Nginx Configuration from Repo

```bash
sudo cp /home/study-and-learn/deploy/nginx.conf /etc/nginx/sites-available/study-and-learn
```

**What's in this file:**

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name study-and-learn.duckdns.org;  # Replace with your DuckDNS domain or droplet IP

    # Upload size limit — must be >= your max PDF upload size
    # The app caps at 5 files per upload; set this generously
    client_max_body_size 50M;

    # Logging
    access_log /var/log/nginx/study-and-learn-access.log;
    error_log /var/log/nginx/study-and-learn-error.log;

    # Static files served directly by Nginx (faster than Flask)
    location /static/ {
        alias /home/study-and-learn/src/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # All other requests → Gunicorn
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for long-running lesson generation (up to 2 hours)
        proxy_connect_timeout 300s;
        proxy_send_timeout 7200s;
        proxy_read_timeout 7200s;
    }
}
```

> If your DuckDNS domain differs from `study-and-learn.duckdns.org`, edit the `server_name` line:
> ```bash
> sudo nano /etc/nginx/sites-available/study-and-learn
> ```

### Step 8.2: Enable Site

```bash
# Enable site
sudo ln -sf /etc/nginx/sites-available/study-and-learn /etc/nginx/sites-enabled/

# Remove default site
sudo rm -f /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Restart Nginx
sudo systemctl enable nginx
sudo systemctl restart nginx
```

**Expected output of `nginx -t`:**
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### Step 8.3: Test Without SSL First

Open your browser and go to: `http://study-and-learn.duckdns.org`

**You should see the Study-and-Learn login page!**

If not, check:
```bash
sudo systemctl status study-and-learn
sudo systemctl status nginx
sudo journalctl -u study-and-learn -n 50 --no-pager
sudo tail -20 /var/log/nginx/study-and-learn-error.log
```

### Step 8.4: Obtain SSL Certificate (Let's Encrypt)

```bash
# First run WITHOUT --redirect (obtains the certificate)
sudo certbot --nginx -d study-and-learn.duckdns.org --email your-email@example.com --agree-tos

# Then run WITH --redirect (forces all HTTP → HTTPS)
sudo certbot --nginx -d study-and-learn.duckdns.org --email your-email@example.com --agree-tos --redirect
```

**Replace `your-email@example.com`** with your actual email.

### Step 8.5: Configure Firewall

```bash
# Allow HTTP/HTTPS
sudo ufw allow 'Nginx Full'

# Allow SSH
sudo ufw allow OpenSSH

# Enable firewall
sudo ufw enable
```

**Type `y`** when prompted.

> **Note:** We do NOT open port 5000 in the firewall. Gunicorn is bound to `127.0.0.1:5000` (localhost only) and is never exposed to the internet. All external traffic goes through Nginx on ports 80/443.

### Step 8.6: Verify HTTPS

Open browser and go to: `https://study-and-learn.duckdns.org`

**You should see the login page with the padlock icon!**

Log in with the seed credentials (`admin` / `ADMINpassword`) and verify you can navigate the app.

---

## 9. Configure DuckDNS Automatic Updates

Your IP might change. DuckDNS keeps your domain updated.

### Step 9.1: Create DuckDNS Script

**On the droplet:**

```bash
mkdir -p ~/duckdns
cd ~/duckdns
nano duck.sh
```

**Paste this** (replace YOUR_TOKEN and YOUR_DOMAIN):

```bash
#!/bin/bash
TOKEN="your-duckdns-token-here"
DOMAIN="study-and-learn"
echo url="https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=" | curl -k -o ~/duckdns/duck.log -K -
```

**Save and exit** (`Ctrl+O`, Enter, `Ctrl+X`)

### Step 9.2: Make Executable and Test

```bash
chmod 700 duck.sh
./duck.sh
cat duck.log
```

**Expected output:** `OK`

### Step 9.3: Set Up Cron Job

```bash
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -
```

**Verify:**
```bash
crontab -l
```

Should show: `*/5 * * * * /root/duckdns/duck.sh >/dev/null 2>&1`

---

## 10. Configure GitHub Secrets for CI/CD

Your GitHub Actions workflow (`.github/workflows/ci-cd.yml`) is a 3-job pipeline that runs on every push/PR to `main`. The deploy and smoke-test jobs require **3 secrets** to SSH into your droplet.

### Step 10.1: Get Your Droplet IP (DO_SSH_HOST)

1. Go to https://cloud.digitalocean.com/droplets
2. Find your droplet
3. Copy the **IP address** (e.g., `134.209.11.38`)

**This is your `DO_SSH_HOST`**

### Step 10.2: SSH Username (DO_SSH_USER)

**Default:** `root`

Unless you created a different user, this is always:
```
root
```

**This is your `DO_SSH_USER`**

### Step 10.3: Create SSH Key for GitHub Actions

**On your LOCAL Windows machine (Git Bash):**

```bash
# Create new SSH key
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions_do
```

**Press Enter twice** (no passphrase)

**Copy the PUBLIC key to your droplet:**

```bash
ssh-copy-id -i ~/.ssh/github_actions_do.pub root@YOUR_DROPLET_IP
```

**Enter droplet password** when prompted.

**Expected output:** `Number of key(s) added: 1`

**Test it:**

```bash
ssh -i ~/.ssh/github_actions_do root@YOUR_DROPLET_IP
```

**Should log in without password!**

**Display the PRIVATE key:**

```bash
cat ~/.ssh/github_actions_do
```

**Copy the ENTIRE output** (including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`)

**This is your `DO_SSH_PRIVATE_KEY`**

### Step 10.4: Add Secrets to GitHub

1. Go to: https://github.com/stephen-cpe/study-and-learn/settings/secrets/actions

2. Click **"New repository secret"** (green button)

3. Add these 3 secrets:

| Name | Value | Example |
|------|-------|---------|
| `DO_SSH_HOST` | Your droplet IP | `134.209.11.38` |
| `DO_SSH_USER` | SSH username | `root` |
| `DO_SSH_PRIVATE_KEY` | Entire private key file | `-----BEGIN OPENSSH PRIVATE KEY-----...` |

4. Click **"Add secret"** for each

5. **Verify** all 3 secrets are listed

> **Why no `SECRET_KEY` or API keys in GitHub Secrets?**  
> Like the malware-detector pattern, `SECRET_KEY`, `OLLAMA_CLOUD_API_KEY`, and `CHROMA_CLOUD_API_KEY` live only on the droplet in `.env` — they are NOT in GitHub Secrets and NOT deployed by CI/CD. CI/CD only deploys code (`git pull` + `pip install` + `systemctl restart`). This keeps secrets off GitHub entirely.

---

## 11. Test Deployment

### Step 11.1: Understand the CI/CD Pipeline

Your workflow (`.github/workflows/ci-cd.yml`) has **3 jobs** that run sequentially:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   TEST      │────▶│   DEPLOY    │────▶│ SMOKE TEST  │
│ (Run tests) │     │ (SSH + pull)│     │ (curl /health)│
└─────────────┘     └─────────────┘     └─────────────┘
```

| Job | What It Does | Runs When |
|-----|--------------|-----------|
| **test** | `pytest` with `AI_MOCK=true`, `CI=true`, `DATABASE_URL` + `poppler-utils` | Every push/PR to `main` |
| **deploy** | SSH to droplet, `git reset --hard origin/main`, recreate venv, `pip install`, `systemctl restart` | Only on `main` push, if test passes |
| **smoke-test** | `curl https://study-and-learn.duckdns.org/health`, assert HTTP 200 | Only on `main` push, if deploy succeeds |

> **What the deploy job does NOT do:** It does NOT run `init_db.sql` (one-time manual setup), does NOT touch `.env` (stays on the droplet), and does NOT run model training (AI is via Ollama Cloud). It only deploys code and restarts the service.

### Step 11.2: Trigger Your First Deployment

**On your LOCAL machine:**

```bash
# Make sure you're on main branch
git checkout main

# Make a small change (e.g., edit README.md)
git add .
git commit -m "Test CI/CD deployment"
git push origin main
```

### Step 11.3: Monitor the Deployment

1. Go to: https://github.com/stephen-cpe/study-and-learn/actions
2. Click on the running workflow
3. Watch each job complete (green checkmarks):
   - **test** — runs pytest (426+ tests, ~4-6 min)
   - **deploy** — SSH to droplet, pull code, recreate venv, restart service (~1-2 min)
   - **smoke-test** — curl /health, verify HTTP 200 (~30 sec)

**What to look for:**
```
CI/CD Pipeline
   ├── test  ✅
   ├── deploy  ✅
   └── smoke-test  ✅
```

### Step 11.4: Verify Deployment

**Test the smoke-test endpoint from your browser:**
```
https://study-and-learn.duckdns.org/health
```

**Expected response:**
```json
{"status":"healthy"}
```

**Verify on your droplet:**

```bash
# SSH to your droplet
ssh root@YOUR_DROPLET_IP

# Check if code was updated
cd /home/study-and-learn
git log -1

# Check service status
sudo systemctl status study-and-learn

# Check the health endpoint locally
curl http://127.0.0.1:5000/health
```

**Your app is deployed with CI/CD.** Every future `git push origin main` will automatically test, deploy, and verify.

---

## 12. Concurrency Test (3 Simultaneous Users)

This is the capstone-specific test — verify 3 users can use the app at the same time.

### Manual Test (3 Browser Sessions):

1. Open 3 separate browser sessions (3 incognito windows, or 3 different browsers)
2. Log in as `admin`, `bob`, and `alice` (one per session)
3. In each session, upload a small PDF and click **Generate**
4. All 3 should see the progress page with the mascot animating
5. All 3 progress bars should advance independently
6. None should show another user's data

### What to check:
- **Sessions stay isolated:** User A does not see User B's study paths or dashboard
- **Progress polls work:** The `/progress` cosmetic poll updates each user's mascot independently
- **Generation completes:** The `generation_completed_at` DB column is set per-path, and each user redirects to their own `/lessons` page when done
- **No 500 errors:** Check `logs/error.log` and `journalctl -u study-and-learn`

> **If progress bars flicker or sessions cross:** This would indicate a multi-worker issue. Verify the systemd service is using `--workers 1` (single process). Run `sudo systemctl cat study-and-learn` to confirm.

---

## 13. Shutdown Plan (Post-Capstone)

Since this is a temporary 3-4 week deployment:

1. **Power off the droplet** (not destroy) if you might need it again:
   - DigitalOcean Dashboard → Droplets → Power Off
   - You stop paying for CPU/RAM but keep the disk (small charge)

2. **Destroy the droplet** when completely done:
   - DigitalOcean Dashboard → Droplets → Destroy
   - Stops all charges

3. **Optional: Take a snapshot** before destroying:
   - DigitalOcean Dashboard → Droplets → Snapshots → Take Snapshot
   - Lets you restore the exact state later (snapshot storage is cheap)

4. **Revoke credentials when done:**
   - Rotate or revoke the Ollama Cloud API key
   - Rotate or revoke the Chroma Cloud API key
   - Remove the `DO_SSH_PRIVATE_KEY` from GitHub Secrets
   - Delete the DuckDNS domain if no longer needed

---

## Troubleshooting

### App Won't Start

**Error:** `RuntimeError: DATABASE_URL environment variable is required`

**Fix:**
1. Verify `.env` exists: `ls -la /home/study-and-learn/.env`
2. Verify it has `DATABASE_URL=postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn`
3. Verify permissions: `chmod 600 .env`
4. Restart: `sudo systemctl restart study-and-learn`
5. Check logs: `sudo journalctl -u study-and-learn -n 50 --no-pager`

### App Won't Start

**Error:** `RuntimeError: DATABASE_URL must use PostgreSQL`

**Fix:** The `DATABASE_URL` must start with `postgresql`. Check for typos in `.env`.

### Database Connection Failed

**Error:** `psycopg2.OperationalError: could not connect to server`

**Fix:**
1. Verify PostgreSQL is running: `sudo systemctl status postgresql`
2. Verify the database exists: `sudo -u postgres psql -l | grep study_and_learn`
3. Verify the user can connect: `psql -U study_user -d study_and_learn -h localhost`
4. If password is wrong, reset it:
   ```bash
   sudo -u postgres psql
   ALTER USER study_user WITH PASSWORD 'study_pass';
   \q
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
1. Verify DuckDNS is pointing to your droplet: `ping study-and-learn.duckdns.org`
2. Verify Nginx is running and port 80 is open: `sudo ufw status`
3. Wait 5 minutes for DNS propagation, then retry certbot

### Tests Fail Locally

**Error:** `ModuleNotFoundError: No module named 'flask'`

**Fix:** Activate your virtual environment first:
```bash
# Windows
venv\Scripts\activate

# Then run tests
pytest -v tests/
```

### Deployment Runs But Doesn't Update

**Check:**
1. SSH key is authorized: `cat ~/.ssh/authorized_keys` (on droplet)
2. Directory exists: `ls -la /home/study-and-learn`
3. Service restarts: `sudo systemctl status study-and-learn`
4. Git pull works: `cd /home/study-and-learn && git pull origin main`
5. Gunicorn restarted after pull: The CI/CD workflow must restart the service after `git pull`

### Lesson Generation Hangs

**Symptom:** Progress page stays at "Building lesson..." for a long time

**This is expected with cloud AI.** Full generation with `gemma3:27b-cloud` and 3+ modules can take 45-90 minutes. The JS hard-timeout is 2 hours and will show a "still working" message without redirecting. Check:

1. Is Ollama Cloud reachable? `curl -H "Authorization: Bearer $OLLAMA_CLOUD_API_KEY" https://ollama.com/api/tags`
2. Check app logs: `tail -50 /home/study-and-learn/logs/error.log`
3. Check the DB column: `psql -U study_user -d study_and_learn -c "SELECT id, generation_completed_at FROM study_paths ORDER BY created_at DESC LIMIT 5;"`
4. If `generation_completed_at` is NULL after 2 hours, the TTS worker may have crashed — check logs for `tts-` thread errors.

---