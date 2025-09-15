from __future__ import annotations
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# -------- Base & Data Paths --------
BASE_DIR = Path(os.getenv("RAG_HOME"))
DATA_DIR = Path(os.getenv("RAG_DATA_DIR"))
FLAT_DIR = Path(os.getenv("RAG_FLAT_DIR", DATA_DIR / "flat2"))
RAW_FHIR_GLOB = os.getenv("RAG_RAW_FHIR_GLOB")

# Vector stores (Chroma persist)
CLAIMS_CHROMA_DIR = Path(os.getenv("RAG_CLAIMS_CHROMA_DIR", BASE_DIR / "TestVec3"))
PDF_CHROMA_DIR = Path(os.getenv("RAG_PDF_CHROMA_DIR", BASE_DIR / "Chroma"))

# -------- Models & Tunables --------
EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "text-embedding-3-small")
CLAIMS_LLM_MODEL = os.getenv("RAG_CLAIMS_LLM_MODEL", "gpt-4o-mini")
PDF_LLM_MODEL = os.getenv("RAG_PDF_LLM_MODEL", "mistral") # Ollama model name
ROUTER_MODEL = os.getenv("RAG_ROUTER_MODEL", "llama3.2:3b")

# Retrieval sizes
PDF_TOP_K = int(os.getenv("RAG_PDF_TOP_K", 5))
CLAIMS_TOP_K = int(os.getenv("RAG_CLAIMS_TOP_K", 4))
MAX_CHUNK_CHARS = int(os.getenv("RAG_MAX_CHUNK_CHARS", 900))
HISTORY_TURNS = int(os.getenv("RAG_HISTORY_TURNS", 4))

# Router & graph
ROUTER_KWARGS = {"num_predict": 8, "temperature": 0.0, "keep_alive": "10m"}
CHECKPOINT_DB = Path(os.getenv("RAG_CHECKPOINT_DB", BASE_DIR / "omnibot_checkpoints.sqlite3"))

# Splitting
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", 800))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", 100))

# Misc
WRITE_JSONL = os.getenv("RAG_WRITE_JSONL", "false").lower() == "true"

if __name__ == '__main__':
    print(BASE_DIR)