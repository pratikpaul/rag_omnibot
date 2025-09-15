from __future__ import annotations
from pathlib import Path
import hashlib
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from omnibot.embeddings.openai_embedder import get_embedding_function
from omnibot.config.constants import FLAT_DIR, CLAIMS_CHROMA_DIR, CHUNK_SIZE, CHUNK_OVERLAP

md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("##", "section")])
char_splitter = RecursiveCharacterTextSplitter(
   chunk_size=CHUNK_SIZE,
   chunk_overlap=CHUNK_OVERLAP,
   separators=["\n\n", "\n", ". ", " "]
)

def load_and_chunk(path: Path):
   text = path.read_text(encoding="utf-8")
   docs = char_splitter.split_documents(md_splitter.split_text(text))
   for d in docs:
      d.metadata.setdefault("source", path.name)
      d.metadata.setdefault("filepath", str(path))
   return docs

def main():
   print("######################")
   print(Path(FLAT_DIR))
   print("######################")
   files = sorted(Path(FLAT_DIR).glob("*.txt"))
   all_docs = []
   for p in files:
      all_docs.extend(load_and_chunk(p))

   embeddings = get_embedding_function()
   persist_dir = Path(CLAIMS_CHROMA_DIR)
   persist_dir.mkdir(parents=True, exist_ok=True)
   vectorstore = Chroma(persist_directory=str(CLAIMS_CHROMA_DIR), embedding_function=embeddings)

   def make_id(doc, idx: int) -> str:
      digest = hashlib.md5(doc.page_content.encode("utf-8")).hexdigest()[:12]
      return f"{doc.metadata.get('source','unknown')}::{idx}::{digest}"

   print("*******************")
   print("Length of all_docs: " + str(len(all_docs)))
   print("*******************")
   ids = [make_id(d, i) for i, d in enumerate(all_docs)]
   vectorstore.add_documents(all_docs, ids=ids)
   print(f"Added {len(all_docs)} chunks from {len(files)} files -> {CLAIMS_CHROMA_DIR}")

if __name__ == "__main__":
   main()