from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import os
from datetime import datetime
import chromadb
from sentence_transformers import SentenceTransformer
import ollama

app = FastAPI(title="Chatbot API", description="RAG Chatbot with Ollama", version="0.2.0")

# CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
CHROMA_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "chroma_db")
os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)

# ChromaDB client
chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
collection = chroma_client.get_or_create_collection(name="documents")

# Embedding model
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

# Ollama config
OLLAMA_MODEL = "llama3"
OLLAMA_HOST = "http://182.165.0.199:11434"

# Set Ollama host globally
ollama.host = OLLAMA_HOST

# In-memory conversations
conversations = []

class Document(BaseModel):
    id: Optional[str] = None
    content: str
    source: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    use_rag: bool = True

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    sources: Optional[List[str]] = None
    rag_used: bool = False

@app.get("/")
def root():
    return {
        "service": "Chatbot RAG API",
        "version": "0.2.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "features": ["RAG", "Ollama LLM", "ChromaDB Vector Store"]
    }

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/documents", response_model=Document)
def add_document(doc: Document):
    """Add document to knowledge base with embedding"""
    doc_id = doc.id or f"doc_{datetime.now().timestamp()}"
    doc.created_at = datetime.now().isoformat()
    doc.metadata = doc.metadata or {}
    
    # Create embedding
    embedding = embedding_model.encode(doc.content).tolist()
    
    # Store in ChromaDB
    collection.upsert(
        ids=[doc_id],
        embeddings=[embedding],
        documents=[doc.content],
        metadatas=[{"source": doc.source or "unknown", "created_at": doc.created_at}]
    )
    
    return doc

@app.get("/documents", response_model=List[Document])
def list_documents():
    """List all documents in knowledge base"""
    results = collection.get(include=["documents", "metadatas"])
    docs = []
    for i, doc_id in enumerate(results["ids"]):
        docs.append(Document(
            id=doc_id,
            content=results["documents"][i],
            source=results["metadatas"][i].get("source", "unknown"),
            created_at=results["metadatas"][i].get("created_at", ""),
            metadata=results["metadatas"][i]
        ))
    return docs

@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """Delete document from knowledge base"""
    collection.delete(ids=[doc_id])
    return {"status": "deleted", "id": doc_id}

def search_similar(query: str, n_results: int = 3):
    """Search for similar documents"""
    query_embedding = embedding_model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "distances"]
    )
    return results

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Chat with RAG + Ollama"""
    conversation_id = request.conversation_id or f"conv_{datetime.now().timestamp()}"
    
    response_text = ""
    sources = []
    rag_used = False
    
    if request.use_rag:
        # Search for relevant documents
        search_results = search_similar(request.message, n_results=3)
        
        if search_results["documents"] and search_results["documents"][0]:
            rag_used = True
            # Build context from search results
            context_parts = []
            for i, doc in enumerate(search_results["documents"][0]):
                sources.append(f"Source {i+1}: {doc[:200]}...")
                context_parts.append(f"[Document {i+1}]: {doc}")
            
            context = "\n\n".join(context_parts)
            
            # Build prompt with context
            prompt = f"""Based on the following context, answer the question. If the context doesn't contain relevant information, say you don't have enough information.

Context:
{context}

Question: {request.message}

Answer:"""
        else:
            # No relevant documents, use simple prompt
            prompt = request.message
    else:
        prompt = request.message
    
    try:
        # Call Ollama
        response = ollama.generate(
            model=OLLAMA_MODEL,
            prompt=prompt
        )
        response_text = response.get("response", "No response from Ollama")
    except Exception as e:
        response_text = f"[Ollama Error] {str(e)}. Make sure Ollama is running on {OLLAMA_HOST}"
    
    # Save conversation
    conversations.append({
        "conversation_id": conversation_id,
        "message": request.message,
        "response": response_text,
        "rag_used": rag_used,
        "timestamp": datetime.now().isoformat()
    })
    
    return ChatResponse(
        response=response_text,
        conversation_id=conversation_id,
        sources=sources if sources else None,
        rag_used=rag_used
    )

@app.get("/conversations/{conv_id}")
def get_conversation(conv_id: str):
    """Get conversation history"""
    convs = [c for c in conversations if c["conversation_id"] == conv_id]
    return {"conversation_id": conv_id, "messages": convs}

@app.get("/models")
def list_models():
    """List available Ollama models"""
    try:
        models = ollama.list(host=OLLAMA_HOST)
        return {"models": models}
    except Exception as e:
        return {"error": str(e), "ollama_host": OLLAMA_HOST}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
