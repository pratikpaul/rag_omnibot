from __future__ import annotations
from langchain_ollama import OllamaLLM
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from omnibot.config.prompts import ROUTER_PROMPT
from omnibot.config.constants import ROUTER_MODEL, ROUTER_KWARGS

router_prompt = ChatPromptTemplate.from_template(ROUTER_PROMPT)
router_llm = OllamaLLM(model=ROUTER_MODEL, **ROUTER_KWARGS)
router_chain = router_prompt | router_llm | StrOutputParser()

async def fast_route(question: str) -> str:
    try:
        out = await router_chain.ainvoke({"question": question})
        ans = (out or "").strip().lower()
        if ans in {"pdf", "claims", "both"}:
            return ans
    except Exception:
        pass
    q = (question or "").lower()
    claims_kw = ("eob", "explanation of benefit", "claim", "adjudication", "cpt", "icd", "diagnosis", "procedure", "denial")
    pdf_kw = ("evidence of coverage", "eoc", "covered", "copay", "coinsurance", "deductible", "benefits chart", "vision", "dental")
    is_claims = any(k in q for k in claims_kw)
    is_pdf = any(k in q for k in pdf_kw)
    if is_claims and is_pdf: return "both"
    if is_claims: return "claims"
    if is_pdf: return "pdf"
    return "pdf"