# Study-and-Learn

A Flask web application that converts uploaded study materials into structured summaries, study paths, interactive lessons, and auto-graded quizzes using AI.

## Prerequisites

1. Install Python 3.13 from https://python.org
2. Install Ollama from https://ollama.com/download
3. Install PostgreSQL from https://www.postgresql.org/download/windows

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/stephen-cpe/study-and-learn.git
cd study-and-learn
```

### 2. Create virtual environment

```bash
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up PostgreSQL database

Open PowerShell as Administrator and run:

```bash
# Connect to PostgreSQL as postgres superuser
psql -U postgres -h localhost -d postgres

# Inside psql, run these commands:
CREATE DATABASE study_and_learn;
CREATE USER study_user WITH PASSWORD 'study_pass';
GRANT ALL PRIVILEGES ON DATABASE study_and_learn TO study_user;
GRANT CREATE ON SCHEMA public TO study_user;
GRANT USAGE ON SCHEMA public TO study_user;
\q
```

### 5. Pull Ollama models

```bash
ollama pull qwen3:0.6b
ollama pull qwen3-embedding:0.6b
```

Note: qwen3:0.6b is a placeholder model. For better results, use qwen3:8b or gemma3:12b if your system can handle it.

### 6. Create .env file

Create a `.env` file in the project root:

```
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql+psycopg2://study_user:study_pass@localhost:5432/study_and_learn
OLLAMA_MODEL=qwen3:0.6b
OLLAMA_EMBEDDING_MODEL=qwen3-embedding:0.6b
```

### 7. Run the application

```bash
python app.py
```

Open http://localhost:5000 in your browser.

## Testing

```bash
pytest -v tests/
```

## Using Ollama Cloud (Optional)

To use Ollama Cloud instead of local models:

1. In `src/services/ai_client.py`, uncomment line 28:
   ```python
   from .ai_client_cloud import call_ollama
   ```

2. Add to your `.env` file:
   ```
   OLLAMA_CLOUD_API_KEY=your-api-key-here
   OLLAMA_MODEL=gemma3:12b-cloud
   ```

## Testing without GPU

Set `AI_MOCK=true` in your `.env` file to use mock responses (no Ollama required).

## Documentation

- SRS.md - Software requirements and user stories
- TODO.md - Sprint plan and task backlog
- DESIGN_AND_TESTING.md - Architecture and testing strategy

## License

MIT - For educational purposes only.
