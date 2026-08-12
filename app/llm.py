import os
from typing import Optional

import anthropic

_client = None  # type: Optional[anthropic.Anthropic]


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Falta la variable de entorno ANTHROPIC_API_KEY. "
                "Configúrala en tu plataforma de despliegue."
            )
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def call_llm(system, history, question, model):
    messages = [{"role": h["role"], "content": h["content"]} for h in history]
    messages.append({"role": "user", "content": question})

    client = _get_client()
    response = client.messages.create(
        model=model,
        max_tokens=1000,
        system=system,
        messages=messages,
    )
    return "".join(block.text for block in response.content if block.type == "text")
