"""Legal Compliance Agent — Day 9 Stage 3, wrapped for production."""
import os
import json
import tempfile
import logging

from langchain_core.tools import tool
from langchain_google_vertexai import ChatVertexAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vertex AI credentials — write JSON from env var to temp file at startup
# ---------------------------------------------------------------------------

def setup_vertex_credentials(credentials_json: str):
    if not credentials_json:
        return
    try:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(credentials_json)
        tmp.flush()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name
        logger.info(f"Vertex AI credentials written to {tmp.name}")
    except Exception as e:
        logger.error(f"Failed to write Vertex credentials: {e}")


# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------

LEGAL_KNOWLEDGE = [
    {
        "id": "nda_breach",
        "keywords": ["nda", "non-disclosure", "confidential", "trade secret", "breach"],
        "text": (
            "NDA breaches trigger contractual and statutory liability. Under the DTSA "
            "(18 U.S.C. § 1836): injunctive relief, actual damages + unjust enrichment, "
            "exemplary damages up to 2x for willful misappropriation, and attorney's fees."
        ),
    },
    {
        "id": "tax_evasion",
        "keywords": ["tax", "evasion", "irs", "penalty", "fraud", "revenue", "overseas"],
        "text": (
            "Tax evasion (26 U.S.C. § 7201): felony with up to $250K fine and 5 years prison. "
            "Civil fraud penalty: 75% of underpayment (IRC § 6663). FBAR penalties up to $100K "
            "or 50% of account balance per violation for unreported overseas income."
        ),
    },
    {
        "id": "data_privacy",
        "keywords": ["data", "privacy", "user", "consent", "gdpr", "ccpa", "sharing"],
        "text": (
            "Sharing user data without consent violates: CCPA (fines up to $7,500 per intentional "
            "violation), GDPR (fines up to 4% of global revenue or EUR 20M), FTC Act Section 5. "
            "Class action lawsuits under state privacy laws."
        ),
    },
    {
        "id": "sox_compliance",
        "keywords": ["sox", "sarbanes", "compliance", "sec", "financial", "reporting"],
        "text": (
            "SOX violations: CEO/CFO certification of false financials — up to $5M fine and "
            "20 years prison (§ 906). Destruction of records — up to 20 years (§ 802)."
        ),
    },
]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def search_legal_database(query: str) -> str:
    """Search the legal knowledge base for relevant statutes and legal principles.

    Args:
        query: Natural language search query about a legal topic.
    """
    query_words = set(query.lower().split())
    scored = []
    for entry in LEGAL_KNOWLEDGE:
        overlap = len(query_words & set(entry["keywords"]))
        if overlap > 0:
            scored.append((overlap, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:2]
    if not top:
        return "No relevant legal sources found."
    return "\n\n".join(f"[{e['id']}] {e['text']}" for _, e in top)


@tool
def calculate_penalty(violation_type: str, severity: str, annual_revenue: float) -> str:
    """Calculate estimated legal penalties based on violation type, severity, and revenue.

    Args:
        violation_type: Type of violation (e.g., 'tax_evasion', 'data_privacy').
        severity: Severity level ('low', 'medium', 'high').
        annual_revenue: Company's annual revenue in USD.
    """
    multipliers = {"low": 0.01, "medium": 0.05, "high": 0.10}
    multiplier = multipliers.get(severity.lower(), 0.05)
    base = annual_revenue * multiplier
    extras = {
        "tax": "Plus criminal charges (up to 5 years) and 75% civil fraud penalty.",
        "privacy": "Plus GDPR fines up to 4% of global revenue and class action exposure.",
        "contract": "Plus consequential damages, attorney's fees, and possible injunction.",
    }
    extra = next((v for k, v in extras.items() if k in violation_type.lower()), "Additional regulatory sanctions may apply.")
    return (
        f"Penalty Estimate for {violation_type} ({severity} severity):\n"
        f"  Base penalty: ${base:,.2f}\n"
        f"  Revenue basis: ${annual_revenue:,.2f}\n"
        f"  {extra}"
    )


@tool
def check_compliance_requirements(industry: str, company_size: str) -> str:
    """Check which regulatory compliance frameworks apply to a company.

    Args:
        industry: The company's industry (e.g., 'technology', 'finance', 'healthcare').
        company_size: Company size ('startup', 'mid-size', 'enterprise').
    """
    frameworks = {
        "technology": ["CCPA/CPRA", "GDPR (if EU users)", "FTC Act Section 5", "SOC 2"],
        "finance": ["SOX", "BSA/AML", "Dodd-Frank", "SEC Regulations"],
        "healthcare": ["HIPAA", "HITECH Act", "FTC Health Breach Notification"],
    }
    size_extras = {
        "startup": "Consider: SOC 2 Type II for investor confidence.",
        "mid-size": "Consider: dedicated compliance officer and annual audits.",
        "enterprise": "Required: full compliance program, board oversight, whistleblower hotline.",
    }
    applicable = frameworks.get(industry.lower(), ["FTC Act Section 5", "State consumer protection laws"])
    size_note = size_extras.get(company_size.lower(), "")
    return (
        f"Applicable frameworks for {industry} ({company_size}):\n"
        f"  {', '.join(applicable)}\n"
        f"  {size_note}"
    )


TOOLS = [search_legal_database, calculate_penalty, check_compliance_requirements]

SYSTEM_PROMPT = (
    "You are a legal analyst agent. You have access to tools for searching legal databases, "
    "calculating penalties, and checking compliance requirements. Use these tools to build "
    "a comprehensive analysis. Keep your final answer concise and under 400 words."
)


def get_llm(project: str, location: str, model: str) -> ChatVertexAI:
    return ChatVertexAI(
        model=model,
        project=project,
        location=location,
        temperature=0.3,
        model_kwargs={"thinking_config": {"thinking_budget": 0}},
    )


async def run_agent(
    question: str, project: str, location: str, model: str,
    history: list | None = None,
) -> str:
    from langgraph.prebuilt import create_react_agent

    def extract_text(content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        return str(content)

    llm = get_llm(project, location, model)
    graph = create_react_agent(model=llm, tools=TOOLS, prompt=SYSTEM_PROMPT)
    messages = list(history or []) + [{"role": "user", "content": question}]
    inputs = {"messages": messages}

    final_answer = ""
    async for chunk in graph.astream(inputs, stream_mode="updates"):
        for node_name, update in chunk.items():
            for msg in update.get("messages", []):
                if msg.type == "ai" and msg.content:
                    final_answer = extract_text(msg.content)

    return final_answer or "Agent did not produce a final answer."
