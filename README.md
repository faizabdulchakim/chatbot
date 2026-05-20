# Chatbot - RAG Foundation

**Status:** 🟡 In Progress  
**Started:** 2026-05-06  
**Priority:** 🔴 High (Foundation for Smart Robot & Video Chatbot)

---

## Progress Log

### ✅ 2026-05-06 - Initial Setup (COMPLETED)
- [x] Created project folder structure
- [x] Created FastAPI main.py with basic endpoints
- [x] Created requirements.txt
- [x] API endpoints ready:
  - `GET /` - Service info
  - `GET /health` - Health check
  - `POST /documents` - Add document to KB
  - `GET /documents` - List documents
  - `POST /chat` - Chat endpoint (basic echo, RAG coming next)
  - `GET /conversations/{id}` - Get conversation history
- [x] Dependencies installed (FastAPI, uvicorn, pydantic)
- [x] Deployed with PM2 (chatbot-api running on port 8001)
- [x] Created simple webapp UI (index.html)
- [x] Health check passed ✅

### 🔄 Next Steps (Pending)
- [ ] Add RAG pipeline with ChromaDB
- [ ] Add document embedding with sentence-transformers
- [ ] Improve chat responses with vector search
- [ ] Add conversation history persistence
- [ ] Deploy webapp with nginx/PM2

---

## Access

- **API:** http://localhost:8001
- **Web UI:** Open `~/Documents/projects/chatbot/webapp/index.html` in browser
- **PM2 Status:** `pm2 status chatbot-api`
- **Logs:** `pm2 logs chatbot-api`

---

## Tech Stack
- **Backend:** FastAPI + Node.js/Express
- **Vector DB:** ChromaDB (persistent, local)
- **LLM:** Ollama (llama3, remote host)
- **Embedding:** SentenceTransformer (`all-MiniLM-L6-v2`)
- **Frontend:** HTML/JS (Chatbot UI + Admin Panel)
- **Deployment:** PM2

---

## 🏗️ Arsitektur Global

```
┌─────────────────┐         ┌─────────────────┐
│   webapp/       │         │   admin/        │
│  Chatbot UI     │         │  Admin Panel    │
│  (FE Chat)      │         │  (FE + BE)      │
│  Port: 3001     │         │  Port: 3003     │
└────────┬────────┘         └────────┬────────┘
         │                           │
         │  HTTP Request             │  Proxy + Upload
         │                           │  (txt, xlsx, etc.)
         └──────────┬────────────────┘
                    ▼
         ┌─────────────────┐
         │   api/          │
         │  Chatbot API    │
         │  (FastAPI/Python│
         │  Port: 8001     │
         └────────┬────────┘
                  │
          Embed & Store
                  ▼
         ┌─────────────────┐
         │   ChromaDB      │
         │  (Vector Store) │
         │  /chroma_db     │
         └─────────────────┘
                  │
          RAG Query
                  ▼
         ┌─────────────────┐
         │   Ollama LLM    │
         │  (llama3)       │
         │  Remote Host    │
         └─────────────────┘
```

---

## 🧩 Breakdown Per Komponen

| App | Tech | Port | Fungsi |
|-----|------|------|--------|
| **webapp/** | Node.js/Express | 3001 | **FE Chat** — antarmuka untuk pengguna ngobrol dengan chatbot |
| **admin/** | Node.js/Express | 3003 | **FE + BE Admin** — upload dokumen (txt/xlsx), parsing, lalu kirim ke API untuk disimpan di ChromaDB |
| **api/** | FastAPI/Python | 8001 | **Chatbot API** — inti sistem: terima dokumen, buat embedding, simpan ke ChromaDB, dan proses chat dengan RAG + Ollama |

> **Catatan:** Admin (`/admin`) sudah berfungsi sebagai FE sekaligus BE-nya sendiri.
> Ia punya server Express yang menerima file upload, parsing Excel/teks,
> lalu mem-proxy ke Chatbot API (`port 8001`). Tidak ada BE terpisah khusus untuk insert.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Service info |
| GET | `/health` | Health check |
| POST | `/documents` | Add document |
| GET | `/documents` | List documents |
| POST | `/chat` | Send message |
| GET | `/conversations/{id}` | Get history |

---

## Running Locally

```bash
cd ~/Documents/projects/chatbot/api
pip install -r requirements.txt
python main.py
```


run on venv
cd api
source venv/Scripts/activate
uvicorn main:app --host 0.0.0.0 --port 8001 --reload

API will be available at: `http://localhost:8001`

---

## Notes
- This is the FOUNDATION project
- Video Chatbot and Smart Robot will extend this
- All AI projects will reuse this RAG pipeline



hapus chroma db
rm -rf C:/Users/user/Documents/prj_2026/chatbot/api/chroma_db