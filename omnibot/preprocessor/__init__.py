"""FHIR preprocessing utilities (JSON Bundle → flat text)."""

from .fhir_preprocessor import (
    flatten_eob_bundle,
    extract_patient_from_eob_bundle,
    derive_eob_summary,
    flatten,
    main as preprocess_fhir,
)

__all__ = [
    "flatten_eob_bundle",
    "extract_patient_from_eob_bundle",
    "derive_eob_summary",
    "flatten",
    "preprocess_fhir",
]
