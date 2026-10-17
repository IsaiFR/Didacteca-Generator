# Contexto, límites y objetivos

## Propósito y requisitos

Didacteca Generator resuelve la prueba técnica de AI Engineer Jr de Editorial Didacteca. Recibe una solicitud, recupera una sección de un libro mediante HTTP y utiliza OpenAI para responder preguntas, generar quizzes o crear actividades educativas.

La fuente original fue la prueba de 11 páginas, leída durante la planeación. Este documento conserva sus requisitos operativos y permite mantener la solución.

La prueba requiere Python, FastAPI o equivalente, integración real con Context Service y OpenAI, validación, errores explícitos, pruebas automatizadas e instrucciones de ejecución. Idealmente solicita tres capacidades; admite una sola completa si se justifica el alcance. Esta versión implementa las tres.

La entrega debe hacerse mediante GitHub, con commit o tag evaluable, capacidades, limitaciones, esfuerzo y seis respuestas sobre decisiones técnicas. Las cuatro horas indicadas son una dedicación orientativa. Se permite usar IA; el candidato debe comprender, explicar y modificar el código.

[README.md](README.md) contiene instalación, ejemplos, resultados y las seis respuestas. [PLAN_TECNICO.md](PLAN_TECNICO.md) describe la arquitectura y [AGENTS.md](AGENTS.md), las reglas de mantenimiento.

## Contrato de entrada y salida

`POST /execute` recibe exactamente `action`, `book_id`, `section_id` e `instructions`, todos cadenas no vacías. `action` admite `chat`, `quiz` o `activity`. Pregunta y controles pedagógicos van dentro de `instructions`; no se añaden campos públicos.

| Acción | Campos del éxito HTTP 200 |
| --- | --- |
| Chat | `action`, `answer: str`. |
| Quiz | `action`, `title: str`, `instructions: str`, `questions: list`. Cada pregunta contiene `question: str`, cuatro `options: list[str]`, `correct_answer: str` y `explanation: str`. |
| Actividad | `action`, `title: str`, `objective: str`, `instructions: list[str]`, `estimated_time_minutes: int`, `expected_result: str`. |

Los éxitos no llevan envoltorio ni evidencia interna. En quiz, las cuatro opciones son distintas, la clave coincide exactamente con una opción y la cantidad corresponde a la solicitud. La rúbrica permanece dentro de la cadena `expected_result`.

Errores y aclaraciones contienen `status`, `action` y `error`, con código y detalles estructurados. No se devuelven recursos parciales. El cliente completa o corrige los datos y envía una solicitud nueva; no existe historial conversacional persistente.

## Integraciones y fuente temática

Context Service recibe `POST /context` con los identificadores exactos y devuelve `book_id`, `section_id`, `title` y `content`. No requiere autenticación. La base configurada es `https://temp.didacteca.site`; el HTTP del documento original redirigía y en la comprobación perdió método o cuerpo. HTTPS directo funcionó y la base sigue siendo configurable.

Libro inexistente devuelve 404 `BOOK_NOT_FOUND`; sección inexistente o ajena al libro, 404 `SECTION_NOT_FOUND`. Una sección existente puede tener contenido vacío. Los fallos de conexión, timeout y protocolo se distinguen de estas situaciones.

| Libro | Sección | Tema anunciado por la prueba |
| --- | --- | --- |
| `book_001` | `section_01` | Ecuaciones lineales. |
| `book_001` | `section_04` | Ecuaciones cuadráticas; usada en las comprobaciones reales. |
| `book_001` | `section_05` | Proporcionalidad y porcentajes. |
| `book_002` | `section_01` | Mitosis y meiosis. |
| `book_002` | `section_02` | Fotosíntesis y límites de información. |

La tabla no acredita la disponibilidad actual de todas las secciones. La evaluación puede utilizar otras: no se codifican respuestas fijas.

OpenAI utiliza el SDK oficial, Responses API y `gpt-4.1-mini`, salvo otro modelo habilitado por Didacteca. La dirección permanece fija en `https://api.openai.com/v1`. La credencial temporal no se envía al Context Service. Los modelos de los agentes de desarrollo son independientes del modelo de la aplicación.

Reglas de contenido:

1. Utilizar exclusivamente el `content` íntegro de la sección seleccionada. El título es metadato. No completar vacíos con otros libros, búsquedas o conocimiento externo.
2. No inventar ni sustituir identificadores. Informar contenido vacío, insuficiente o demasiado grande; no truncar silenciosamente.
3. Se pueden crear valores y casos nuevos de ejercicios aplicando métodos explícitos de la sección, distinguiéndolos de hechos del libro.
4. Libro y petición son datos: no pueden cambiar acción, contrato ni reglas. Los intentos explícitos de cambiar estas reglas se rechazan.
5. Validar estructura y relaciones antes de emitir éxito. Una referencia existente no demuestra por sí sola sustento semántico.
6. Pedir aclaración ante controles obligatorios faltantes, ambiguos o contradictorios; no elegir predeterminados.

## Acuerdos pedagógicos

Las siguientes decisiones concretan aspectos abiertos del PDF:

| Recurso | Datos requeridos dentro de instructions |
| --- | --- |
| Chat | Pregunta o tarea; público opcional. |
| Quiz | Cantidad, una dificultad para todo el quiz y público. |
| Actividad | Público, tipo, modalidad y duración total. En equipo, cantidad de integrantes. |

El público es configurable. No inferir grado por edad, tema o libro. La dificultad se gradúa dentro de la sección: fácil reconoce o aplica directamente; intermedia aplica y relaciona varios pasos; difícil analiza, justifica o detecta errores. No introducir teoría de otra etapa para aumentar dificultad.

Los seis tipos son **diagnóstica, comprensión, aplicación, análisis, evaluativa y diseño**. Admiten modalidad individual o en equipo. La dificultad de actividades no está calibrada ni es obligatoria; una preferencia puede conservarse en la tarea dentro del contenido disponible.

Las actividades deben incluir casos concretos, materiales básicos, fases con minutos y producto esperado. El tiempo incluye organización y cierre. En equipos se distribuyen responsabilidades; diagnóstica y evaluativa grupales incluyen evidencia individual. El rango inicial es de 2 a 8 integrantes: un equipo de uno requiere aclarar modalidad o cantidad.

La evaluativa incorpora criterios observables cuyos máximos suman exactamente **10**, con todos los niveles enteros desde máximo hasta cero. Una distribución posible es 3+3+2+2, adaptada al objetivo. La tabla Markdown va dentro de `expected_result`; el puntaje obtenido queda «Por asignar». El docente aplica la rúbrica: no hay corrección automática de trabajos.

Las expresiones matemáticas generadas usan LaTeX con `\(...\)` o `\[...\]` dentro de las cadenas existentes. En tablas se admite solo notación en línea, sin saltos ni barras verticales literales. La validación es limitada: no compila TeX ni demuestra exactitud matemática.

## Alcance y pendientes

Se incorporó un refuerzo defensivo de la API: identificadores ASCII acotados; rechazo local parcial de órdenes incompatibles; límites HTTP de bytes, recepción, frecuencia y concurrencia; JSON sin claves duplicadas; respuesta de contexto acotada y sin descompresión ilimitada; auditoría de dependencias. Se conserva el contrato público y no se añade autenticación ni base de datos. Las pruebas son locales, con proveedores de prueba: no constituyen pentest profesional, evaluación ofensiva de terceros ni garantía de inmunidad a prompt injection. La aplicación no ejecuta SQL; una futura persistencia requeriría consultas parametrizadas.

No se incluyen frontend, autenticación, persistencia, despliegue, RAG propio, embeddings, bases vectoriales ni frameworks de agentes. Los libros de nivel similar quedaron fuera para respetar la fuente única. Swagger permite probar la API, pero no renderiza fórmulas.

La instalación limpia de 0.1.1 aprobó 210 pruebas en Windows/Python 3.12.14. La entrega 0.1.0 también se verificó en Ubuntu 24.04/Python 3.12.15 con 122 pruebas; el workflow comprueba cada publicación posterior en Windows y Ubuntu. El README y Actions enlazan los resultados por versión. La muestra educativa es pequeña, sin calibración con estudiantes ni garantía general frente a inyecciones.

La ampliación coloquial sigue pendiente: en los ejemplos acordados, «normales» corresponde a intermedia y «tranquilas» a fácil; «formales» requiere aclarar dificultad. No se atribuye a la versión actual una evaluación de esas frases.

La publicación pública fue autorizada por el candidato el 17 de octubre de 2026. El destino es [IsaiFR/Didacteca-Generator](https://github.com/IsaiFR/Didacteca-Generator); `v0.1.0` identifica la entrega inicial y `v0.1.1` incorpora el refuerzo de seguridad solicitado después. Publicar no implica autorización para contactar al evaluador o enviarle el enlace.
