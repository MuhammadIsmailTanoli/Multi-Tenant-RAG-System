# Multi-Tenant RAG System

A Multi-Tenant Retrieval-Augmented Generation (RAG) system built with **FastAPI** and **ChromaDB**. 

It lets different companies (such as **Acme Corp** and **Globex Corporation**) use the same AI service while keeping their private employee handbooks completely separate and secure.

---

## How It Works

Many RAG applications put all company files into one shared database and try to separate them using AI prompts or metadata tags. This can easily lead to data leaks.

This project uses **strict physical separation**:
- **Separate Databases**: Each company gets its own folder and its own ChromaDB collection on disk.
- **Zero Data Leaks**: An Acme Corp employee cannot view, search, or ask questions about Globex Corporation documents.
- **Combined Google + Company Login**: Users sign in with their Google account, then enter their company password to get a signed JWT session token.
- **Fast Company Switching**: If a user has access to multiple companies, they can switch between them with just the new company password. They do not need to sign in with Google again.
- **Fair Rate Limits**: Usage limits (50 queries per day, 200 queries per week) track the user's real Google ID (`google_sub`). Querying both companies counts towards the same limit. Limits are saved in SQLite so they do not reset when the server restarts.
- **Live Limits Button in Chat**: A small button next to the chat box shows how many queries you have used with colored progress bars and exact numbers.
- **Clean Answers (No Citations)**: Answers are taken directly from the company handbook. Citation badges and download links were removed so answers are clean and easy to read.

---

## Demo Company Passwords for Graders

You can use these demo accounts from [tenants.yaml](file:///c:/Users/Ismail/Desktop/Multi-Tenant-RAG-System/tenants.yaml) and [.env.example](file:///c:/Users/Ismail/Desktop/Multi-Tenant-RAG-System/.env.example) to test the system:

| Company Name | Tenant ID (`tenant_id`) | Plaintext Password | Stored Password Hash (bcrypt) | Handbook File |
| :--- | :--- | :--- | :--- | :--- |
| **Acme Corp** | `acme` | `AcmeSecret2026!` | `$2b$12$X8hEXcoAfdnt5N0/bspE9.DkxDkhiRsSlEjFNBBQewDVzmFGCQ486` | `Acme Corp Employee Handbook.pdf` |
| **Globex Corporation** | `globex` | `GlobexSecret2026!` | `$2b$12$fivoERBV1xrncJGAIpDk1eJv1fVyrc7w0dTw0liPLdghg6OPRw8Zy` | `Globex Corporation Employee Handbook.pdf` |

> [!IMPORTANT]
> Passwords are case-sensitive. To log in, you must provide both the company password and a valid Google ID token.

---

## Login & Session Flow

The login flow connects a real user's Google account to a specific company:

```text
[ Google Sign-In ]  --->  POST /auth/company  --->  JWT Session Token
 (google_id_token)        (Google Token + Password) (has tenant_id + google_sub)
                                |                          |
                                v                          v
                       POST /auth/switch-company      POST /query
                       (Same Google + New Password)   (Rate limits track google_sub)
```

---

### 1. Verify Google Sign-In (`POST /auth/google`)

Checks the Google ID token received from the browser and returns user profile details (`google_user_id`, `email`, `name`, `picture`).

```bash
curl -X POST "http://localhost:8000/auth/google" \
  -H "Content-Type: application/json" \
  -d '{
    "id_token": "YOUR_GOOGLE_ID_TOKEN_HERE"
  }'
```

**Example Response (`200 OK`)**:
```json
{
  "google_user_id": "109876543210987654321",
  "email": "user@example.com",
  "email_verified": true,
  "name": "Alex Smith",
  "picture": "https://lh3.googleusercontent.com/a/...",
  "message": "Google authentication successful."
}
```

---

### 2. Log in to a Company (`POST /auth/company`)

Checks the company password and the Google token together. Returns a signed JWT token that is locked to that company and user.

```bash
curl -X POST "http://localhost:8000/auth/company" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "acme",
    "password": "AcmeSecret2026!",
    "google_id_token": "YOUR_GOOGLE_ID_TOKEN_HERE"
  }'
```

**Example Response (`200 OK`)**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "tenant_id": "acme",
  "google_sub": "109876543210987654321",
  "email": "user@example.com",
  "expires_in": 3600,
  "message": "Authenticated successfully as Acme Corp."
}
```

---

### 3. Switch to Another Company (`POST /auth/switch-company`)

Allows a user who is already signed in with Google to switch to another company (like moving from Acme to Globex). **Only the new company's password is required. You do not need to sign in with Google again.**

```bash
curl -X POST "http://localhost:8000/auth/switch-company" \
  -H "Content-Type: application/json" \
  -d '{
    "new_tenant_id": "globex",
    "password": "GlobexSecret2026!",
    "google_id_token": "YOUR_GOOGLE_ID_TOKEN_HERE"
  }'
```

**Example Response (`200 OK`)**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "tenant_id": "globex",
  "google_sub": "109876543210987654321",
  "email": "user@example.com",
  "expires_in": 3600,
  "message": "Switched successfully to Globex Corporation."
}
```

---

### 4. Ask a Question (`POST /query`)

Requires the Bearer token in the `Authorization` header. 
- If you use an Acme token to query Globex, the request is rejected with `403 Forbidden`.
- Each query counts against your user rate limit.

```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE" \
  -d '{
    "tenant_id": "acme",
    "question": "What is the probation period duration?",
    "top_k": 4
  }'
```

**Example Response (`200 OK`)**:
```json
{
  "tenant_id": "acme",
  "tenant_name": "Acme Corp",
  "question": "What is the probation period duration?",
  "answer": "At Acme Corp, the standard employee probationary period is 90 days from the date of hire.",
  "sources": [],
  "chunks_retrieved": 4,
  "execution_time_ms": 412.0
}
```

> [!NOTE]
> Citations were removed: the response does not include document links or file citations, giving a clean and direct answer.

---

### 5. Check Your Remaining Limit (`GET /limits`)

Shows how many questions you have asked today and this week, and how many you have left.

```bash
curl -X GET "http://localhost:8000/limits" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE"
```

**Example Response (`200 OK`)**:
```json
{
  "google_sub": "109876543210987654321",
  "authenticated": true,
  "limits": [
    {
      "limit": 50,
      "period": "day",
      "count": 12,
      "remaining": 38,
      "percentage_used": 24.0,
      "reset_seconds": 68400,
      "reset_time": "2026-09-17T11:21:19+00:00"
    },
    {
      "limit": 200,
      "period": "week",
      "count": 45,
      "remaining": 155,
      "percentage_used": 22.5,
      "reset_seconds": 586800,
      "reset_time": "2026-09-23T11:21:19+00:00"
    }
  ]
}
```

---

## Rate Limits (Usage Quotas)

To prevent abuse, the `/query` endpoint limits how many questions a user can ask:

- **Daily Limit**: 50 requests per day (`50/day`)
- **Weekly Limit**: 200 requests per week (`200/7 days`)
- **Saved in SQLite**: Query counts are stored in `data/rate_limits.db`. Restarting the server does not reset the count.
- **Tracked by Real User**: Limits track your Google account ID (`google_sub`), not your IP address. If you ask 30 questions under Acme and 20 under Globex, you have used all 50 questions for the day.
- **Too Many Requests (Error 429)**: If you go over the limit, the API returns HTTP 429 with the exact time when your limit resets and a `Retry-After` header.

### How to Change Rate Limits

You can adjust the limits in your `.env` file:

```env
# Increase or decrease limits (e.g. 100 per day, 500 per week)
RATE_LIMIT_QUERY=100/day;500/7 days

# Change the SQLite database file location
RATE_LIMIT_STORAGE_URI=sqlite:///data/rate_limits.db

# Turn off rate limiting completely for testing
RATE_LIMIT_ENABLED=true
```

### In-Browser Limits Button
In the web chat interface ([http://localhost:8000/chat](http://localhost:8000/chat)), click the **Limits** button next to the chat box. A popup shows:
- **Progress Bar Lines**: Changes color from green (< 60%), to yellow (60%–85%), to red (> 85%).
- **Numbers**: Shows exact numbers like `12 / 50 used (24%)` and `38 queries remaining`.

---

## How to Run the Project Locally

### 1. Set Up the Environment

```bash
# Clone the repository
git clone https://github.com/MuhammadIsmailTanoli/Multi-Tenant-RAG-System.git
cd Multi-Tenant-RAG-System

# Create and activate a Python 3.13 virtual environment
python -m venv venv

# On Windows:
.\venv\Scripts\activate

# On Linux or macOS:
source venv/bin/activate

# Install required packages
pip install -r requirements.txt

# Create your environment file from the template
cp .env.example .env
```

### 2. Ingest the Employee Handbooks

Reads the Acme and Globex PDF handbooks and creates the Chroma vector databases:

```bash
python -m ingestion.ingest
```

### 3. Start the Server

```bash
python -m uvicorn api.main:app --reload --port 8000
```

- **Web Chat Interface**: [http://localhost:8000/chat](http://localhost:8000/chat)
- **API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **OpenAPI Schema**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

## Running the Automated Tests

The repository includes a complete test suite with **121 tests**. Run them with:

```bash
pytest tests/ -v
```

### What the Tests Check:
- `tests/test_auth_rate_limit_flow.py`: Full login flow, Google token verification, company switching without repeated Google login, expired/wrong token rejection, and daily/weekly rate limit blocks.
- `tests/test_api.py`: FastAPI endpoints, error handling, bad input rejection, and health checks.
- `tests/test_isolation.py`: Verifies zero cross-tenant data leakage and prompt injection resistance.
- `tests/test_ingestion.py`: PDF parsing, chunking, and ChromaDB collection isolation.
- `tests/test_llm_provider.py`: LLM adapters (Gemini, Groq, Claude).
- `tests/test_prompts.py`: Prompt construction and answer formatting.
- `tests/test_retriever.py`: Vector search and tenant collection checks.
