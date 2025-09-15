"""Ingestion entry points to build vector stores."""

from .claims_ingest import main as build_claims_store
from .pdf_ingest import main as build_pdf_store

__all__ = ["build_claims_store", "build_pdf_store"]
