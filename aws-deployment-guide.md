# AWS EC2 Deployment Guide
## For AWS EC2 m7i-flex.large (2 vCPU / 8 GB RAM / 40 GB gp3) + DuckDNS + Let's Encrypt SSL
### Complete Guide for Windows 11 Users

## Disclaimer
_This guide is a work in progress. Use at your own risk. No warranties, guarantees, or support are provided._

---

## Overview

This guide walks you through deploying the Study-and-Learn Flask application to AWS EC2 with:
-  **Automated CI/CD** via GitHub Actions
-  **HTTPS/SSL** with Let's Encrypt
-  **Dynamic DNS** with DuckDNS
-  **Gunicorn** (gthread, 1 worker, 8 threads) + **Nginx** reverse proxy
-  **PostgreSQL** + **Chroma Cloud** + **Ollama Cloud** (all heavy AI offloaded)
-  **Windows 11** compatible (uses Git Bash)

**Time Required:** 60-90 minutes  
**Cost:** ~$28-35/month (EC2 m7i-flex.large, 2 vCPU / 8 GB RAM / 40 GB gp3; or free with AWS trial credits)

> **Why gthread (1 worker, 8 threads) instead of multi-worker?**  
> The app uses `cachelib.FileSystemCache` for Flask sessions (`data/flask_session/`) and progress tracking (`data/progress_cache/`). These are per-process filesystem caches. Multiple Gunicorn workers would split the cache and break session/progress consistency. A single worker with 8 threads keeps all caching in one process and trivially handles 3 concurrent users.

> **Instance sizing note:** The m7i-flex.large (2 vCPU / 8 GB RAM / 40 GB gp3) is sufficient because heavy AI inference runs on Ollama Cloud (`AI_BACKEND=cloud`) and vector storage on Chroma Cloud (`CHROMA_DB=cloud`). The EC2 instance only runs Flask/Gunicorn, Nginx, and PostgreSQL. The app is I/O-bound (waiting on cloud API responses), so 2 vCPUs handle 3 concurrent users without bottlenecking. The 40 GB gp3 volume provides headroom for OS (~6 GB), venv (~2 GB), PostgreSQL (~1 GB), and ~10 GB of TTS audio + uploads (enough for a 3-4 week capstone deployment).

---

## Prerequisites

### What You Need:
1. **AWS Account** - https://aws.amazon.com (free tier or trial credits)
2. **GitHub Account** - https://github.com
3. **DuckDNS Account** - https://duckdns.org (free)
4. **Git for Windows** - https://git-scm.com/download/win (includes Git Bash)
5. **Ollama Cloud API Key** - https://ollama.com (for `AI_BACKEND=cloud`)
6. **Chroma Cloud Credentials** - https://chromadb.com (API key, tenant ID, collection name)

---

## 1. Create an AWS EC2 Instance

### Step-by-Step:

1. Log in to https://console.aws.amazon.com
2. Go to **EC2** → **Instances** → **Launch instances**
3. Choose the following configuration:
   - **Name**: `studyandlearn-aws`
   - **AMI**: Ubuntu Server 26.04 LTS (64-bit x86)
   - **Instance type**: `m7i-flex.large` (2 vCPU / 8 GB RAM)
   - **Key pair**: Create a new key pair (RSA, `.pem` format) — name it `aws-ec2-key` — download and save it (you cannot download it again)
   - **Storage**: 40 GB gp3 (EBS volume)
   - **Network settings**: Create or select a security group with the following inbound rules (see Step 1.1 below)
4. Click **Launch instance**
5. Wait 1-2 minutes for provisioning
6. Note your instance's **Public IPv4 address** (shown in the EC2 Instances list)

### Step 1.1: Configure Security Group (AWS Firewall)

AWS uses **security groups** instead of UFW for firewall management. You must create these inbound rules before the instance is usable:

| Type | Port | Source | Purpose |
|------|------|--------|---------|
| SSH | 22 | My IP (or `0.0.0.0/0` for testing) | SSH access |
| HTTP | 80 | `0.0.0.0/0` | Web traffic (Let's Encrypt + redirect) |
| HTTPS | 443 | `0.0.0.0/0` | Secure web traffic |

**To configure:**
1. During instance launch, under **Network settings** → **Security group**, click **Create security group**
2. Name it `studyandlearn-sg`
3. Add the 3 inbound rules above
4. Outbound rules: leave default (allow all)

> **Note:** We do NOT open port 5000 in the security group. Gunicorn is bound to `127.0.0.1:5000` (localhost only) and is never exposed to the internet. All external traffic goes through Nginx on ports 80/443.

### Step 1.2: Allocate an Elastic IP (Optional but Recommended)

AWS EC2 instances get a new public IP on every stop/start. An Elastic IP gives you a fixed IP that survives reboots:

1. Go to **EC2** → **Elastic IPs** → **Allocate Elastic IP address**
2. Click **Allocate**
3. Select the new Elastic IP → **Actions** → **Associate Elastic IP address**
4. Select your `studyandlearn-aws` instance
5. Click **Associate**
6. Note the **Elastic IP** — this is your instance's permanent public IP

> **Cost note:** Elastic IPs are free while associated with a running instance. They incur a small hourly charge if allocated but NOT associated. For a 3-4 week capstone deployment, this is effectively free.

---

## 2. Configure DuckDNS

1. Go to https://duckdns.org
2. Sign in with GitHub/Google
3. In the domain field, type: `studyandlearnaws` (without .duckdns.org)
4. Click **Add Domain**
5. Update the IP address:
   - Enter your EC2 instance's Public IPv4 address (or Elastic IP)
   - Click **Update IP**
6. Note your **DuckDNS Token** (click "token" link) - you'll need this later

**Keep this page open** or save:
- Domain: `studyandlearnaws.duckdns.org`
- Token: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- IP: `54.209.11.38` (example)

---

## 3. Connect to Your EC2 Instance

### Using Git Bash (Windows):

First, set permissions on your downloaded `.pem` key file (AWS requires strict permissions):

```bash
# Move the downloaded key to your .ssh directory
mv ~/Downloads/aws-ec2-key.pem ~/.ssh/aws-ec2-key.pem
chmod 600 ~/.ssh/aws-ec2-key.pem

# Connect (AWS Ubuntu AMIs use 'ubuntu' as the default user, not 'root')
ssh -i ~/.ssh/aws-ec2-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```

**First time?** You'll see:
```
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```
Type `yes` and press Enter.

> **Important AWS difference:** AWS Ubuntu AMIs use `ubuntu` as the default SSH user, NOT `root`. You will use `sudo` for commands that need root privileges. This is a security best practice — you should NOT enable root SSH login.

### Using AWS EC2 Instance Connect (Alternative):

If SSH fails:
1. Go to AWS Console → EC2 → Instances
2. Select your instance
3. Click **Connect** → **EC2 Instance Connect**
4. Click **Connect**
5. You get a browser-based terminal logged in as `ubuntu`

---

## 4. Prepare the Server

**Once connected via SSH**, run these commands on the EC2 instance:

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

**On the EC2 instance:**

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

> **Why `sudo -u postgres`?** On Ubuntu, PostgreSQL defaults to *peer authentication* for local socket connections — the OS user running `psql` must match the database username. Running `psql -U postgres` as `ubuntu` or `root` fails with `Peer authentication failed`. The fix is to run `psql` as the `postgres` OS user via `sudo -u postgres`.

This creates three seed accounts for testing:

| Username | Password       | Role  | Can generate lessons |
|----------|---------------|-------|----------------------|
| admin    | ADMINpassword | ADMIN | Yes                  |
| bob      | BOBpassword   | USER  | Yes                  |
| alice    | ALICEpassword | USER  | Yes                  |

> **Security note:** Change these seed passwords or remove the seed users from `init_db.sql` before deploying to the public internet. For a 3-4 week temporary capstone demo, the seed accounts are fine for testing.

### Step 6.3: Install Ollama and Pull the Embedding Model

The app uses Ollama Cloud (`AI_BACKEND=cloud`) for all chat/completion calls, but the ChromaDB vector store uses a **local Ollama embedding model** (`qwen3-embedding:0.6b`) to embed query text during RAG retrieval. This model is tiny (~600 MB) and runs in CPU-only mode — no GPU needed.

Without this model, the RAG retrieval pipeline silently fails: ChromaDB cannot embed the learning goal query, so it returns empty context and empty sources. The app generates lessons without document-grounded context (pure LLM hallucination), and the "View Sources" button never appears.

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull ONLY the embedding model (tiny, ~600 MB, CPU-only)
ollama pull qwen3-embedding:0.6b

# Verify it works
ollama run qwen3-embedding:0.6b "test embedding"

# Verify Ollama is running on localhost:11434
curl http://localhost:11434/api/tags
```

**Expected output of the tags check:**
```json
{"models":[{"name":"qwen3-embedding:0.6b", ...}]}
```

> **Why local Ollama for embeddings when AI_BACKEND=cloud?**  
> Ollama Cloud's API only supports the OpenAI-compatible `/v1/chat/completions` endpoint. The `langchain_ollama.OllamaEmbeddings` class uses the native Ollama `/api/embed` endpoint, which is not exposed by Ollama Cloud. So embedding calls must go to a local Ollama instance. The `qwen3-embedding:0.6b` model is tiny (~600 MB) and runs in CPU-only mode — it won't compete with the app for resources.
>
> **What about the chat model?** Chat/completion calls (lesson generation, quiz generation, relevance checks) go through `ai_client_cloud.py` to Ollama Cloud (`AI_BACKEND=cloud`, `OLLAMA_MODEL=gemma3:27b-cloud`). You do NOT need to pull `gemma3:27b-cloud` locally — only the embedding model.

### Step 6.4: Create Environment File

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
# Secure the file (only owner can read it)
chmod 600 .env
```

> **Why `AI_BACKEND=cloud` and `CHROMA_DB=cloud`?**  
> Running local AI models (e.g., a 27B parameter LLM) on an 8 GB RAM instance would cause OOM crashes. Ollama Cloud offloads all LLM inference to Ollama's hosted infrastructure. Chroma Cloud offloads vector storage and similarity search. The EC2 instance only orchestrates HTTP requests, DB reads/writes, and the background TTS worker thread — all lightweight CPU work.

### Step 6.5: Create Logs and Data Directories

```bash
cd /home/study-and-learn
mkdir -p logs
touch logs/access.log logs/error.log
mkdir -p data/flask_session data/progress_cache data/uploads data/tts data/chroma_db
```

> These directories are created automatically by the app on startup, but creating them now avoids first-run permission issues.

### Step 6.6: Verify the App Starts

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

# Raise the file descriptor limit from the Linux default (1024) to 65536.
# The default 1024 is too low for a Gunicorn gthread worker doing async I/O:
# the two-poll JS design opens 2 HTTP connections per 2s tick, TTS generation
# opens WebSocket+SSL sockets to Microsoft Edge-TTS (1 per slide), and
# FileSystemCache + PostgreSQL hold FDs open. Without this, the worker
# crashes with OSError: [Errno 24] Too many open files during long
# TTS-enabled lesson generations.
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

> **AWS note:** The systemd unit uses `User=root`. On AWS Ubuntu AMIs, the default SSH user is `ubuntu`, but the systemd service runs as `root` — this is correct. The `User=root` in the service file refers to the user the Gunicorn process runs as, not who you SSH in as.

`gunicorn.conf.py` — the Gunicorn config:
```python
bind = "127.0.0.1:5000"
workers = 1
worker_class = "gthread"
threads = 8
timeout = 7200  # 2 hours — lesson generation with cloud AI can take 45-90 min

# NOTE: max_requests / max_requests_jitter are deliberately omitted.
# The two-poll JS design fires ~1-2 HTTP requests per second. With
# max_requests=1000, the worker auto-restarts every ~15-20 minutes,
# killing the TTS background thread mid-generation.

# Logging
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
> **Why `timeout 7200` (2 hours)?**  
> Lesson generation with cloud AI (gemma3:27b-cloud) and 3+ modules can take 45-90 minutes end-to-end (lessons + checkpoints + quiz + narration script + edge-tts audio). The 2-hour timeout ensures Gunicorn doesn't kill long-running generation requests. The app's own JS hard-timeout is also 2 hours and stops polling without redirecting.
>
> **Why no `max_requests`?**  
> The two-poll JS design fires ~1-2 HTTP requests per second. With `max_requests=1000`, the worker would auto-restart every ~15-20 minutes, killing the daemon TTS background thread mid-generation. TTS-enabled generation takes 45-90 minutes; the worker must stay alive for the entire duration.
>
> **Why `bind 127.0.0.1:5000`?**  
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

**Then update the `server_name` to match your DuckDNS domain:**

```bash
sudo nano /etc/nginx/sites-available/study-and-learn
```

Change the `server_name` line to:
```nginx
    server_name studyandlearnaws.duckdns.org;
```

**Save and exit** (`Ctrl+O`, Enter, `Ctrl+X`)

**What's in this file:**

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name studyandlearnaws.duckdns.org;  # Your DuckDNS domain

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

> **⚠️ WARNING: This repo config is HTTP-only (port 80).** It does NOT contain SSL directives — those are added by Certbot in Step 8.4. If you ever re-copy this file to `/etc/nginx/sites-available/` (e.g., after a config change), you **MUST re-run the Certbot commands in Step 8.4** afterward to restore the SSL block (`listen 443 ssl`, certificate paths, and HTTP→HTTPS redirect). Otherwise HTTPS will break. This is a one-time manual step — CI/CD does NOT touch the live Nginx config.

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

Open your browser and go to: `http://studyandlearnaws.duckdns.org`

**You should see the Study-and-Learn login page!**

If not, check:
```bash
sudo systemctl status study-and-learn
sudo systemctl status nginx
sudo journalctl -u study-and-learn -n 50 --no-pager
sudo tail -20 /var/log/nginx/study-and-learn-error.log
```

> **AWS-specific check:** If the page doesn't load, verify your EC2 security group allows inbound HTTP (port 80) from `0.0.0.0/0`. Go to AWS Console → EC2 → Security Groups → your security group → Inbound Rules.

### Step 8.4: Obtain SSL Certificate (Let's Encrypt)

```bash
# First run WITHOUT --redirect (obtains the certificate)
sudo certbot --nginx -d studyandlearnaws.duckdns.org --email your-email@example.com --agree-tos

# Then run WITH --redirect (forces all HTTP → HTTPS)
sudo certbot --nginx -d studyandlearnaws.duckdns.org --email your-email@example.com --agree-tos --redirect
```

**Replace `your-email@example.com`** with your actual email.

### Step 8.5: Verify HTTPS

Open browser and go to: `https://studyandlearnaws.duckdns.org`

**You should see the login page with the padlock icon!**

Log in with the seed credentials (`admin` / `ADMINpassword`) and verify you can navigate the app.

> **Note:** On AWS, you do NOT need to configure UFW (Uncomplicated Firewall). AWS security groups handle all firewall management at the hypervisor level. The security group rules you set in Step 1.1 (ports 22/80/443) are the only firewall configuration needed.

---

## 9. Configure DuckDNS Automatic Updates

Your IP might change (especially without an Elastic IP). DuckDNS keeps your domain updated.

### Step 9.1: Create DuckDNS Script

**On the EC2 instance:**

```bash
mkdir -p ~/duckdns
cd ~/duckdns
nano duck.sh
```

**Paste this** (replace YOUR_TOKEN and YOUR_DOMAIN):

```bash
#!/bin/bash
TOKEN="your-duckdns-token-here"
DOMAIN="studyandlearnaws"
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

Should show: `*/5 * * * * /home/ubuntu/duckdns/duck.sh >/dev/null 2>&1`

> **AWS note:** The cron path will be `/home/ubuntu/duckdns/duck.sh` (not `/root/`) because AWS Ubuntu AMIs use `ubuntu` as the default user.

---

## 10. Configure GitHub Secrets for CI/CD

Your GitHub Actions workflow (`.github/workflows/ci-cd.yml`) is a 3-job pipeline that runs on every push/PR to `main`. The deploy and smoke-test jobs require **3 secrets** to SSH into your EC2 instance.

> **AWS note:** The CI/CD workflow's smoke-test job hits `https://studyandlearn.duckdns.org/health` (the DigitalOcean domain). If you want the smoke-test to verify the AWS deployment instead, you need to either:
> - Create a separate workflow for AWS (e.g., `ci-cd-aws.yml`) with the AWS domain, OR
> - Update the existing workflow's smoke-test URL to `https://studyandlearnaws.duckdns.org/health`, OR
> - Keep the smoke-test pointed at the DigitalOcean deployment (if both are running simultaneously)
>
> For a single-target AWS deployment, the simplest approach is to update the smoke-test URL in `ci-cd.yml`.

### Step 10.1: Get Your EC2 Public IP (AWS_SSH_HOST)

1. Go to AWS Console → EC2 → Instances
2. Find your instance
3. Copy the **Public IPv4 address** (or Elastic IP, if allocated)

**This is your `AWS_SSH_HOST`**

### Step 10.2: SSH Username (AWS_SSH_USER)

**Default for AWS Ubuntu AMIs:** `ubuntu`

```
ubuntu
```

> **AWS difference:** AWS Ubuntu AMIs use `ubuntu` as the default SSH user, NOT `root` (which is the DigitalOcean default). The CI/CD workflow's `username` field must be set to `ubuntu` for AWS.

**This is your `AWS_SSH_USER`**

### Step 10.3: Create SSH Key for GitHub Actions

**On your LOCAL Windows machine (Git Bash):**

```bash
# Create new SSH key
ssh-keygen -t ed25519 -C "github-actions-deploy-aws" -f ~/.ssh/github_actions_aws
```

**Press Enter twice** (no passphrase)

**Copy the PUBLIC key to your EC2 instance:**

```bash
ssh-copy-id -i ~/.ssh/github_actions_aws.pub ubuntu@YOUR_EC2_PUBLIC_IP
```

> **AWS note:** You may need to specify the EC2 key pair to connect first:
> ```bash
> ssh-copy-id -i ~/.ssh/github_actions_aws.pub -o IdentityFile=~/.ssh/aws-ec2-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
> ```

**Enter the EC2 instance password** when prompted (or if using key-based auth only, this should work automatically).

**Expected output:** `Number of key(s) added: 1`

**Test it:**

```bash
ssh -i ~/.ssh/github_actions_aws ubuntu@YOUR_EC2_PUBLIC_IP
```

**Should log in without password!**

**Display the PRIVATE key:**

```bash
cat ~/.ssh/github_actions_aws
```

**Copy the ENTIRE output** (including `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----`)

**This is your `AWS_SSH_PRIVATE_KEY`**

### Step 10.4: Add Secrets to GitHub

1. Go to: https://github.com/stephen-cpe/study-and-learn/settings/secrets/actions

2. Click **"New repository secret"** (green button)

3. Add these 3 secrets:

| Name | Value | Example |
|------|-------|---------|
| `AWS_SSH_HOST` | Your EC2 public IP | `54.209.11.38` |
| `AWS_SSH_USER` | SSH username | `ubuntu` |
| `AWS_SSH_PRIVATE_KEY` | Entire private key file | `-----BEGIN OPENSSH PRIVATE KEY-----...` |

4. Click **"Add secret"** for each

5. **Verify** all 3 secrets are listed

> **Why no `SECRET_KEY` or API keys in GitHub Secrets?**  
> `SECRET_KEY`, `OLLAMA_CLOUD_API_KEY`, and `CHROMA_CLOUD_API_KEY` live only on the EC2 instance in `.env` — they are NOT in GitHub Secrets and NOT deployed by CI/CD. CI/CD only deploys code (`git pull` + `pip install` + `systemctl restart`). This keeps secrets off GitHub entirely.

> **CI/CD workflow note:** The current `ci-cd.yml` uses `DO_SSH_HOST`, `DO_SSH_USER`, `DO_SSH_PRIVATE_KEY` secrets and deploys to DigitalOcean. To deploy to AWS instead, either:
> 1. Update the workflow to use `AWS_SSH_HOST`, `AWS_SSH_USER`, `AWS_SSH_PRIVATE_KEY`, OR
> 2. Reuse the existing `DO_SSH_*` secret names but put the AWS values in them, OR
> 3. Create a separate `ci-cd-aws.yml` workflow for the AWS deployment
>
> The simplest approach for a single-target migration: reuse the existing `DO_SSH_*` secret names and put the AWS values in them. The workflow code doesn't need to change — only the secret values and the smoke-test URL.

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
| **deploy** | SSH to instance, `git reset --hard origin/main`, recreate venv, `pip install`, `systemctl restart` | Only on `main` push, if test passes |
| **smoke-test** | `curl https://studyandlearnaws.duckdns.org/health`, assert HTTP 200 | Only on `main` push, if deploy succeeds |

> **What the deploy job does NOT do:** It does NOT run `init_db.sql` (one-time manual setup), does NOT touch `.env` (stays on the instance), and does NOT run model training (AI is via Ollama Cloud). It only deploys code and restarts the service.

### Step 11.2: Trigger Your First Deployment

**On your LOCAL machine:**

```bash
# Make sure you're on main branch
git checkout main

# Make a small change (e.g., edit README.md)
git add .
git commit -m "Test AWS CI/CD deployment"
git push origin main
```

### Step 11.3: Monitor the Deployment

1. Go to: https://github.com/stephen-cpe/study-and-learn/actions
2. Click on the running workflow
3. Watch each job complete (green checkmarks):
   - **test** — runs pytest (427+ tests, ~4-6 min)
   - **deploy** — SSH to EC2, pull code, recreate venv, restart service (~1-2 min)
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
https://studyandlearnaws.duckdns.org/health
```

**Expected response:**
```json
{"status":"healthy"}
```

**Verify on your EC2 instance:**

```bash
# SSH to your EC2 instance
ssh -i ~/.ssh/aws-ec2-key.pem ubuntu@YOUR_EC2_PUBLIC_IP

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
- **No file descriptor exhaustion:** Monitor `ls /proc/$(pgrep -f gunicorn | tail -1)/fd 2>/dev/null | wc -l` during generation — should stay well under 65536

> **If progress bars flicker or sessions cross:** This would indicate a multi-worker issue. Verify the systemd service is using `--workers 1` (single process). Run `sudo systemctl cat study-and-learn` to confirm.

---

## 13. Shutdown Plan (Post-Capstone)

Since this is a temporary 3-4 week deployment:

1. **Stop the EC2 instance** (not terminate) if you might need it again:
   - AWS Console → EC2 → Instances → Actions → Stop Instance
   - You stop paying for compute but still pay for EBS storage (~$0.08/GB-month for gp3)

2. **Terminate the EC2 instance** when completely done:
   - AWS Console → EC2 → Instances → Actions → Terminate Instance
   - Stops all charges (including EBS storage)
   - ⚠️ **This destroys all data** — take a snapshot first if you want to preserve anything

3. **Optional: Create an AMI snapshot** before terminating:
   - AWS Console → EC2 → Instances → Actions → Image and templates → Create image
   - Lets you launch a new instance with the same state later
   - AMI storage costs ~$0.05/GB-month

4. **Release the Elastic IP** (if allocated):
   - AWS Console → EC2 → Elastic IPs → Disassociate → Release Elastic IP address
   - ⚠️ Elastic IPs incur charges if allocated but NOT associated with a running instance

5. **Revoke credentials when done:**
   - Rotate or revoke the Ollama Cloud API key
   - Rotate or revoke the Chroma Cloud API key
   - Remove the `AWS_SSH_PRIVATE_KEY` (or `DO_SSH_PRIVATE_KEY`) from GitHub Secrets
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

### Cannot Connect to EC2 Instance (Timeout)

**Error:** SSH or browser connection times out

**Fix:**
1. Verify your EC2 security group allows inbound SSH (port 22), HTTP (port 80), and HTTPS (port 443)
2. Verify the instance is running: AWS Console → EC2 → Instances
3. Verify the Public IPv4 address is correct
4. Check if the instance has an Elastic IP — if it was stopped and restarted without an Elastic IP, the public IP changed (update DuckDNS)

### SSL Certificate Issues

**Error:** Certbot fails to verify domain

**Fix:**
1. Verify DuckDNS is pointing to your EC2 instance: `ping studyandlearnaws.duckdns.org`
2. Verify Nginx is running and port 80 is open: `sudo systemctl status nginx`
3. Verify the AWS security group allows inbound HTTP (port 80) from `0.0.0.0/0`
4. Wait 5 minutes for DNS propagation, then retry certbot

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
1. SSH key is authorized: `cat ~/.ssh/authorized_keys` (on EC2 instance)
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
4. If `generation_completed_at` is NULL after 2 hours, the TTS worker may have crashed — check logs for `tts-` thread errors or `OSError: [Errno 24] Too many open files`.

### TTS Generation Fails (Errno 24: Too many open files)

**Symptom:** Error log shows `OSError: [Errno 24] Too many open files` during TTS-enabled generation

**Fix:**
1. Verify `LimitNOFILE=65536` is in the systemd unit: `grep LimitNOFILE /etc/systemd/system/study-and-learn.service`
2. Verify the running process has the limit: `cat /proc/$(pgrep -f gunicorn | head -1)/limits | grep "Max open files"` — should show `65536`
3. Verify `max_requests` is NOT set in `gunicorn.conf.py`: `grep max_requests gunicorn.conf.py` — should show only the comment explaining why it's omitted
4. If the limit is still 1024, reload and restart:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart study-and-learn
   ```

---