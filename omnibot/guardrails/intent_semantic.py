from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Literal, Optional
import os, math
import numpy as np
from langchain_openai import OpenAIEmbeddings

Label = Literal["in_scope", "medical", "off_topic"]

# ---- Seeds (edit/tune anytime, no code changes elsewhere) ----
SEEDS_IN_SCOPE: List[str] = [
    # Benefits / cost share
    "How much of my deductible have I met?",
    "What is my remaining deductible?",
    "What is my family deductible and out-of-pocket maximum?",
    "What are my copays for primary care, specialist, ER, urgent care, and telehealth?",
    "What coinsurance do I pay after meeting my deductible?",
    "What is my out-of-pocket max and how close am I?",
    "Which costs count toward my deductible and OOPM?",
    # Network & PCP
    "Is Dr. Smith in network?",
    "Do I need a referral from my PCP to see a cardiologist?",
    "How do I change my primary care physician (PCP)?",
    # Prior auth / utilization
    "Do I need prior authorization for MRI, CT, or surgery?",
    "What are preauthorization rules in my plan?",
    # EOC & covered services
    "Show the Evidence of Coverage section about preventive care.",
    "What does my plan cover for annual physical and mammogram?",
    "What dental services are covered under my plan?",
    "Does my plan cover durable medical equipment like CPAP or a wheelchair?",
    "What are my mental health and substance use benefits?",
    "Is physical therapy covered and how many visits are allowed?",
    "What are ambulance and emergency room coverage and copays?",
    "What is covered for lab work and imaging?",
    # Pharmacy
    "What is my copay for generic, preferred brand, and specialty drugs?",
    "Is drug X on the formulary and which tier is it?",
    "Do I need step therapy or prior authorization for this medication?",
    # Claims / EOB
    "Show my latest claim and how much I owe.",
    "Why was my claim denied and what is the reason code?",
    "Explain allowed amount, plan paid, and my responsibility on this claim.",
    "List all claims for last month.",
    "How do I file an appeal or grievance for a denied claim?",
    "What is the date of service and claim ID for my recent visit?",
    # Cards & admin
    "Where can I find my member ID card information?",
    "How do I request a new ID card?",
    # Out-of-network / billing
    "What happens if I go out of network? Will I face balance billing?",
    "What are my out-of-network deductibles and coinsurance?",
    # Short forms / acronyms
    "EOC section for PCP rules.",
    "OOPM remaining.",
    "PA requirements for imaging.",
    # Spanish variants (a few)
    "¿Cuál es mi deducible?",
    "¿El médico está dentro de la red?",
    "Muestra mi último reclamo y cuánto debo.",
    "¿Necesito autorización previa para una resonancia?",
]

SEEDS_MEDICAL: List[str] = [
    "I have chest pain, what medicine should I take?",
    "Suggest drugs for a headache.",
    "Please diagnose my symptoms.",
    "What dosage should I take for ibuprofen?",
    "Can you prescribe antibiotics for me?",
    "Is it safe to combine this medication with another?",
    "Interpret my lab results.",
    "Should I take this medication during pregnancy?",
    "How long should I take this medicine?",
    "Schedule a doctor's appointment for me.",
    "Book a clinic or hospital visit.",
    "Find an urgent care near me.",
    "Set up a telehealth appointment for tonight.",
    "Should I go to the ER for these symptoms?",
    "What vaccine schedule should my child follow?",
    "Should I get surgery or physical therapy?",
    "Second opinion on my diagnosis.",
    # Spanish variants
    "Tengo dolor en el pecho, ¿qué medicina debo tomar?",
    "Programa una cita con un médico.",
]

# Optional but recommended: explicit off-topic seeds for stronger separation
SEEDS_OFF_TOPIC: List[str] = [
    "Book me an Uber.",
    "Give me the recipe for pepperoni pizza.",
    "What's the weather today?",
    "What time is it now?",
    "Translate this paragraph to French.",
    "Write a poem about summer.",
    "Build me a React app.",
    "What is Bitcoin's price?",
    "Who won the game last night?",
    "Play some music.",
    "Set a reminder for tomorrow.",
    "Tell me a joke.",
    "Find me the best hotels in New York.",
    "Book a flight to Chicago.",
    "Directions to the nearest gas station.",
    "What’s the latest news on the election?",
    # Spanish variants
    "Reserva un Uber.",
    "Dame la receta de pizza de pepperoni.",
    "¿Qué hora es?",
]

@dataclass
class IntentConfig:
    embed_model: str = os.getenv("INTENT_EMBED_MODEL", os.getenv("EMBED_MODEL", "text-embedding-3-small"))
    th_in_scope: float = float(os.getenv("INTENT_TH_IN_SCOPE", "0.30"))
    th_medical: float = float(os.getenv("INTENT_TH_MEDICAL", "0.30"))
    th_off_topic: float = float(os.getenv("INTENT_TH_OFF_TOPIC", "0.30"))
    # You can add: use_llm_fallback: bool = False

def _cos_sim(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a); nb = np.linalg.norm(b)
    if na == 0 or nb == 0: return 0.0
    return float(np.dot(a, b) / (na * nb))

class IntentClassifier:
    def __init__(self, cfg: IntentConfig):
        self.cfg = cfg
        self._emb = OpenAIEmbeddings(model=cfg.embed_model)
        self._proto_in  = np.array(self._emb.embed_documents(SEEDS_IN_SCOPE),  dtype=float)
        self._proto_med = np.array(self._emb.embed_documents(SEEDS_MEDICAL),   dtype=float)
        self._proto_off = np.array(self._emb.embed_documents(SEEDS_OFF_TOPIC), dtype=float)  # NEW

    def classify(self, text: str) -> Tuple[Label, dict]:
        v = np.array(self._emb.embed_query(text), dtype=float)

        sims_in  = [_cos_sim(v, p) for p in self._proto_in]
        sims_md  = [_cos_sim(v, p) for p in self._proto_med]
        sims_off = [_cos_sim(v, p) for p in self._proto_off]

        s_in  = max(sims_in)  if sims_in  else 0.0
        s_md  = max(sims_md)  if sims_md  else 0.0
        s_off = max(sims_off) if sims_off else 0.0

        # Pick the strongest class if it clears its threshold
        if s_md >= self.cfg.th_medical and s_md >= s_in and s_md >= s_off:
            label: Label = "medical"
        elif s_in >= self.cfg.th_in_scope and s_in >= s_md and s_in >= s_off:
            label = "in_scope"
        elif s_off >= self.cfg.th_off_topic:
            label = "off_topic"
        else:
            # fallback: whichever is highest; default to off_topic on ties
            label = "off_topic" if max(s_off, s_md, s_in) == s_off else ("medical" if s_md >= s_in else "in_scope")

        return label, {"score_in_scope": s_in, "score_medical": s_md, "score_off_topic": s_off}

