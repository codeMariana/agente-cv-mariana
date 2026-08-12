# Agente de CV — Mariana Lugo

Agente conversacional (RAG) sobre el perfil profesional de Mariana Lugo, expuesto
como endpoint compatible con la especificación [Open Responses](https://www.openresponses.org/specification).

## Arquitectura

```
Pregunta del usuario
      │
      ▼
POST /v1/responses  (FastAPI)
      │
      ▼
Retriever TF-IDF sobre data/*.md  →  top-4 chunks relevantes
      │
      ▼
Claude (API de Anthropic) con contexto recuperado + historial
      │
      ▼
Respuesta en formato Open Responses
```

## Decisiones técnicas

- **RAG en vez de prompt estático**: separar el conocimiento (`data/*.md`) del
  código permite actualizar el CV sin re-desplegar el agente, y reduce el
  riesgo de alucinaciones al forzar al modelo a responder solo con contexto
  recuperado.
- **TF-IDF local en vez de embeddings + vector store externo**: el corpus es
  pequeño (unos pocos documentos de CV), así que un servicio de embeddings
  agregaría costo y latencia sin beneficio real. `app/rag.py` es el único
  punto que habría que tocar para migrar a Chroma/FAISS si el corpus creciera.
- **Chunking por sub-sección (`##`)** en vez de por tamaño fijo de caracteres:
  mantiene unidades temáticas completas (un proyecto, una experiencia) en vez
  de cortar a la mitad una idea.
- **Historial stateless**: el endpoint recibe todo el historial en cada
  llamada (`input`), consistente con el modo "reproducir transcripción" de la
  plataforma — no se guarda estado en el servidor.
- **Modelo configurable** vía `MODEL_NAME`, y proveedor aislado en `app/llm.py`
  para poder cambiar de LLM sin tocar la lógica de RAG ni el contrato HTTP.
- **`AGENT_API_KEY` opcional**: si se define, el endpoint exige
  `Authorization: Bearer <key>`; si no, queda abierto (útil para pruebas).
- **Agent Card (`/.well-known/agent-card.json`)**: expone los metadatos del
  agente en formato A2A, incluyendo la URL de Open Responses, para que
  plataformas compatibles (como la del reto) puedan importarlo automáticamente
  en vez de llenar el formulario campo por campo a mano.

## Correr localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y coloca tu ANTHROPIC_API_KEY
export $(cat .env | xargs)
uvicorn app.main:app --reload
```

Probar:
```bash
curl -X POST http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Cuéntame sobre tu experiencia en el BID"}'
```

## Desplegar

Cualquier plataforma que corra un contenedor Docker sirve (Render, Railway,
Fly.io, Azure Container Apps, Hugging Face Spaces). Pasos generales:

1. Sube este repo a GitHub.
2. En la plataforma elegida, crea un servicio nuevo apuntando al repo (build
   con el `Dockerfile` incluido).
3. Configura la variable de entorno `ANTHROPIC_API_KEY` (y opcionalmente
   `AGENT_API_KEY`, `MODEL_NAME`) en el panel de la plataforma.
4. Despliega. Anota la URL pública que te asigne, por ejemplo
   `https://tu-agente.onrender.com`.
5. Vuelve a las variables de entorno y agrega `AGENT_BASE_URL` con esa misma
   URL (sin `/v1` al final). Esto hace que `/.well-known/agent-card.json`
   quede bien formado. Redeploy si tu plataforma no lo hace automático al
   guardar la variable.

## Registrar el agente en la plataforma del reto

**Opción rápida**: en el formulario "Añadir un agente", pega tu URL desplegada
(sin `/v1`, ej. `https://tu-agente.onrender.com`) en el campo **"Importar
desde tarjeta de agente"** y dale a Importar — debería autocompletar Nombre,
Descripción y URL base leyendo `/.well-known/agent-card.json`. Revisa los
campos igual, por si algo no se llenó como esperabas.

**Opción manual**, en **Agentes → Añadir un agente**:

| Campo | Valor |
|---|---|
| Nombre | CV de Mariana Lugo |
| Descripción | Agente conversacional sobre mi perfil profesional, experiencia y proyectos |
| URL base | `https://tu-agente.onrender.com/v1`  *(las solicitudes van a `{URL base}/responses`)* |
| Clave de API | el valor de `AGENT_API_KEY`, si lo configuraste (déjalo vacío si no) |
| Estado de la conversación | "Reproducir transcripción" |
| Entrada de imágenes / archivos | apagado (este agente no las usa) |
