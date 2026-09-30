# AI Mental Health Support & Wellness Chatbot

A web-based chatbot that gives **general wellbeing information**, remembers the conversation, answers questions from your own documents (RAG), and includes a **safety layer** for crisis situations.

> **Not a medical or emergency service.** This project is for education and portfolio purposes. It does not diagnose, prescribe, or replace a doctor or therapist.

## Overview

The backend is built with **FastAPI**. Chat replies come from **Google Gemini** (free tier, default) or the **OpenAI API** (switch with one setting). Document Q&A uses **LlamaIndex** to index PDF/TXT/MD files and retrieve relevant passages. A plain **HTML/CSS/JavaScript** frontend is served by the same FastAPI app, so there is only one thing to run.

## Features

- **AI chat** with follow-up questions and short, readable answers
- **Session memory**: session IDs, bounded history, expiry, and a Clear chat button. Memory is in RAM only and is never written to disk
- **Document Q&A (LlamaIndex)**: the index is saved to disk and rebuilt only when documents change; weak matches are filtered out; if the answer is not in the documents, the bot says so instead of guessing; sources are shown
- **Safety layer**: rule-based crisis detection runs *before* any AI call and returns a fixed supportive message with emergency and crisis-line guidance
- **Medical safety**: system prompt plus an extra guard when a message mentions diagnosis or medication
- **Modern UI**: responsive, light/dark mode, loading indicator, error notifications, keyboard accessible
- **Robust errors**: missing key, empty message, invalid session, timeouts, OpenAI failures, indexing failures, all with friendly messages
- **Security basics**: keys only in environment variables, input validation, rate limiting, security headers (CSP), no message text in logs

## Tech Stack

Python 3.10+, FastAPI, Uvicorn, Pydantic v2 / pydantic-settings, OpenAI Python SDK (async, also used for Gemini's OpenAI-compatible endpoint), LlamaIndex, HTML, CSS, JavaScript, pytest.
SQLite is intentionally **not** used: storing mental-health conversations in a database is unnecessary risk for a demo (see Future Enhancements).

## Project Architecture

```
ai-mental-health-chatbot/
├── backend/
│   ├── __init__.py
│   ├── main.py            # FastAPI app, routes, error handlers, security headers
│   ├── config.py          # Settings from environment variables / .env
│   ├── models.py          # Request/response schemas and input validation
│   ├── chat_service.py    # Safety check -> memory -> Gemini/OpenAI -> memory
│   ├── memory_service.py  # In-memory sessions (TTL, size limits)
│   ├── safety_service.py  # Crisis and medical-boundary detection
│   ├── rag_service.py     # LlamaIndex indexing, retrieval, answering
│   ├── prompts.py         # All prompt text in one place
│   ├── exceptions.py      # AppError and AI error mapping
│   ├── rate_limiter.py    # Per-IP sliding-window limiter
│   └── logger.py          # Logging setup (never logs message text)
├── frontend/              # index.html, style.css, script.js
├── documents/             # Put your PDF/TXT/MD files here
├── tests/                 # Automated tests (pytest)
├── .env.example  .gitignore  requirements.txt  requirements-dev.txt  pytest.ini  LICENSE
└── README.md
```

## How It Works

```
Browser --POST /chat--> FastAPI
                          |-> safety_service: crisis? --yes--> fixed supportive reply (no AI call)
                          |-> memory_service: load recent messages for this session
                          |-> chat_service: system prompt + history + message -> Gemini/OpenAI
                          '-> memory_service: save the exchange -> reply

Browser --POST /document/query--> FastAPI -> safety check
   -> LlamaIndex: load saved index (rebuild only if files changed)
   -> retrieve top-k chunks -> drop low-similarity chunks
   -> none left?  "not found in documents" (no AI call)
   -> otherwise the LLM answers from those chunks only, and sources are returned
```

## Installation (beginner friendly)

### 1. Install the software
1. **Python 3.10 or newer**: https://www.python.org/downloads/ . On Windows, tick **"Add python.exe to PATH"** in the installer.
2. **Git**: https://git-scm.com/downloads
3. **VS Code** (optional editor): https://code.visualstudio.com/
4. An API key. **Gemini (free, no card):** https://aistudio.google.com/apikey . Or an OpenAI key: https://platform.openai.com/api-keys (needs billing credit).

Check the installs by opening a terminal (Windows: PowerShell; Mac: Terminal):
```bash
python --version      # Mac/Linux: python3 --version
git --version
```

### 2. Get the project
Unzip the project (or clone your GitHub repo), then open a terminal **inside the project folder** (the one containing `README.md`):
```bash
cd path/to/ai-mental-health-chatbot
```

### 3. Create a virtual environment (an isolated box for this project's packages)
```bash
python -m venv .venv
```
Activate it:
- Windows PowerShell: `.venv\Scripts\Activate.ps1`
- Windows cmd: `.venv\Scripts\activate.bat`
- Mac/Linux: `source .venv/bin/activate`

You should now see `(.venv)` at the start of your terminal line.

> Windows PowerShell says "running scripts is disabled"? Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer `Y`, and activate again.

### 4. Install dependencies
```bash
pip install -r requirements-dev.txt
```
This installs the app packages plus the testing tools and takes a couple of minutes.

### 5. Add your API key
Copy `.env.example` to `.env`:
- Windows: `copy .env.example .env`
- Mac/Linux: `cp .env.example .env`

Open `.env`. For the free Gemini setup, keep `LLM_PROVIDER=gemini` and paste your key after `GEMINI_API_KEY=` with no quotes or spaces. To use OpenAI instead, set `LLM_PROVIDER=openai` and fill `OPENAI_API_KEY=`. Save the file and restart the server.

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `LLM_PROVIDER` | No | `gemini` | `gemini` or `openai` |
| `GEMINI_API_KEY` | If provider is gemini | none | Your Gemini key |
| `GEMINI_MODEL` | No | `gemini-2.5-flash-lite` | Chat model |
| `GEMINI_EMBEDDING_MODEL` | No | `gemini-embedding-001` | Document embeddings |
| `OPENAI_API_KEY` | If provider is openai | none | Your OpenAI key |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Chat model |
| `OPENAI_EMBEDDING_MODEL` | No | `text-embedding-3-small` | Document embeddings |
| `MAX_HISTORY_MESSAGES` | No | `12` | Messages sent as context |
| `SESSION_TTL_MINUTES` | No | `60` | Idle session expiry |
| `RAG_TOP_K` | No | `4` | Chunks retrieved per question |
| `RAG_SIMILARITY_CUTOFF` | No | `0.2` | Minimum similarity for a chunk to be used |
| `RATE_LIMIT_PER_MINUTE` | No | `20` | Requests per IP per minute |
| `LOG_LEVEL` | No | `INFO` | Logging detail |

If a Gemini model name stops working ("model was not found"), pick a current free-tier Flash or Flash-Lite model from https://ai.google.dev/gemini-api/docs/models and set `GEMINI_MODEL`. Gemini's free tier has daily and per-minute limits, so "busy or quota" errors mean wait a little. If you change `OPENAI_MODEL`, use a chat model that supports the `temperature` setting (as `gpt-4o-mini` does). Some newer reasoning models do not and would need small code changes.

## Running the Project

```bash
uvicorn backend.main:app --reload
```
Expected output ends with:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```
Open **http://127.0.0.1:8000** in your browser. Interactive API docs are at **http://127.0.0.1:8000/docs**. Stop the server with `Ctrl+C`.

### Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Reinstall Python and tick "Add to PATH", or use `python3` |
| `No module named 'backend'` | Run commands from the project root folder (where README.md is) |
| `uvicorn` not found | Activate the virtual environment, then run `pip install -r requirements.txt` |
| Status shows "API key missing" | Check `.env` exists (not `.env.txt`) and has your key, then restart the server |
| "AI service rejected the API key" | The key is wrong or revoked; create a new one |
| "busy or quota is used up" | Gemini: wait a minute (free-tier limit). OpenAI: add billing credit |
| Port already in use | Run `uvicorn backend.main:app --port 8001` and open port 8001 |
| Document Q&A: "No documents found" | Add `.pdf`, `.txt` or `.md` files to `documents/` |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Status, version, whether an API key is configured, active sessions |
| POST | `/chat` | Send a message. Body: `{"message": "...", "session_id": null}` |
| DELETE | `/session/{session_id}` | Clear a conversation |
| POST | `/document/query` | Ask about the documents. Body: `{"question": "..."}` |
| GET | `/document/status` | List document files and whether the index is loaded |
| POST | `/document/reindex` | Force a rebuild of the document index |

Errors always look like `{"error": {"code": "MISSING_API_KEY", "message": "..."}}`.

## Screenshots

_Add screenshots here after running the app, for example:_

```
![Chat](docs/screenshots/chat.png)
![Document Q&A](docs/screenshots/document-qa.png)
```

## Example Usage

```bash
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"message": "I feel stressed about exams. Any tips?"}'
# -> {"reply": "...", "session_id": "3f2b...", "is_crisis": false}

# Follow-up: reuse the session_id from the previous reply
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" \
  -d '{"message": "Which of those can I do tonight?", "session_id": "PASTE_ID_HERE"}'

curl -X POST http://127.0.0.1:8000/document/query -H "Content-Type: application/json" \
  -d '{"question": "How does slow breathing work?"}'
```
On Windows PowerShell, `curl` behaves differently. The easiest way to try the API there is the built-in page at `/docs`.

## Testing

```bash
pytest
```
Expected: `40 passed`. Tests never call Gemini or OpenAI (model calls are mocked; LlamaIndex uses mock models).

**Manual checklist**
- [ ] Server starts and `/health` returns `"status": "ok"`
- [ ] The chat page loads and the status shows "Online"
- [ ] A normal question gets a reply; a follow-up ("tell me more") uses earlier context
- [ ] Clear chat empties the screen and the old context is gone
- [ ] Sending an empty message shows a notification
- [ ] Type `I want to die`: you get the safety message, not an AI answer
- [ ] Ask "Do I have depression?": the bot declines to diagnose
- [ ] Document Q&A: "How does slow breathing work?" gives an answer with sources
- [ ] Document Q&A: "What is the capital of France?" says it is not in the documents
- [ ] Stop the server: the page shows a friendly "could not reach the server" message
- [ ] `git status` never lists `.env`

## Safety & Limitations

- The crisis detector is **keyword-based**. It can miss unusual wording and can over-trigger; it is a first safety net, not a clinical tool
- The crisis message lists example helplines (India, USA, UK/Ireland, findahelpline.com). Numbers change, so verify them and adapt to your audience
- AI answers can be wrong. The bot is instructed not to diagnose or advise on medication, but no prompt is a guarantee
- Sessions live in memory, so a restart clears them. Do not deploy publicly without adding authentication, HTTPS, monitoring, and a privacy policy
- Message text is sent to the selected AI provider (Gemini free tier content may be used by Google to improve its products; OpenAI applies your account's data terms). Do not enter real personal information while testing
- Document Q&A quality depends on the documents and the similarity cutoff

## Future Enhancements

- Optional encrypted, opt-in conversation history (SQLite or PostgreSQL) with user accounts
- Streaming responses (Server-Sent Events)
- Multilingual support and region-aware crisis resources
- Smarter safety classification (moderation model plus human-reviewed rules)
- Docker image and CI (GitHub Actions running pytest)
- Document upload from the UI

## Publishing to GitHub

1. Create an empty repository on https://github.com/new (do **not** add a README there). Copy its URL, for example `https://github.com/YOUR-USERNAME/ai-mental-health-chatbot.git`.
2. In the project folder run:
```bash
git init
git add .
git status                      # confirm .env is NOT listed
git commit -m "Initial commit: AI mental health support chatbot"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/ai-mental-health-chatbot.git   # <- replace with YOUR URL
git push -u origin main
```
Replace `YOUR-USERNAME/ai-mental-health-chatbot` with your own repository URL. If Git asks who you are, first run `git config --global user.name "Your Name"` and `git config --global user.email "you@example.com"`. When pushing, sign in through the browser window or use a personal access token as the password.

Before making the repo public, edit `LICENSE` and replace `YOUR NAME`. **If you ever accidentally commit a key, revoke it immediately in the Gemini or OpenAI dashboard.**

## License

MIT. See [LICENSE](LICENSE).
