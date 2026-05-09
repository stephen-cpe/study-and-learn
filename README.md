# Study-and-Learn

A guided, form-driven AI web application that converts uploaded study materials into structured summaries, relevance assessments, and bite-sized learning paths.

## Tech Stack
- Python 3.13 + Flask
- Bootstrap 5 (frontend)
- Ollama (local AI serving)
- pytest + GitHub Actions (CI/CD)

## Ollama Setup

1. Install Ollama from https://ollama.com/download
2. Pull required models:
```bash
ollama pull qwen3:1.7b
ollama pull gemma3:4b
```

## Quick Start (Local Development)
```bash
# 1. Clone and enter repo
git clone https://github.com/stephen-cpe/study-and-learn.git
cd study-and-learn

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install --upgrade pip

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python run.py

# 5. Run tests
pytest -v tests/
```

## Links
- [Public Task Board](https://stephen-cpe.github.io/task-board-v1/)
- [Task Board Repository](https://github.com/stephen-cpe/task-board-v1/)
- [Deployed App](#) *(coming soon)*

## License
MIT — for educational purposes only.
