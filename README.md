# Agente de CV — Mariana Lugo

Este repositorio contiene el agente conversacional que construí para el Reto IA de Banorte: un agente capaz de hablar sobre mi trayectoria profesional —experiencia, habilidades y proyectos— de forma natural, sin inventar información que no esté respaldada por mi CV real.

No lo pensé como un ejercicio de "conectar un LLM a un prompt con mi CV pegado". Lo armé como lo armaría para un caso de uso real: separando el conocimiento del comportamiento, dejando el proveedor de modelo intercambiable, y exponiéndolo con un contrato HTTP estándar (Open Responses) para que cualquier plataforma compatible —no solo la de este reto— pueda conectarse sin cambios.

## Demostración

El agente está desplegado y accesible en:

```
https://agente-cv-mariana.onrender.com
```

Un intercambio real, capturado directamente del endpoint en producción:

**Pregunta:** *"Cuéntame de tu experiencia en el BID"*

**Respuesta del agente:**

> Actualmente trabajo en el Banco Interamericano de Desarrollo desde junio de 2024, en la División de Protección Social y Mercados Laborales. Ha sido una experiencia muy enriquecedora donde he podido aplicar mis habilidades en ciencia de datos y análisis económico a temas de alto impacto social.
>
> Uno de mis primeros grandes proyectos fue diseñar flujos de trabajo basados en IA generativa para automatizar el análisis de más de 90 operaciones del BID, extrayendo y sintetizando evidencia sobre escalabilidad, capacidad institucional y diseño de intervenciones (...)
>
> También lideré un análisis regional sobre la economía de plataformas digitales en ocho países de América Latina, integrando datos administrativos con una encuesta que desarrollamos junto con Uber, evaluando ingresos, vulnerabilidad laboral y brechas de protección social. Ese trabajo resultó en una publicación técnica donde participé como coautora.

Lo interesante de probarlo no es solo que responde bien a preguntas directas, sino cómo se comporta en los bordes: si le preguntas algo que no está en mi CV (una opinión personal, un dato que no documenté), no lo inventa — lo dice explícitamente, porque el `system prompt` lo obliga a ceñirse al contexto recuperado.

Puedes reproducir esta misma prueba con:

```bash
curl -X POST https://agente-cv-mariana.onrender.com/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Cuéntame de tu experiencia en el BID"}'
```

El endpoint se mantiene despierto 24/7 mediante un monitor externo (UptimeRobot) que le hace ping cada 5 minutos — así no depende de la hora a la que alguien decida probarlo.

## Cómo está armado

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
Claude (API de Anthropic) con el contexto recuperado + historial de la conversación
      │
      ▼
Respuesta en el formato que exige la spec de Open Responses
```

Cuatro piezas, cada una con una responsabilidad clara:

- **`data/`** — el conocimiento. Tres documentos en markdown (experiencia, educación/habilidades, proyectos) que reflejan mi CV real.
- **`app/rag.py`** — la recuperación de contexto relevante para cada pregunta.
- **`app/llm.py`** — la llamada al modelo de lenguaje, aislada del resto.
- **`app/main.py`** — el servidor HTTP: parsea la solicitud, orquesta RAG + LLM, arma la respuesta en el formato que espera Open Responses.

## Por qué lo diseñé así

**RAG en vez de meter todo el CV en el prompt de sistema.** Podría haber pegado mi CV completo como texto fijo dentro del `system prompt` y listo — funciona, pero acopla el conocimiento al código. Con RAG, actualizar mi CV es editar un `.md` y volver a desplegar, sin tocar la lógica del agente. Y, más importante: al forzar al modelo a responder solo con lo que el retriever le entrega, reduzco el riesgo de que "rellene" con generalidades cuando no sabe algo.

**TF-IDF local en vez de un vector store con embeddings.** Evalué usar Chroma o FAISS con embeddings de OpenAI/Anthropic, pero para un corpus de tres documentos eso es sobre-ingeniería: agrega una dependencia externa, latencia de red y costo por cada llamada de embedding, sin ninguna ganancia real de calidad sobre un corpus tan pequeño. TF-IDF + similitud coseno, corriendo en memoria con scikit-learn, resuelve el mismo problema en milisegundos y sin llamadas externas. Si mi CV creciera a decenas de documentos, `app/rag.py` es el único archivo que tendría que tocar para migrar a un vector store real — el resto del sistema no se entera del cambio.

**Chunking por sub-sección temática, no por tamaño de caracteres.** Partir el texto cada 500 caracteres es la forma más común de hacerlo, pero corta ideas a la mitad (por ejemplo, dividir un proyecto en dos pedazos que pierden sentido por separado). En su lugar, parto cada documento por sus encabezados `##`, así cada chunk es una unidad completa: un puesto, un proyecto, un bloque de habilidades. Esto se nota directamente en la calidad de las respuestas.

**El endpoint es completamente stateless.** No guardo historial de conversación en ningún lado del servidor — cada llamada a `/v1/responses` recibe el historial completo en el campo `input`, tal como lo manda la plataforma en modo "reproducir transcripción". Esto simplifica mucho la operación: no hay base de datos de sesiones que mantener, no hay que preocuparse por expiración de estado, y el servicio puede escalar horizontalmente sin problema porque cualquier instancia puede atender cualquier request.

**El proveedor de LLM está aislado en un solo archivo.** Durante el desarrollo cambié dos veces de proveedor (probé con OpenAI antes de decidirme por Anthropic, por temas de crédito disponible en cada cuenta). Gracias a que `app/llm.py` expone una sola función (`call_llm`) con una firma fija, ese cambio no tocó nada de `app/main.py` ni de la lógica de RAG — es exactamente el tipo de desacoplamiento que uno quiere cuando no sabe de antemano si va a necesitar cambiar de modelo por costo, disponibilidad o rendimiento.

**Agent Card en `/.well-known/agent-card.json`.** Además del endpoint de Open Responses, expongo una tarjeta de agente en formato A2A con mis metadatos (nombre, descripción, capacidades, la URL de Open Responses). Esto le permite a plataformas compatibles —como la de este reto— autocompletar el formulario de registro con un solo campo (la URL base) en vez de llenarlo a mano, y en general es el tipo de detalle que facilita que un agente sea descubrible por otros sistemas sin coordinación manual.

**API key opcional (`AGENT_API_KEY`).** Dejé la protección por token como opcional y, por ahora, sin activar — prioricé la facilidad de registro en la plataforma del reto. En un entorno de producción real la activaría sin dudar: sin ella, cualquiera con la URL puede hacerle llamadas al endpoint y consumir mi crédito de la API de Anthropic. Lo dejo documentado como una decisión consciente, no como un descuido.

## Un par de cosas que aprendí desplegándolo

No todo salió a la primera. Vale la pena mencionarlo porque también es parte de "operar" un agente, no solo construirlo:

- Mi máquina tenía una versión de Python bastante vieja para lo que pedían las librerías modernas (FastAPI, Pydantic), así que tuve que instalar Python 3.11 con `pyenv` en paralelo, sin tocar el Python del sistema, para no romper nada más.
- El código original usaba sintaxis de anotaciones de tipos de Python 3.10+ (`str | None`), que Pydantic evalúa en tiempo de ejecución — así que tuve que reescribirlo con `typing.Optional` para que fuera compatible hacia atrás, en vez de asumir que todo el mundo corre la versión más reciente.
- Elegí Render sobre alternativas serverless porque necesitaba persistencia de un `Dockerfile` simple y build automático desde GitHub sin configuración adicional. La contraparte es que el plan gratuito duerme el servicio tras 15 minutos sin tráfico — lo resolví con un monitor externo (UptimeRobot) que le hace ping cada 5 minutos, en vez de pagar por un plan que nunca duerma, dado que el tráfico esperado para este reto no lo justifica.

## Correr localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y coloca tu ANTHROPIC_API_KEY
export $(grep -v '^#' .env | xargs)
python -m uvicorn app.main:app --reload
```

Probar:
```bash
curl -X POST http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Cuéntame sobre tu experiencia en el BID"}'
```

## Desplegar

Cualquier plataforma que corra un contenedor Docker sirve (Render, Railway, Fly.io, Azure Container Apps, Hugging Face Spaces). Así lo hice yo en Render:

1. Subí este repo a GitHub.
2. Creé un Web Service en Render apuntando al repo — detecta el `Dockerfile` automáticamente, no hace falta configurar build/start command a mano.
3. Configuré las variables de entorno `ANTHROPIC_API_KEY` y `MODEL_NAME` en el panel de Render.
4. Una vez desplegado, tomé la URL pública que me asignó (`https://agente-cv-mariana.onrender.com`) y la agregué como una variable más: `AGENT_BASE_URL`, para que la Agent Card quedara bien formada.
5. Configuré un monitor gratuito en UptimeRobot apuntando a `/health` cada 5 minutos, para que el servicio nunca se duerma por inactividad.

## Registrar el agente en la plataforma del reto

La forma más rápida: en el formulario "Añadir un agente", en el campo **"Importar desde tarjeta de agente"**, pegar la URL base del despliegue (sin `/v1`, ej. `https://agente-cv-mariana.onrender.com`) y darle a Importar — la plataforma lee `/.well-known/agent-card.json` y autocompleta Nombre, Descripción y URL base. Vale la pena revisar los campos igual después de importar, en particular que **URL base** haya quedado terminando en `/v1` y que **Estado de la conversación** esté en "Reproducir transcripción" (mi endpoint es stateless y espera el historial completo en cada llamada).

Si se prefiere llenar a mano en vez de importar:

| Campo | Valor |
|---|---|
| Nombre | CV de Mariana Lugo |
| Descripción | Agente conversacional sobre mi perfil profesional, experiencia y proyectos |
| URL base | `https://agente-cv-mariana.onrender.com/v1` |
| Clave de API | vacío (no configuré `AGENT_API_KEY` en este despliegue) |
| Estado de la conversación | "Reproducir transcripción" |
| Entrada de imágenes / archivos | apagado (este agente no las usa) |
