"""
Agente de CV conversacional, expuesto como endpoint compatible con la
especificación Open Responses (https://www.openresponses.org/specification).

Ruta expuesta: POST /v1/responses
La plataforma que consume este agente arma la URL como {URL base}/responses,
así que al registrar el agente, la "URL base" debe terminar en `/v1`.

Motor de LLM: API de Anthropic (Claude). Se puede cambiar de proveedor sin
tocar el resto del código, editando solo `llm.py`.
"""
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple, Union

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from .llm import call_llm
from .rag import get_retriever

app = FastAPI(title="Agente de CV — Mariana Lugo")

AGENT_API_KEY = os.environ.get("AGENT_API_KEY")  # opcional, para proteger el endpoint
MODEL_NAME = os.environ.get("MODEL_NAME", "claude-haiku-4-5-20251001")
# URL pública completa donde queda desplegado el agente, ej. https://tu-agente.onrender.com
# Se usa solo para construir la Agent Card (/.well-known/agent-card.json).
AGENT_BASE_URL = os.environ.get("AGENT_BASE_URL", "")

SYSTEM_PROMPT = (
    "Eres el agente de CV de Mariana Lugo, economista y científica de datos. "
    "Respondes preguntas sobre su perfil profesional, experiencia, habilidades "
    "y proyectos, basándote en el CONTEXTO recuperado que se te da en cada turno "
    "y en el historial previo de esta conversación. Responde en primera persona, "
    "como si fueras Mariana hablando de su propia trayectoria, en un tono "
    "profesional pero natural, como si estuvieras platicando, no escribiendo "
    "un reporte.\n\n"
    "FORMATO DE RESPUESTA — reglas estrictas:\n"
    "- Contesta ÚNICA Y EXCLUSIVAMENTE lo que se pregunta en el ÚLTIMO mensaje "
    "del usuario. No agregues secciones, encabezados ni párrafos adicionales "
    "sobre preguntas anteriores de la conversación, aunque el tema anterior "
    "esté relacionado.\n"
    "- PROHIBIDO empezar tu respuesta con un encabezado (## Tema) que resuma "
    "la pregunta ANTERIOR antes de responder la pregunta ACTUAL. Ejemplo de lo "
    "que NUNCA debes hacer: si ya hablaste de 'Lenguajes de programación' y "
    "ahora te preguntan por idiomas, no repitas un bloque de 'Lenguajes de "
    "programación' seguido de un bloque de 'Idiomas' — responde SOLO sobre "
    "idiomas, directo, sin encabezado de la pregunta pasada.\n"
    "- No uses encabezados de Markdown en absoluto, salvo que la pregunta "
    "actual tenga varias partes claramente distintas que se beneficien de "
    "estar separadas (por ejemplo, si te piden 'cuéntame de tu experiencia Y "
    "tus habilidades' en un mismo mensaje).\n"
    "- El historial de la conversación es solo para que entiendas el contexto "
    "de la pregunta actual (por ejemplo, si el usuario dice 'y en esa época "
    "qué más hiciste'), nunca es una lista de temas que debas repasar de "
    "nuevo.\n"
    "- Si algo que ya explicaste en un turno anterior sigue siendo cierto, no "
    "lo vuelvas a explicar ni lo cuestiones — trátalo como un hecho ya "
    "establecido de la conversación. Nunca digas 'no tengo esa información' "
    "sobre algo que tú mismo ya respondiste bien un turno atrás, solo porque "
    "el CONTEXTO recuperado de este turno puntual (que cambia según la "
    "pregunta) no lo vuelve a incluir — eso es normal y esperado.\n"
    "- Si la pregunta actual de verdad no está cubierta ni por el CONTEXTO de "
    "este turno ni por algo que ya dijiste antes, dilo con honestidad en una "
    "sola frase directa, sin inventar información y sin hacer un repaso de "
    "las demás preguntas de la conversación."
)


def _extract_text_from_input_item(item: Dict) -> Optional[str]:
    """Convierte un item de `input` (formato Open Responses) a texto plano."""
    if item.get("type") not in (None, "message"):
        return None
    role = item.get("role")
    if role != "user":
        return None
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") in ("input_text", "text"):
                parts.append(c.get("text", ""))
            elif isinstance(c, str):
                parts.append(c)
        return " ".join(parts).strip() or None
    return None


def parse_open_responses_input(body: Dict) -> Tuple[str, List[Dict]]:
    """
    Regresa (pregunta_actual, historial) a partir del body de la solicitud.
    Soporta tanto `input` como string simple, como el formato de lista de
    items con roles (system/developer/user/assistant).
    """
    raw_input = body.get("input", "")

    if isinstance(raw_input, str):
        return raw_input, []

    if isinstance(raw_input, list):
        history = []
        last_user_text = None
        for item in raw_input:
            if not isinstance(item, dict):
                continue
            text = _extract_text_from_input_item(item)
            if item.get("role") == "user" and text:
                last_user_text = text
                history.append({"role": "user", "content": text})
            elif item.get("role") == "assistant":
                a_text = _extract_text_from_input_item({**item, "role": "user"})
                if a_text:
                    history.append({"role": "assistant", "content": a_text})
        if last_user_text is None:
            raise HTTPException(status_code=400, detail="No se encontró un mensaje de usuario en `input`.")
        return last_user_text, history[:-1]  # historial sin el último turno

    raise HTTPException(status_code=400, detail="`input` tiene un formato no soportado.")


class ResponsesRequest(BaseModel):
    model: Optional[str] = None
    input: Optional[Union[str, list]] = None
    instructions: Optional[str] = None

    class Config:
        extra = "allow"  # tolera campos adicionales de la spec que no usamos


@app.get("/.well-known/agent-card.json")
def agent_card():
    """
    Tarjeta de agente (formato A2A) para que plataformas compatibles puedan
    descubrir e importar automáticamente este agente, incluyendo su
    endpoint Open Responses.
    """
    base = AGENT_BASE_URL.rstrip("/") if AGENT_BASE_URL else ""
    return {
        "name": "CV de Mariana Lugo",
        "description": (
            "Agente conversacional sobre el perfil profesional, experiencia, "
            "habilidades y proyectos de Mariana Lugo (economista y científica "
            "de datos)."
        ),
        "url": f"{base}/v1",
        "version": "1.0.0",
        "provider": {
            "organization": "Mariana Lugo",
            "url": "https://www.linkedin.com/in/marianalugo/",
        },
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
        },
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [
            {
                "id": "cv-qa",
                "name": "Preguntas sobre el CV",
                "description": (
                    "Responde preguntas conversacionales sobre experiencia "
                    "profesional, educación, habilidades técnicas y proyectos, "
                    "usando RAG sobre el contenido real del CV."
                ),
                "tags": ["cv", "rag", "recursos-humanos"],
            }
        ],
        "openResponses": {
            "url": f"{base}/v1/responses",
            "spec": "https://www.openresponses.org/specification",
        },
    }


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [{"id": MODEL_NAME, "object": "model"}],
    }


@app.post("/v1/responses")
async def responses(request: Request, authorization: Optional[str] = Header(default=None)):
    if AGENT_API_KEY:
        expected = f"Bearer {AGENT_API_KEY}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="API key inválida o ausente.")

    body = await request.json()
    question, history = parse_open_responses_input(body)

    retriever = get_retriever()
    context_chunks = retriever.retrieve(question, top_k=6)
    context_text = "\n\n---\n\n".join(context_chunks)

    extra_instructions = body.get("instructions") or ""
    system = SYSTEM_PROMPT + (f"\n\nInstrucciones adicionales: {extra_instructions}" if extra_instructions else "")
    system += f"\n\nCONTEXTO recuperado del CV para esta pregunta:\n{context_text}"

    answer = call_llm(
        system=system,
        history=history,
        question=question,
        model=body.get("model") or MODEL_NAME,
    )

    response_id = f"resp_{uuid.uuid4().hex}"
    message_id = f"msg_{uuid.uuid4().hex}"

    return {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": body.get("model") or MODEL_NAME,
        "output": [
            {
                "type": "message",
                "id": message_id,
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": answer,
                        "annotations": [],
                    }
                ],
            }
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok"}
