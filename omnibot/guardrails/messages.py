from typing import Optional, Literal
Label = Literal["in_scope", "medical", "off_topic"]

def guardrail_reply(kind: Label) -> Optional[str]:
    if kind == "off_topic":
        return (
            "I’m set up to help with your health plan—things like benefits and costs in your "
            "Evidence of Coverage (EOC), and questions about your claims (amounts, dates, status, "
            "deductible, out-of-pocket, copays, etc.).\n\n"
            "Try asking, for example: “What’s my specialist copay?” or “Show my latest claim and "
            "how much I owe.”"
        )
    if kind == "medical":
        return (
            "I’m not able to provide medical advice or schedule care directly, but I’m here for your "
            "plan and claims questions.\n\n"
            "If you’re feeling unwell, a clinician can help: you can book a **virtual doctor visit** "
            "through Zocdoc. If this might be urgent (e.g., chest pain or trouble breathing), please "
            "seek in-person care or call your local emergency number."
        )
    return None
