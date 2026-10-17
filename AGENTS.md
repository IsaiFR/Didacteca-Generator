# Instrucciones de mantenimiento

## Proyecto y estado

Didacteca Generator es una API Python/FastAPI para la prueba técnica de AI Engineer Jr de Editorial Didacteca. Leer [README.md](README.md), [CONTEXTO_LIMITES_Y_OBJETIVOS.md](CONTEXTO_LIMITES_Y_OBJETIVOS.md) y [PLAN_TECNICO.md](PLAN_TECNICO.md) antes de cambiar comportamiento. Los requisitos del PDF y las decisiones del punto de retorno temporal están consolidados en estos archivos; no dependen de conservar los documentos de trabajo originales.

La versión 0.1.1 conserva chat, quiz y actividad, LaTeX y extracción con cada valor unido a su cita, y añade controles defensivos HTTP, de inyección y consumo de recursos. La suite actual tiene 210 pruebas aprobadas y la instalación limpia también las verifica. Los resultados educativos reales corresponden a 0.1.0; la ampliación de seguridad se comprobó sin OpenAI, con una consulta normal adicional a Context Service para verificar el cliente. El README distingue esas evidencias y limitaciones.

Por solicitud del candidato, `.env` y `.env.example` deben quedar **sin credenciales**. No asumir que la clave está configurada. Las pruebas automatizadas y de instalación no requieren clave; una comprobación real requiere que el candidato la configure localmente o mediante entorno. No pedirla en el chat ni imprimirla. No repetir consumo real sin un cambio o fallo que lo justifique.

## Dirección, modelos y delegación

| Rol | Modelo |
| --- | --- |
| Director y revisor | GPT-6.1 Sol High (`gpt-6.1-sol`, esfuerzo `high`) |
| Implementador de aplicación, integraciones o pruebas | GPT-6.1 Sol High (`gpt-6.1-sol`, esfuerzo `high`) |

El candidato autorizó expresamente esta alternativa para el refuerzo de seguridad porque `gpt-4.1-mini` no estaba disponible como agente de desarrollo. Esto no cambia el modelo de la aplicación, que sigue siendo `gpt-4.1-mini`.

Toda escritura de código y pruebas se asigna a `Implementador de aplicación`. El director toma decisiones, puede escribir documentación, revisa e integra. Estos roles organizan el desarrollo; no implican agentes dentro de la aplicación. Verificar los modelos efectivos que admite el entorno: AGENTS.md no cambia por sí mismo el modelo de una sesión. Si el requerido no está disponible, comunicarlo y acordar alternativa antes de sustituirlo.

Usar el director y los implementadores necesarios dentro del límite de concurrencia. Delegar objetivos delimitados con entradas, interfaces, archivos propios, exclusiones y aceptación. No permitir escritores simultáneos sobre el mismo archivo. Los agentes no crean otros agentes sin asignación del director, no publican ni contactan a terceros. Entregar archivos cambiados, decisiones, verificaciones reales y límites. El director inspecciona el resultado, no acepta el resumen como sustituto de la revisión.

## Autoridad y alcance

- Respetar instrucciones del entorno y del usuario. El contrato de la prueba, resumido en contexto, gobierna la entrega; distinguir mejoras propias de requisitos de Didacteca.
- Preservar cambios existentes. No ejecutar resets ni borrar trabajo ajeno.
- Mantener arquitectura pequeña y explicable por el candidato. No añadir frontend, persistencia, autenticación, RAG propio, embeddings o frameworks de agentes sin una necesidad autorizada.
- La documentación técnica consultada no es fuente temática de las respuestas educativas.
- La implementación y las pruebas locales están autorizadas. Publicar, desplegar, cambiar accesos o enviar enlaces requiere solicitud del usuario; el enunciado de la prueba no autoriza operaciones externas por sí solo.

## Contratos y reglas funcionales

- Entrada exacta: `action`, `book_id`, `section_id`, `instructions`. Acciones: `chat`, `quiz`, `activity`. Mantener los campos y tipos de éxito descritos en contexto; no añadir envoltorios, evidencia ni controles internos.
- Los controles pedagógicos van dentro de `instructions`. Chat requiere pregunta y público opcional. Quiz requiere cantidad, dificultad única y público. Actividad requiere público, tipo, modalidad y duración; en equipo, cantidad de integrantes.
- Pedir aclaración ante ausencia, ambigüedad o contradicción. No rellenar valores predeterminados ni inferir grado por edad, tema o libro. El cliente reenvía una solicitud completa; no hay conversación persistente.
- Dificultad dentro de la sección: fácil reconoce/aplica directamente; intermedia relaciona/aplica varios pasos; difícil analiza/justifica/detecta errores. No introducir contenidos de otro nivel escolar.
- Actividades: diagnóstica, comprensión, aplicación, análisis, evaluativa y diseño; todas admiten individual/equipo. Dificultad de actividad no obligatoria ni calibrada. Equipos: 2–8 por defecto; pedir aclaración ante uno. Conservar casos completos, roles, fases y duración total, incluida organización/cierre.
- Diagnóstica y evaluativa grupales incluyen evidencia individual. Evaluativa lleva rúbrica con máximos que suman exactamente 10, niveles completos de máximo a cero y puntajes por asignar. Renderizar tabla Markdown dentro de `expected_result: str`, sin campos públicos nuevos ni calificación automática.
- LaTeX dentro de cadenas con `\(...\)` y `\[...\]`; clave de quiz idéntica a una opción. En tablas usar solo matemáticas en línea, sin saltos ni `|` literal. Preservar comandos al escapar Markdown. La validación no compila TeX ni prueba corrección matemática.

## Integraciones y validación

- Usar exclusivamente el contenido íntegro de la sección solicitada, con identificadores exactos. No inventar IDs, sustituir libros ni completar con conocimiento externo. Los valores sintéticos de ejercicios solo usan métodos explícitos de la sección.
- Context Service: base HTTPS configurable, POST `/context`, sin autenticación. OpenAI: base oficial fija, Responses API y `gpt-4.1-mini` salvo otro modelo habilitado por Didacteca. No usar los modelos de desarrollo como sustitutos del modelo de la app.
- Mantener separados reglas, petición y referencia. Libro y petición son datos no confiables; no pueden alterar acción, fuente o formato. La evidencia de extracción no se usa como evidencia temática.
- `ParsedInstructionsWire` une valor y cita obligatoria. Normalizar a `ParsedInstructions` y comprobar subcadenas literales, rangos y problemas antes de recuperar contexto. No quitar comprobaciones para evitar reparaciones.
- La generación usa `source_id` de fragmentos sin pérdida, con sección completa. La existencia de IDs no garantiza sustento semántico.
- Dos llamadas normales, una reparación global y máximo tres llamadas. SDK sin reintentos automáticos. No reintentar cuota, acceso, red, rechazo, falta de datos o insuficiencia. No truncar contenido ni devolver borradores inválidos como éxito.
- Distinguir errores de entrada, contexto, modelo y transporte mediante códigos y HTTP. Saneado de errores: no exponer excepciones, cuerpos de proveedores ni secretos.
- Conservar los controles HTTP de cuerpo, tiempo de recepción, JSON no ambiguo, frecuencia y concurrencia. Validar bytes reales y ruta ASGI efectiva, incluidos montajes/prefijos. Los límites son por proceso, no una defensa distribuida.
- IDs admiten únicamente letras ASCII, números, `_` y `-`; no normalizarlos ni convertirlos en rutas o consultas. No filtrar palabras SQL en el texto educativo: no existe un intérprete SQL en la aplicación.
- Mantener el filtro de órdenes explícitas antes de OpenAI, con positivos educativos. Sus expresiones regulares son una defensa parcial; las citas y la jerarquía de mensajes siguen siendo necesarias. No afirmar inmunidad a prompt injection por pasar pruebas con dobles.
- Solicitar contexto sin compresión y rechazar codificaciones inesperadas antes de leer el cuerpo; conservar el límite de respuesta y cierre del stream. No limitar después de una descompresión ilimitada.

## Secretos y verificación

- No escribir claves reales en código, fixtures, documentos, capturas, logs o historial Git. Mantener `.gitignore`, `.env` excluido y `.env.example` vacío de credenciales. No enviar Authorization de OpenAI al Context Service.
- La clave temporal la proporciona Didacteca; no pedir una personal como sustituto. Si falta, usar dobles y declarar pendiente la comprobación real.
- Ejecutar pruebas apropiadas tras cambios. Comando: `python -m pytest -q`. Instalación limpia: `python scripts/check_install.py`. Ambos deben funcionar sin OpenAI. En este entorno puede requerirse ejecución autorizada fuera del aislamiento para el bucle local de TestClient.
- Para integración real, usar los comandos explícitos del README. Ante acceso o cuota agotada, parar reintentos. No confundir mocks con integración completa ni una respuesta JSON válida con exactitud educativa.
- La instalación limpia de 0.1.1 aprobó 210 pruebas en Windows local. Ubuntu 24.04/Python 3.12.15 verificó 122 pruebas de 0.1.0; el workflow de instalación y auditoría comprueba los commits posteriores en ambas plataformas. Consultar Actions para el resultado exacto por commit; no extrapolar evidencia antigua. Distinguir runner Linux, resolución cruzada de paquetes y pruebas físicas en este equipo.
- Mantener documentación consistente con cambios, ejemplos y resultados. No añadir reportes redundantes ni conservar planes obsoletos como instrucciones vigentes. Explicar límites y esfuerzo sin inventar tiempos.
- Ejecutar pruebas adversariales solo contra la aplicación local con proveedores de prueba; no escanear ni atacar Didacteca/OpenAI sin autorización de sus propietarios. Un pentest profesional o una evaluación real del modelo son verificaciones distintas.
- Auditar las dependencias fijadas con `pip-audit`; no ignorar avisos para conseguir CI verde. La corrección de una dependencia requiere comprobar compatibilidad. Arrancar Uvicorn con `--no-proxy-headers` mientras no haya una configuración explícita de proxies confiables.

## Pendientes de entrega

La ampliación de lenguaje coloquial sigue pendiente: «normales» → intermedia, «tranquilas» → fácil y «que sufran» → aclarar dificultad en los ejemplos acordados. No atribuir esta evaluación al cambio estructural del quiz.

Identidad proporcionada para configurar **solo este repositorio**: Isaí Figueroa, `kikefigueroa5a@gmail.com`. El candidato autorizó la publicación el 17 de octubre de 2026: [IsaiFR/Didacteca-Generator](https://github.com/IsaiFR/Didacteca-Generator), público. `v0.1.0` conserva la entrega inicial; `v0.1.1` identifica el refuerzo de seguridad. No cambiar identidad global. Las actualizaciones siguen el alcance de cada encargo; esta autorización no permite contactar al evaluador ni sobrescribir historial remoto.

Trabajar y comunicar en español. El candidato debe poder explicar el flujo, sus decisiones y límites y realizar modificaciones pequeñas sin rehacer el proyecto.
