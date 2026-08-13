# Agente de CV — Mariana Lugo

Este es el agente que construí para el Reto IA de Banorte: un agente conversacional que puede hablar sobre mi trayectoria —experiencia, habilidades, proyectos— sin inventar cosas que no estén en mi CV real.

Armé  el reto como un problema de negocio real: separé el conocimiento del comportamiento del agente, dejando el proveedor de modelo fácil de cambiar, y exponiéndolo con un contrato HTTP estándar (Open Responses) para que cualquier plataforma compatible pueda conectarse sin tocar el código.

## Demostración

El agente está desplegado y accesible en:

```
https://agente-cv-mariana.onrender.com
```

Esto es un intercambio real, tomado directamente del endpoint en producción:

**Pregunta:** *"Cuéntame de su experiencia en el BID"*

**Respuesta del agente:**

> Actualmente trabaja en el Banco Interamericano de Desarrollo desde junio de 2024, en la División de Protección Social y Mercados Laborales. Ha sido una experiencia muy enriquecedora donde ha podido aplicar mis habilidades en ciencia de datos y análisis económico a temas de alto impacto social.
>
> Uno de sus primeros grandes proyectos fue diseñar flujos de trabajo basados en IA generativa para automatizar el análisis de más de 90 operaciones del BID, extrayendo y sintetizando evidencia sobre escalabilidad, capacidad institucional y diseño de intervenciones (...)
>
> También lideró un análisis regional sobre la economía de plataformas digitales en ocho países de América Latina, integrando datos administrativos con una encuesta que desarrollamos junto con Uber, evaluando ingresos, vulnerabilidad laboral y brechas de protección social. Ese trabajo resultó en una publicación técnica donde participé como coautora.

El agente no inventa información. Cuando se le preguntaba algo que no está documentado en mi CV, el agente, en vez de inventar una respuesta genérica, dice abiertamente que no tiene esa información, porque el prompt lo obliga a ceñirse solo al contexto que le llega del retriever.Ahí es donde se nota si el diseño funciona.

Se puede reproducir la misma prueba con:

```bash
curl -X POST https://agente-cv-mariana.onrender.com/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Cuéntame de tu experiencia en el BID"}'
```

El servicio se mantiene despierto todo el tiempo gracias a un monitor externo (UptimeRobot) que le hace ping cada 5 minutos, así que no depende de a qué hora alguien decida probarlo.

## Estructura

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
Claude, con el contexto recuperado
      │
      ▼
Respuesta en el formato de Open Responses
```

`data/` tiene el conocimiento: tres archivos en markdown con mi experiencia, mi educación/habilidades y mis proyectos, escritos a partir de mi CV real. `app/rag.py` se encarga de buscar qué fragmentos son relevantes para cada pregunta. `app/llm.py` solo llama al modelo, sin saber nada de RAG ni de HTTP. Y `app/main.py` amarra todo: recibe la solicitud, junta RAG con el LLM, arma la respuesta en el formato que pide Open Responses.

## Decisiones técnicas del diseño

- **RAG vs. CV en el prompt:** En lugar de incluir todo el CV en el `system prompt`, opté por **RAG**. Esto facilita actualizar el contenido sin modificar código y reduce respuestas genéricas o información inventada.

- **TF-IDF vs. embeddings:** Aunque un RAG tradicional usaría embeddings + vector store (Chroma/FAISS), el corpus son solo **tres documentos**. Para este volumen, `TF-IDF + similitud coseno` con `scikit-learn` ofrece menor complejidad, sin dependencias externas y con tiempos de respuesta de milisegundos.

- **Chunking por estructura:** En lugar de dividir los documentos cada N caracteres, los separo por **encabezados**. Así cada chunk representa una unidad completa, como un puesto, proyecto o sección del CV, mejorando la calidad de la recuperación.

- **Arquitectura stateless:** El endpoint no mantiene sesiones ni estado en servidor. Esto permite escalar a múltiples instancias sin problemas de sincronización.

- **Proveedor de LLM desacoplado:** Aislé la integración con el modelo en `app/llm.py`. Durante el desarrollo cambié de proveedor dos veces sin modificar el resto de la arquitectura, demostrando la utilidad de mantener esta dependencia desacoplada.

- **Compatibilidad con A2A:** Expongo `/.well-known/agent-card.json` siguiendo el formato **A2A**, permitiendo que plataformas compatibles descubran automáticamente los metadatos y endpoint del agente.

- **API Key opcional:** La protección mediante API key está implementada pero desactivada para facilitar el registro en la plataforma del reto. En un entorno productivo se activaría para evitar uso no autorizado y consumo de créditos.

## Retos del agente y lecciones aprendidas

Operar un agente también implica resolver problemas que aparecen durante el desarrollo y, sobre todo, en producción.

- **Compatibilidad de Python:** La versión disponible no era compatible con FastAPI y Pydantic. Lo resolví instalando una versión nueva con `pyenv` y adaptando el código para mantener compatibilidad.

- **Render:** El plan gratuito duerme el servicio después de 15 minutos sin tráfico. Para este volumen de uso, opté por mantenerlo activo mediante un monitor externo en lugar de contratar un plan de pago.

- **Recuperación de información:** En producción, TF-IDF confundía términos similares como *"experiencia profesional"* y *"dominio profesional"*, recuperando información incorrecta. Lo solucioné incorporando **bigramas** al vectorizador.

- **Historial conversacional:**

El reto más importante fue el manejo del historial. Inicialmente enviaba la conversación completa al modelo, lo que provocaba que:

- recapitulase preguntas anteriores;
- se contradijera con respuestas previas;
- e incluso mencionara herramientas que el agente no utilizaba.

Probé reducir el historial y utilizar un modelo más grande, pero la solución más estable fue **procesar cada pregunta de forma independiente**.

Esto implica perder cierta capacidad para responder preguntas de seguimiento que dependan del contexto, pero para un agente de CV prioricé **consistencia y precisión sobre continuidad conversacional**, ya que la mayoría de las preguntas son autocontenidas.
