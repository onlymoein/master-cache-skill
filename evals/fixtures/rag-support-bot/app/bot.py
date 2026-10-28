import datetime

import anthropic

client = anthropic.Anthropic()
POLICY_DOCS = open("docs/policies.md").read()  # ~20k tokens, changes monthly


def answer(tenant_id: str, user_question: str, retrieved: list[str]) -> str:
    system = (
        f"Current time: {datetime.datetime.now().isoformat()}\n"
        f"Tenant: {tenant_id}\n"
        f"Retrieved context:\n{chr(10).join(retrieved)}\n\n"
        f"Company policies:\n{POLICY_DOCS}"
    )
    msg = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user_question}],
    )
    return msg.content[0].text
