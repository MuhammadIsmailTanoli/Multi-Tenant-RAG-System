# Multi-Tenant RAG System

A secure, enterprise-grade Multi-Tenant Retrieval-Augmented Generation (RAG) system built with **FastAPI**, **ChromaDB**, **Groq / LLaMA 3**, and **React (TypeScript)**.

It allows multiple distinct corporate entities ( **Acme Corp** and **Globex Corporation**) to query their internal confidential employee handbooks through a unified interface while guaranteeing **100% strict physical data isolation**, multi-tiered authentication, and persistent quota enforcement.

---

## Demo Video

<video src="https://github.com/MuhammadIsmailTanoli/Multi-Tenant-RAG-System/raw/dev/DEMO.mp4" controls width="700"></video>

## 🌐 Live Web Access & Demo Credentials

The frontend is live and deployed on **Vercel**:
🔗 **[https://multi-tenant-rag-system.vercel.app](https://multi-tenant-rag-system.vercel.app)**

### 🔑 Company Access Passwords

| Company | Tenant ID | Demo Password |
| :--- | :--- | :--- |
| **Acme Corp** | `acme` | `Acme@Admin` |
| **Globex Corporation** | `globex` | `Globex@Admin` |

> [!IMPORTANT]
> **Authentication Flow:**
> 1. Select the company on the landing page.
> 2. Enter the corresponding company password (`Acme@Admin` or `Globex@Admin`).
> 3. Sign in with your **Google Account** (OAuth 2.0) to complete verification and receive your secure session.

> [!NOTE]
> **Live Server Notice (Backend on Laptop via ngrok):**  
> The frontend is hosted 24/7 on Vercel, while the backend runs locally on a private server tunneled securely via **ngrok**.  
> If the backend appears offline or you wish to evaluate the live demo, **please contact me 10 minutes prior on WhatsApp (+92 313 5060949)** to spin up the server tunnel.  
> Alternatively, you can effortlessly run the entire system on your local machine using the complete setup guide below.

---

## 🛠️ Technology Stack & AI Models

| Layer | Technologies & Models |
| :--- | :--- |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS, Framer Motion, Lucide Icons, `@react-oauth/google` |
| **Backend Framework** | FastAPI, Python 3.13, Uvicorn, Pydantic v2 |
| **Vector Database** | ChromaDB (Independent persistent physical collections: `tenant_acme`, `tenant_globex`) |
| **Embedding Model** | `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional dense semantic vectors) |
| **LLM Providers** | **Groq** (`llama-3.3-70b-versatile`), with built-in adapters for Google Gemini and Anthropic Claude |
| **Authentication** | Google OAuth 2.0 (token verification), Passlib (bcrypt password hashing), PyJWT (HS256 signed tenant tokens) |
| **Rate Limiting** | SlowAPI & Limits with custom persistent **SQLite** storage (`data/rate_limits.db`) |
| **Deployment & Tunneling** | Vercel (Frontend), ngrok (Secure TLS backend tunnel) |

---

## 🚀 Complete Local Setup Guide

Follow these steps to run both the FastAPI backend and the React frontend on your local system.

### Prerequisites
- **Python 3.13** installed
- **Node.js 18+** and **npm** installed
- **Git** installed
- Free API keys from [Groq Console](https://console.groq.com) and [Google Cloud Console](https://console.cloud.google.com/) (OAuth Client ID)

---

### Step 1: Clone the Repository
```bash
git clone https://github.com/MuhammadIsmailTanoli/Multi-Tenant-RAG-System.git
cd Multi-Tenant-RAG-System
```

---

### Step 2: Backend Setup (Python / FastAPI)

1. **Create and activate a virtual environment:**
   - **Windows:**
     ```bash
     python -m venv venv
     .\venv\Scripts\activate
     ```


2. **Install backend dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the `.env` file:**
   Copy the example configuration:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in your keys:
   ```env
   # LLM Provider Configuration
   LLM_PROVIDER=groq
   GROQ_API_KEY=your_groq_api_key_here

   # Google OAuth Client ID (must match frontend)
   GOOGLE_CLIENT_ID=your_google_client_id_here

   # JWT Security Secret
   JWT_SECRET=your_super_secret_jwt_key_here

   # Rate Limit Configuration
   RATE_LIMIT_QUERY=50/day;200/7 days
   RATE_LIMIT_STORAGE_URI=sqlite:///data/rate_limits.db
   RATE_LIMIT_ENABLED=true
   ```

4. **Ingest Employee Handbooks into ChromaDB:**
   Parse the Acme and Globex PDF handbooks, generate embeddings, and build isolated ChromaDB vector stores:
   ```bash
   python -m ingestion.ingest
   ```

5. **Start the FastAPI Backend Server:**
   ```bash
   py -3.13 -m uvicorn api.main:app --reload --port 8000
   ```
   The backend will be live at:
   - **API Root**: [http://localhost:8000](http://localhost:8000)
   - **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

### Step 3: Frontend Setup (React / Vite)

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install Node dependencies:**
   ```bash
   npm install
   ```

3. **Configure frontend environment variables:**
   Create a `.env` file inside `frontend/`:
   ```env
   VITE_API_BASE_URL=http://localhost:8000
   VITE_GOOGLE_CLIENT_ID=your_google_client_id_here
   ```

4. **Start the Vite development server:**
   ```bash
   npm run dev
   ```
   Open your browser and navigate to:
   👉 **[http://localhost:5173](http://localhost:5173)**

---

## 🔄 System Architecture & Flow of Control

```text
[ User Browser ]
       │
       ▼
 1. Company Selection ───► Enter Company Password (Acme@Admin / Globex@Admin)
       │
       ▼
 2. Google OAuth 2.0  ───► Verify ID Token (Backend confirms Google identity)
       │
       ▼
 3. JWT Token Issued  ───► Scoped with tenant_id ("acme" | "globex") + google_sub
       │
       ▼
 4. Question Input    ───► Character Counter & Validation (1 - 500 chars)
       │
       ├──► [Small-Talk Interceptor] ──► Instant greeting response (0 vector DB calls)
       │
       └──► [Rate Limiter] ────────────► Checks SQLite by google_sub (50/day, 200/week)
                   │
                   ▼ (Quota Available)
       [Vector Search] ────────────────► Query strictly tenant's isolated ChromaDB collection
                   │
                   ▼
       [LLM Generation] ───────────────► Groq LLaMA-3.3 grounded on handbook context only
                   │
                   ▼
       [Clean Response] ───────────────► Direct policy answer rendered; counter synced in UI
```

1. **Company Selection & Password Gate**: User selects their designated enterprise and enters the company password verified against salted bcrypt hashes in `tenants.yaml`.
2. **Google Identity Verification**: The client acquires a Google OAuth ID token. The backend verifies this directly against Google's public certs, extracting the permanent subject identifier (`google_sub`).
3. **Session Token Generation**: A JWT access token is signed using HS256 containing both the `tenant_id` and the user's `google_sub`.
4. **Fast Switch Mechanism**: A user can switch between Acme and Globex by providing the new company password; the client re-uses the existing Google identity without prompting for a re-login.
5. **Small-Talk Filter**: Common greetings ("hi", "hello", "good morning") bypass the vector database and LLM entirely, returning an immediate friendly prompt to save tokens and latency.
6. **Isolated Retrieval**: Relevant handbook chunks are retrieved strictly from `data/chroma/tenant_<id>`.
7. **Prompt Grounding**: Groq LLaMA 3.3 processes the retrieved chunks with strict guardrails preventing hallucinations or cross-company knowledge leakage.

---

## 🌟 Key Features & Enterprise Safeguards 

### 1. 🛡️ Strict Physical Multi-Tenant Isolation
- **Separate Physical Storage**: Rather than relying on soft metadata tags or prompt filtering, each tenant maintains an isolated physical directory (`data/chroma/tenant_acme` vs. `data/chroma/tenant_globex`).
- **Cryptographic Enforcement**: The backend verifies that the token's `tenant_id` claim strictly matches the queried `tenant_id`. Any attempt to cross-query is terminated with `403 Forbidden`.

### 2. ⏱️ Cross-Tenant Persistent Rate Limiting
- **Identity-Keyed Quotas**: Rate limits (50 requests/day, 200 requests/week) are keyed against the user's real Google ID (`google_sub`), **not** an IP address or tenant ID. Querying Acme 25 times and Globex 25 times exhausts the daily quota.
- **SQLite Persistence**: Rate counters are backed by SQLite (`data/rate_limits.db`). Re-starting the backend server or switching networks does not reset quotas.
- **Real-Time Synchronized UI**: The frontend displays an interactive **Usage & Rate Limits Modal** showing remaining queries, percentages, and exact countdown timers to reset.
- **Graceful HTTP 429 Takeover**: When quota is exhausted, a specialized full-screen takeover modal provides an animated countdown until the window re-opens.

### 3. ✍️ Prompt Character & Input Constraints
- **Client-Side Visual Counter**: Dynamic character counter (500-character limit) with progressive color feedback (turns amber at 400+, rose at 480+, and blocks input past 500).
- **Backend Length & Content Validation**: API rejects empty queries, whitespace-only messages, and inputs exceeding maximum character lengths before executing embeddings.

### 4. ⚡ Small-Talk Interceptor (Cost & Latency Optimization)
- Fast regex matching instantly answers conversational pleasantries ("hello", "hey", "who are you?") without querying ChromaDB or making LLM API calls, slashing inference latency and API costs.

### 5. 🔒 Prompt Injection & Leakage Defenses
- **System Guardrails**: Grounded system prompts instruct the LLM to refuse speculative answers, ignore prompt override attempts, and never reveal underlying prompt instructions or cross-tenant data.
- **Clean Output Formatting**: Raw system paths, internal chunk citations, and download links are stripped, presenting clean, professional answers.

### 6. 🌐 ngrok & Production Tunnel Compatibility
- All client network requests inject `ngrok-skip-browser-warning: true`, ensuring that tunneling via ngrok does not trigger interstitial HTML warning pages that corrupt JSON responses.

---

## 🧪 Automated Testing Suite

The repository features **121 automated unit and integration tests** verifying system resilience:

```bash
pytest tests/ -v
```

### Test Coverage Breakdown:
- `test_auth_rate_limit_flow.py`: Complete Google OAuth flow, company login, company switching, token expiry, and daily/weekly rate limit enforcement.
- `test_isolation.py`: Verifies zero cross-tenant data leakage and prompt injection containment.
- `test_api.py`: FastAPI endpoints, validation rules, and error handling.
- `test_ingestion.py`: PDF document processing, chunking algorithms, and collection creation.
- `test_llm_provider.py`: Groq, Gemini, and Claude adapter functionality and error fallbacks.
- `test_retriever.py`: Tenant vector search accuracy and score thresholds.

---

## 📄 Further Technical Documentation

> [!TIP]
> For in-depth architecture diagrams, vector space analysis, threat modeling, and full API endpoint specifications, please read  **`documentation.pdf`** file located in the root directory.

---

## 👤 Author & Support
- **Author**: Muhammad Ismail Tanoli
- **Live Demo**: [https://multi-tenant-rag-system.vercel.app](https://multi-tenant-rag-system.vercel.app)
- **WhatsApp for Server Activation**: **+92 313 5060949**
