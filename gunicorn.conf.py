# Gunicorn configuration file for Study-and-Learn
# Optimized for 4 vCPU / 8 GB RAM DigitalOcean droplet
#
# Usage:
#   gunicorn -c gunicorn.conf.py app:app
#
# The gthread single-worker model (1 worker, 8 threads) is required because
# the app uses cachelib.FileSystemCache for Flask sessions and progress
# tracking — these are per-process filesystem caches that would split across
# multiple Gunicorn workers, breaking session/progress consistency.
# 8 threads trivially handle 3 concurrent users (the capstone target).

bind = "127.0.0.1:5000"
workers = 1
worker_class = "gthread"
threads = 8
timeout = 7200  # 2 hours — lesson generation with cloud AI can take 45-90 min

# Restart the worker periodically to release any leaked memory
# (defense-in-depth; the app is short-lived and this is a temp deployment)
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = "/home/study-and-learn/logs/access.log"
errorlog = "/home/study-and-learn/logs/error.log"
loglevel = "info"

# Process naming
proc_name = "study-and-learn"

# Server mechanics
daemon = False
pidfile = "/tmp/study-and-learn.pid"