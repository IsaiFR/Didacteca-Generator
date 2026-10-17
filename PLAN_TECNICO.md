# Diseño técnico de Didacteca Generator

Este documento describe la versión 0.1.1, incluido el refuerzo de seguridad. Los requisitos están en [CONTEXTO_LIMITES_Y_OBJETIVOS.md](CONTEXTO_LIMITES_Y_OBJETIVOS.md); los comandos y resultados comprobados, en [README.md](README.md).

## Componentes y flujo

Python 3.12, FastAPI/Uvicorn, Pydantic 2, pydantic-settings, HTTPX, SDK oficial de OpenAI y pytest. Las versiones están fijadas en `requirements.txt`. La aplicación es asíncrona y no guarda conversación ni recursos en una base de datos.

Los módulos de `src/didacteca_ai/` tienen estas responsabilidades:

| Archivo | Responsabilidad |
| --- | --- |
| `main.py` | Ciclo de vida, endpoint y conversión HTTP de errores. |
| `config.py` | Entorno, `.env`, secretos y límites. |
| `schemas.py` | Contratos públicos y modelos internos. |
| `service.py` | Flujo, timeout total y presupuesto global de llamadas. |
| `context_client.py` | Consulta exacta de sección, contrato y errores externos. |
| `llm_client.py` | Responses API, extracción, normalización, errores y métricas. |
| `prompts.py` | Reglas y mensajes separados de extracción y generación. |
| `validation.py` | Límites, citas, aclaraciones, coherencia y proyección pública. |
| `source_reference.py` | Fragmentos deterministas del contenido, sin pérdida. |
| `math_format.py` | Comprobaciones limitadas de delimitadores y llaves LaTeX. |
| `rubric.py` | Validación y tabla Markdown de rúbricas. |
| `errors.py` | Códigos, detalles y mapeo HTTP. |
| `http_security.py` | Admisión HTTP, bytes, recepción, JSON no ambiguo, frecuencia y concurrencia por proceso. |
| `injection_guard.py` | Rechazo parcial de órdenes explícitas sobre una copia normalizada de la solicitud. |

Recorrido:

1. Aplicar admisión HTTP y límites de cuerpo/tiempo/JSON; validar los cuatro campos públicos, caracteres de identificadores y límites. Rechazar propiedades adicionales y órdenes explícitas incompatibles antes de OpenAI.
2. Extraer tarea y controles con el modelo, sin enviar el libro. Cada dato presente contiene valor y cita literal: `{"value": 2, "quote": "2 preguntas"}`. Un control ausente es `null`; `task` siempre tiene valor y cita.
3. Normalizar al modelo plano `ParsedInstructions` y sus enlaces de evidencia. Comprobar citas como subcadenas exactas, rangos, faltantes y problemas. Una aclaración detiene el flujo antes de consultar contexto.
4. Consultar la sección exacta. Validar identificadores, estructura, contenido vacío y tamaño; no truncar.
5. Generar con controles validados, sección completa, fragmentos y petición original en mensajes separados. La evidencia de extracción no es fuente temática de generación.
6. Validar el borrador y proyectarlo al éxito público, retirando controles y referencias internas.

Unir dato y cita elimina la posibilidad de un valor presente sin cita en una salida válida del esquema de transporte. No garantiza interpretación correcta ni apoyo semántico: se mantienen comprobación literal, aclaraciones y revisión educativa. Los clientes se inyectan en pruebas; importar la aplicación no abre conexiones. El arranque normal exige clave.

## Generación y evidencia

`source_reference.py` divide `content` en fragmentos de hasta 800 caracteres, conservando todos los caracteres originales. Se envían contenido completo y fragmentos numerados desde uno. No es RAG ni filtrado.

El modelo devuelve `source_id` existentes, no citas copiadas. Python verifica IDs, no demuestra que cada afirmación esté respaldada. Se usan borradores separados por acción con estados de éxito, aclaración, rechazo o insuficiencia. Solo un éxito válido se convierte al contrato público; nunca se presenta un recurso parcial como completo.

## Recuperación y presupuesto

Dos llamadas normales: extracción y generación. **Una reparación global y máximo tres llamadas** por ejecución. Si se repara extracción, generación ya no dispone de otra reparación. Los reintentos automáticos del SDK están desactivados; la configuración puede reducir estos topes, pero no ampliarlos.

La reparación solicita el objeto completo de la etapa con datos originales y comentarios saneados. No cambia la petición para conseguir éxito. Si vuelve a fallar, devuelve `MODEL_OUTPUT_INVALID`. No repara falta de datos, contradicciones, insuficiencia, rechazo de seguridad, autorización, cuota o transporte.

## Errores

La respuesta contiene `status` (`needs_clarification` o `error`), `action` reconocida o `null`, y `error` con `code`, `message` y `details`. Los cuatro arreglos de detalles siempre existen: `missing_fields`, `conflicting_fields`, `invalid_fields`, `constraints`. Los controles nombrados indican datos dentro de `instructions`.

| HTTP | Códigos principales |
| --- | --- |
| 400 | `INVALID_JSON`, `DUPLICATE_JSON_KEYS`. |
| 408 | `REQUEST_BODY_TIMEOUT`. |
| 413 | `REQUEST_BODY_TOO_LARGE`. |
| 415 | `UNSUPPORTED_MEDIA_TYPE`. |
| 429 | `REQUEST_RATE_LIMITED`. |
| 422 | `INVALID_REQUEST`, `UNSUPPORTED_ACTION`, `REQUEST_RULE_CONFLICT`, `CONTENT_EMPTY`, `CONTENT_INSUFFICIENT`, `CONTEXT_TOO_LARGE`, `AI_REFUSAL`. |
| 422, aclaración | `MISSING_INPUT_FIELDS`, `MISSING_PARAMETERS`, `AMBIGUOUS_INSTRUCTIONS`, `CONFLICTING_INSTRUCTIONS`, `INVALID_PARAMETERS`, `UNFEASIBLE_ACTIVITY`. |
| 404 | `BOOK_NOT_FOUND`, `SECTION_NOT_FOUND`. |
| 502 | `CONTEXT_INVALID_RESPONSE`, `CONTEXT_REQUEST_REJECTED`, `MODEL_OUTPUT_INVALID`, `AI_INVALID_RESPONSE`. |
| 503 | `CONTEXT_UNAVAILABLE`, `AI_UNAVAILABLE`, `AI_ACCESS_DENIED`, `AI_QUOTA_EXCEEDED`, `AI_RATE_LIMITED`, `AI_MODEL_UNAVAILABLE`, `EXECUTION_CAPACITY_REACHED`, `CLIENT_CAPACITY_REACHED`. |
| 504 | `CONTEXT_TIMEOUT`, `AI_TIMEOUT`, `EXECUTION_TIMEOUT`. |
| 500 | `INTERNAL_ERROR`. |

`ACTION_NOT_IMPLEMENTED`/501 se reserva para capacidades reconocidas pendientes; las tres están implementadas. Un 422 del Context Service se convierte en `CONTEXT_REQUEST_REJECTED`/502. No se exponen cuerpos de error externos ni stacktraces.

## Actividades y LaTeX

Se comprueban duración entera, suma de minutos de fases, modalidad explícita y tamaño del equipo. Los prompts exigen casos completos, roles y producto; diagnóstica y evaluativa grupales incluyen evidencia individual. Las comprobaciones no demuestran viabilidad pedagógica universal.

La evaluativa tiene criterios internos con máximos positivos que suman 10 y niveles completos de máximo a cero. `rubric.py` los convierte a tabla dentro de `expected_result`, con puntajes por asignar. No redistribuye pesos inválidos silenciosamente.

`math_format.py` revisa emparejamiento, fragmentos vacíos, anidamiento, balance de llaves y algunas marcas TeX sin delimitar. No compila TeX ni reconoce toda expresión en texto libre. El formateador de tablas protege las fórmulas en línea y escapa el texto normal sin destruir comandos.

## Configuración, pruebas y entrega

El refuerzo de seguridad limita cuerpos reales antes de Pydantic, rechaza JSON duplicado y acota admisión y lectura. Las cuotas son por proceso y no se basan en cabeceras del usuario. `--no-proxy-headers` conserva la IP del transporte; otros despliegues deben definir su frontera de confianza. El contexto se solicita sin compresión y se limita antes de cargar JSON para evitar buffers y descompresión sin cota.

No hay SQL ni shell en el flujo de usuario. Los datos educativos no se ejecutan; las palabras SQL pueden ser contenido legítimo. La detección por patrones de prompt injection es parcial y no sustituye separación de mensajes, ausencia de herramientas/secretos, validación de salidas y evaluación del modelo. El README detalla controles, nuevos errores, auditoría y límites de las pruebas locales.

`.env.example` enumera las variables. Context usa HTTPS configurable y OpenAI su base oficial fija. Los archivos `.env` y `.env.example` quedan con `OPENAI_API_KEY` vacía por solicitud del candidato; ejecutar contra proveedores requiere configurarla nuevamente o proporcionarla como variable de entorno.

Límites iniciales: instrucciones 6.000 caracteres, identificadores 128, preguntas 1–10, equipos 2–8, duración 1–120 minutos y contexto 60.000 caracteres. Timeout de contexto 10 s, IA 30 s por llamada y ejecución total 110 s; salida de extracción 2.000 tokens y generación 8.000. El README contiene los nombres definitivos.

Los registros operativos contienen identificador, acción, código, duración, llamadas y contadores de tokens, sin claves ni contenido educativo completo. Las métricas usan contexto asíncrono para separar solicitudes concurrentes.

`tests/` comprueba contratos, aclaraciones, proveedores, reparación, concurrencia, referencias, rúbrica y matemáticas con dobles. `scripts/smoke_live.py` verifica casos con ambos servicios; consume la credencial y guarda evidencia saneada. Los informes históricos no acreditan automáticamente cambios posteriores.

`scripts/check_install.py` crea una copia temporal y otro entorno virtual, instala requisitos, ejecuta `pip check`, pytest y un chequeo HTTP sin proveedores. La versión 0.1.1 aprobó 210 pruebas desde copia limpia en Windows. El workflow lo repite en Windows y Ubuntu 24.04 con Python 3.12, permisos de lectura y sin secretos ni despliegue; añade un trabajo independiente de auditoría de los 35 paquetes fijados. El README y Actions identifican la evidencia exacta por versión.

La publicación fue autorizada por el candidato el 17 de octubre de 2026 en [IsaiFR/Didacteca-Generator](https://github.com/IsaiFR/Didacteca-Generator), con visibilidad pública y tag de entrega `v0.1.0`. La identidad Git se configura solo para este repositorio. El envío del enlace al evaluador es una acción separada y no se realiza automáticamente.
