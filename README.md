# Agente de CV — Mariana Lugo

Este es el agente que construí para el Reto IA de Banorte: un agente conversacional que puede hablar sobre mi trayectoria —experiencia, habilidades, proyectos— sin inventar cosas que no estén en mi CV real.

Armé el proyecto separando el conocimiento del comportamiento del agente, dejando el proveedor de modelo fácil de cambiar, y exponiéndolo con un contrato HTTP estándar (Open Responses) para que cualquier plataforma compatible pueda conectarse sin tocar el código.

## Demostración

El agente está desplegado y accesible en:

```
https://agente-cv-mariana.onrender.com
```

Esto es un intercambio real, tomado directamente del endpoint en producción:

**Pregunta:** *"Cuéntame de la experiencia de Mariana en el BID"*

**Respuesta del agente:**

> Actualmente trabaja en el Banco Interamericano de Desarrollo desde junio de 2024, en la División de Protección Social y Mercados Laborales. Ha sido una experiencia muy enriquecedora donde ha podido aplicar mis habilidades en ciencia de datos y análisis económico a temas de alto impacto social.
>
> Uno de sus primeros grandes proyectos fue diseñar flujos de trabajo basados en IA generativa para automatizar el análisis de más de 90 operaciones del BID, extrayendo y sintetizando evidencia sobre escalabilidad, capacidad institucional y diseño de intervenciones (...)
>
> También lideró un análisis regional sobre la economía de plataformas digitales en ocho países de América Latina, integrando datos administrativos con una encuesta que desarrollamos junto con Uber, evaluando ingresos, vulnerabilidad laboral y brechas de protección social. Ese trabajo resultó en una publicación técnica donde participé como coautora.

Lo que más me interesaba probar no era si respondía bien a preguntas obvias, sino qué hacía cuando le preguntaba algo que no está documentado en mi CV. Ahí es donde se nota si el diseño funciona: en vez de inventar una respuesta genérica, el agente dice abiertamente que no tiene esa información, porque el prompt lo obliga a ceñirse solo al contexto que le llega del retriever.

Se puede reproducir la misma prueba con:

```bash
curl -X POST https://agente-cv-mariana.onrender.com/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Cuéntame de tu experiencia en el BID"}'
```

El servicio se mantiene despierto todo el tiempo gracias a un monitor externo (UptimeRobot) que le hace ping cada 5 minutos, así que no depende de a qué hora alguien decida probarlo.

## Cómo está armado

```
Pregunta del usuario
      │
      ▼
POST /v1/responses  (FastAPI)
      │
      ▼
Retriever TF-IDF sobre data/*.md  →  chunks relevantes
      │
      ▼
Claude, con el contexto recuperado + historial de la conversación
      │
      ▼
Respuesta en el formato de Open Responses
```

`data/` tiene el conocimiento: tres archivos en markdown con mi experiencia, mi educación/habilidades y mis proyectos, escritos a partir de mi CV real. `app/rag.py` se encarga de buscar qué fragmentos son relevantes para cada pregunta. `app/llm.py` solo llama al modelo, sin saber nada de RAG ni de HTTP. Y `app/main.py` amarra todo: recibe la solicitud, junta RAG con el LLM, arma la respuesta en el formato que pide Open Responses.

## Decisiones técnicas

Podría haber puesto todo mi CV como texto fijo dentro del system prompt. Funciona, pero me generaba dos problemas: primero, actualizar mi CV significaría editar código y volver a desplegar cada vez; segundo, un modelo con todo el texto disponible tiende más a "rellenar" con generalidades cuando algo no está claro. Con RAG, el modelo solo ve lo que el retriever considera relevante para esa pregunta puntual, y eso lo mantiene más honesto.

Para la recuperación pensé en usar embeddings con un vector store (Chroma, FAISS), que es lo que normalmente se recomienda para RAG. Pero mi corpus son tres documentos. Meter un servicio de embeddings ahí es agregar una dependencia externa, latencia de red y costo, por un beneficio que no vas a notar con un corpus tan chico. Terminé usando TF-IDF con similitud coseno, corriendo en memoria con scikit-learn — resuelve exactamente el mismo problema, en milisegundos, sin llamar a nada afuera. Si algún día mi CV creciera a decenas de documentos, `app/rag.py` es el único archivo que tocaría para migrar a algo más sofisticado.

Una decisión más chica pero que sí se nota: en vez de partir el texto cada N caracteres (lo más común), parto cada documento por sus encabezados. Así cada chunk es una unidad completa —un puesto, un proyecto— en vez de un pedazo de idea cortado a la mitad. Lo probé de las dos formas al principio y la diferencia en la calidad de las respuestas fue bastante notoria.

El endpoint no guarda ningún estado. Cada llamada llega con el historial completo de la conversación (el modo "reproducir transcripción" de la plataforma), y yo simplemente lo proceso y respondo — no hay sesiones que mantener ni memoria que expire. Esto también significa que puedo tener varias instancias del servicio corriendo sin que se pisen entre ellas.

Durante el desarrollo cambié de proveedor de LLM dos veces —empecé con Anthropic, probé OpenAI cuando tuve problemas de crédito, y terminé regresando a Anthropic. El hecho de que ese cambio solo haya tocado un archivo (`app/llm.py`) y nada más del sistema confirma que valió la pena aislarlo desde el inicio; no sabía de antemano si iba a necesitar cambiar de proveedor por costo o disponibilidad, y resultó que sí.

También expongo una tarjeta de agente en `/.well-known/agent-card.json`, siguiendo el formato A2A, con mis metadatos y la URL de Open Responses. La idea es que una plataforma compatible pueda autocompletar el registro con solo mi dominio, en vez de que alguien tenga que llenar el formulario campo por campo a mano.

Y dejé la protección por API key como opcional, sin activarla por ahora, para simplificar el registro en la plataforma del reto. Lo pienso como una decisión consciente, no un descuido: en un entorno real la activaría de inmediato, porque sin ella cualquiera con la URL puede pegarle al endpoint y consumir mi crédito de la API.

## Principales retos

Mi máquina tenía una versión de Python demasiado vieja para las librerías que estaba usando (FastAPI, Pydantic), así que tuve que instalar una versión más nueva con pyenv, en paralelo al Python del sistema, para no romper nada más en la máquina.

El código utiliza una sintaxis de tipos de Python 3.10+ (`str | None`), que Pydantic evalúa en tiempo real al validar las solicitudes. Tuve que reescribirlo con `typing.Optional` para que funcionara en versiones más viejas — un recordatorio de que no todo el mundo va a correr esto con el Python más reciente.

Elegí Render para el despliegue porque solo necesitaba un Dockerfile simple y build automático desde GitHub, sin configurar nada extra. El costo de eso es que el plan gratuito duerme el servicio después de 15 minutos sin tráfico. En vez de pagar por un plan que nunca duerma (que para el tráfico que espera este reto no se justifica), configuré un monitor gratuito que lo mantiene despierto con pings periódicos.
