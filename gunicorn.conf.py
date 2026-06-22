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

# NOTE: max_requests / max_requests_jitter are deliberately omitted.
# The two-poll JS design fires ~1-2 HTTP requests per second (cosmetic
# /progress + redirect /lessons/generation-status). With max_requests=1000,
# the worker would auto-restart every ~15-20 minutes — killing the daemon
# TTS background thread mid-generation. TTS-enabled generation takes 45-90
# minutes; the worker must stay alive for the entire duration. The TTS
# worker's finally block sets generation_completed_at; if the worker dies
# first, that never runs and the user is stuck on the results page forever.

# Logging
accesslog = "/home/study-and-learn/logs/access.log"
errorlog = "/home/study-and-learn/logs/error.log"
loglevel = "info"

# Process naming
proc_name = "study-and-learn"

# Server mechanics
daemon = False
pidfile = "/tmp/study-and-learn.pid"