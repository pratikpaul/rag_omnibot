from __future__ import annotations
from pathlib import Path
import hashlib
from typing import Iterable
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader, JSONLoader
from langchain_chroma import Chroma
from omnibot.embeddings.openai_embedder import get_embedding_function
from omnibot.config.constants import PDF_CHROMA_DIR, DATA_DIR, CHUNK_SIZE, CHUNK_OVERLAP

SUPPORTED = (".pdf", ".txt", ".json", ".jsonl")

splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

def load_docs(root: Path) -> Iterable:
   for p in sorted(root.rglob("*")):
      if not p.is_file():
         continue
      if p.suffix.lower() not in SUPPORTED:
         continue
      if p.suffix.lower() == ".pdf":
         for d in PyPDFLoader(str(p)).load():
            d.metadata.setdefault("source", p.name)
            yield d
      elif p.suffix.lower() == ".txt":
         for d in TextLoader(str(p), encoding="utf-8").load():
            d.metadata.setdefault("source", p.name)
            yield d
      elif p.suffix.lower() == ".json":
      # Treat as a single text doc of JSON content
         loader = JSONLoader(file_path=str(p), jq_schema=".", text_content=True)
         for d in loader.load():
            d.metadata.setdefault("source", p.name)
            yield d
      elif p.suffix.lower() == ".jsonl":
         for line_doc in TextLoader(str(p), encoding="utf-8").load():
            line_doc.metadata.setdefault("source", p.name)
            yield line_doc

def main():
   # print(Path(DATA_DIR))
   root = Path(DATA_DIR) / "eoc"
   root.mkdir(parents=True, exist_ok=True)

   # print(root)
   base_docs = list(load_docs(root))
   # print(base_docs)
   chunks = splitter.split_documents(base_docs)
   for d in chunks:
      d.metadata.setdefault("source", d.metadata.get("source", "unknown"))

   vs = Chroma(persist_directory=str(PDF_CHROMA_DIR), embedding_function=get_embedding_function())

   def make_id(doc, i: int) -> str:
      digest = hashlib.md5(doc.page_content.encode("utf-8")).hexdigest()[:12]
      return f"{doc.metadata.get('source','unknown')}::{i}::{digest}"

   vs.add_documents(chunks, ids=[make_id(d, i) for i, d in enumerate(chunks)])
   print(f"Added {len(chunks)} chunks from folder: {root} -> {PDF_CHROMA_DIR}")

if __name__ == "__main__":
    main()