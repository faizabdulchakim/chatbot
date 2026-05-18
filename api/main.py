from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import os
import logging
import re
from datetime import datetime
import chromadb
from sentence_transformers import SentenceTransformer
import ollama

app = FastAPI(title="Chatbot API", description="RAG Chatbot with Ollama", version="0.2.0")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
#OLLAMA_MODEL = "phi4:latest"
#OLLAMA_HOST = "http://localhost:11434"

OLLAMA_MODEL = "qwen3.6:latest"
OLLAMA_HOST = "http://192.168.199.38:11434"

# RAG config
SIMILARITY_THRESHOLD = 1.5  # Max distance for document relevance (L2 distance; lower = more similar)
MIN_QUERY_TOKEN_MATCH = 2   # Minimum overlapping important tokens between question and context
RETRIEVAL_TOP_K = 8         # Retrieve more candidates, then filter
CHUNK_WORD_SIZE = 120       # Chunk size in words for long documents
CHUNK_WORD_OVERLAP = 25     # Overlap to preserve context across chunks

# Ollama client with custom host
ollama_client = ollama.Client(host=OLLAMA_HOST)

# In-memory conversations
conversations = []

def chunk_text(content: str, chunk_word_size: int = CHUNK_WORD_SIZE, chunk_word_overlap: int = CHUNK_WORD_OVERLAP) -> List[str]:
    """Split long text into overlapping word chunks for better retrieval."""
    words = (content or "").split()
    if not words:
        return []

    if len(words) <= chunk_word_size:
        return [content]

    step = max(1, chunk_word_size - chunk_word_overlap)
    chunks = []
    for start in range(0, len(words), step):
        piece = words[start:start + chunk_word_size]
        if not piece:
            continue
        chunks.append(" ".join(piece))
        if start + chunk_word_size >= len(words):
            break
    return chunks

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

    # Chunk long documents so distant paragraphs remain retrievable
    chunks = chunk_text(doc.content)
    ids = []
    documents = []
    metadatas = []

    for idx, chunk in enumerate(chunks):
        chunk_id = doc_id if len(chunks) == 1 else f"{doc_id}::chunk_{idx + 1}"
        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append({
            "source": doc.source or "unknown",
            "created_at": doc.created_at,
            "parent_doc_id": doc_id,
            "chunk_index": idx + 1,
            "total_chunks": len(chunks),
        })

    embeddings = embedding_model.encode(documents).tolist()

    # Store chunks in ChromaDB
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )

    logger.info("Document %s stored as %d chunk(s)", doc_id, len(chunks))
    
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

def search_similar(query: str, n_results: int = 3, distance_threshold: float = 1.0):
    """Search for similar documents with threshold filtering
    
    Args:
        query: Search query text
        n_results: Number of results to return
        distance_threshold: Max distance for relevance (lower = more similar; ~1.0 is reasonable for L2 distance)
    """
    query_embedding = embedding_model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "distances"]
    )
    
    # Filter by distance threshold
    if results["documents"] and results["documents"][0]:
        original_count = len(results["documents"][0])
        filtered_docs = []
        filtered_distances = []
        for doc, distance in zip(results["documents"][0], results["distances"][0]):
            if distance <= distance_threshold:
                filtered_docs.append(doc)
                filtered_distances.append(distance)
        
        results["documents"] = [filtered_docs]
        results["distances"] = [filtered_distances]
        logger.info("Similarity search: found %d/%d docs within threshold %.2f", 
                    len(filtered_docs), original_count, distance_threshold)
    
    return results

def _important_tokens(text: str):
    """Extract lowercase alphanumeric tokens and keep only informative ones."""
    tokens = re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
    return {t for t in tokens if len(t) >= 4}

def is_context_relevant(question: str, docs: List[str], min_token_match: int = MIN_QUERY_TOKEN_MATCH) -> bool:
    """Return True only when context shares enough important tokens with question."""
    if not docs:
        return False

    question_tokens = _important_tokens(question)
    if not question_tokens:
        return False

    context_tokens = _important_tokens(" ".join(docs))
    overlap = question_tokens.intersection(context_tokens)
    logger.info(
        "Context relevance check: overlap=%s (count=%d, min=%d)",
        sorted(overlap),
        len(overlap),
        min_token_match,
    )
    return len(overlap) >= min_token_match

def filter_docs_by_token_overlap(question: str, docs: List[str], strict_min_match: int = 2) -> List[str]:
    """Filter retrieved docs by per-chunk query token overlap.

    Strategy:
    - Prefer chunks matching >= strict_min_match query tokens.
    - Fallback to chunks matching >= 1 query token.
    - If none match, return original docs unchanged.
    """
    if not docs:
        return docs

    question_tokens = _important_tokens(question)
    if not question_tokens:
        return docs

    scored = []
    for doc in docs:
        overlap_count = len(question_tokens.intersection(_important_tokens(doc)))
        scored.append((doc, overlap_count))

    strong_matches = [doc for doc, overlap in scored if overlap >= strict_min_match]
    if strong_matches:
        logger.info(
            "Per-chunk token filter: kept %d/%d chunks with overlap >= %d",
            len(strong_matches),
            len(docs),
            strict_min_match,
        )
        return strong_matches

    weak_matches = [doc for doc, overlap in scored if overlap >= 1]
    if weak_matches:
        logger.info(
            "Per-chunk token filter: kept %d/%d chunks with overlap >= 1 (fallback)",
            len(weak_matches),
            len(docs),
        )
        return weak_matches

    logger.info("Per-chunk token filter: no token-overlap matches, using original chunks")
    return docs

def find_keyword_chunks(required_tokens: set, max_results: int = RETRIEVAL_TOP_K) -> List[str]:
    """Find chunks that contain any required tokens using lexical matching.

    This is a fallback when vector similarity misses rare/explicit keywords.
    """
    if not required_tokens:
        return []

    rows = collection.get(include=["documents"])
    all_docs = rows.get("documents") or []
    if not all_docs:
        return []

    scored = []
    for doc in all_docs:
        doc_tokens = _important_tokens(doc)
        overlap = required_tokens.intersection(doc_tokens)
        if overlap:
            scored.append((doc, len(overlap)))

    scored.sort(key=lambda item: item[1], reverse=True)
    return [doc for doc, _ in scored[:max_results]]

def truncate_at_sentence(text: str, max_chars: int = 300) -> str:
    """Truncate text at sentence boundary instead of mid-sentence.
    
    Args:
        text: Text to truncate
        max_chars: Maximum characters to keep
        
    Returns:
        Truncated text ending at a sentence boundary, or with ... if no boundary found
    """
    if len(text) <= max_chars:
        return text
    
    truncated = text[:max_chars]
    # Find last period/sentence end in the truncated text
    last_period = truncated.rfind('.')
    last_question = truncated.rfind('?')
    last_exclaim = truncated.rfind('!')
    
    # Get the rightmost sentence boundary
    last_sentence_end = max(last_period, last_question, last_exclaim)
    
    # If sentence boundary exists and is reasonably close (at least 70% of max_chars)
    if last_sentence_end > max_chars * 0.7:
        return truncated[:last_sentence_end + 1]
    
    return truncated + "..."

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Chat with RAG + Ollama"""
    conversation_id = request.conversation_id or f"conv_{datetime.now().timestamp()}"
    
    response_text = ""
    sources = []
    rag_used = False
    
    if request.use_rag:
        # Search for relevant documents
        search_results = search_similar(
            request.message,
            n_results=RETRIEVAL_TOP_K,
            distance_threshold=SIMILARITY_THRESHOLD,
        )
        
        if search_results["documents"] and search_results["documents"][0]:
            relevant_docs = search_results["documents"][0]
            relevant_docs = filter_docs_by_token_overlap(request.message, relevant_docs)

            # Lexical rescue: if some query tokens are still missing from retrieved chunks,
            # fetch chunks containing those tokens directly from Chroma documents.
            query_tokens = _important_tokens(request.message)
            retrieved_tokens = _important_tokens(" ".join(relevant_docs))
            missing_tokens = query_tokens.difference(retrieved_tokens)
            if missing_tokens:
                keyword_docs = find_keyword_chunks(missing_tokens, max_results=RETRIEVAL_TOP_K)
                if keyword_docs:
                    # Prioritize keyword-hit chunks so they survive top-k truncation.
                    merged = keyword_docs + relevant_docs
                    # Preserve order while removing duplicates.
                    relevant_docs = list(dict.fromkeys(merged))[:RETRIEVAL_TOP_K]
                    logger.info(
                        "Lexical fallback added %d chunk(s) for missing tokens=%s",
                        len(keyword_docs),
                        sorted(missing_tokens),
                    )

            if not is_context_relevant(request.message, relevant_docs):
                logger.info("Retrieved docs exist but are out-of-context for the question")
                response_text = "No information provided"
                rag_used = False
            else:
                rag_used = True
            # Build context from search results
                context_parts = []
                max_chunk_display = 1200  # Limit context per chunk for clarity and token efficiency
                for i, doc in enumerate(relevant_docs):
                    doc_preview = truncate_at_sentence(doc, 200)
                    sources.append(f"Source {i+1}: {doc_preview}")
                    
                    doc_truncated = truncate_at_sentence(doc, max_chunk_display)
                    context_parts.append(f"[Chunk {i+1}]: {doc_truncated}")
                
                context = "\n\n".join(context_parts)
                logger.info("Context built for RAG: %s", context)
                
                # Build strict grounded prompt
                prompt = f"""You must answer using ONLY the provided context.
If the answer is not explicitly present in the context, output exactly: No information provided
Do not infer, do not add external facts, and do not continue after that sentence.

Context:
{context}

Question: {request.message}

Answer:"""

                # Call Ollama with context
                try:
                    response = ollama_client.generate(
                        model=OLLAMA_MODEL,
                        prompt=prompt
                    )
                    response_text = response.get("response", "No response from Ollama")
                except Exception as e:
                    response_text = f"[Ollama Error] {str(e)}. Make sure Ollama is running on {OLLAMA_HOST}"
        else:
            # No relevant documents found, skip Ollama call
            logger.info("No documents matched similarity threshold, returning no information")
            response_text = "No information provided"
            rag_used = False
    else:
        # RAG disabled, skip Ollama call
        logger.info("RAG disabled, returning no information")
        response_text = "No information provided"
        rag_used = False
    
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
        models = ollama_client.list()
        return {"models": models}
    except Exception as e:
        return {"error": str(e), "ollama_host": OLLAMA_HOST}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
