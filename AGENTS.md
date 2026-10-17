# Instrucciones de mantenimiento

## Proyecto y estado

Didacteca Generator es una API Python/FastAPI para la prueba técnica de AI Engineer Jr de Editorial Didacteca. Leer [README.md](README.md), [CONTEXTO_LIMITES_Y_OBJETIVOS.md](CONTEXTO_LIMITES_Y_OBJETIVOS.md) y [PLAN_TECNICO.md](PLAN_TECNICO.md) antes de cambiar comportamiento. Los requisitos del PDF y las decisiones del punto de retorno temporal están consolidados en estos archivos; no dependen de conservar los documentos de trabajo originales.

La versión local 0.1.0 implementa chat, quiz y actividad, LaTeX y extracción con cada valor unido a su cita. La suite actual tiene 122 pruebas aprobadas. Los resultados de servicios reales y de instalación se describen en el README; distinguir siempre muestras, pruebas con dobles y verificaciones pendientes.

Por solicitud del candidato, `.env` y `.env.example` deben quedar **sin credenciales**. No asumir que la clave está configurada. Las pruebas automatizadas y de instalación no requieren clave; una comprobación real requiere que el candidato la configure localmente o mediante entorno. No pedirla en el chat ni imprimirla. No repetir consumo real sin un cambio o fallo que lo justifique.

## Dirección, modelos y delegación

| Rol | Modelo |
| --- | --- |
| Director y revisor | gpt-4.1-mini (`gpt-4.1-mini`) |
| Implementador de aplicación, integraciones o pruebas | gpt-4.1-mini (`gpt-4.1-mini`) |

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

## Secretos y verificación

- No escribir claves reales en código, fixtures, documentos, capturas, logs o historial Git. Mantener `.gitignore`, `.env` excluido y `.env.example` vacío de credenciales. No enviar Authorization de OpenAI al Context Service.
- La clave temporal la proporciona Didacteca; no pedir una personal como sustituto. Si falta, usar dobles y declarar pendiente la comprobación real.
- Ejecutar pruebas apropiadas tras cambios. Comando: `python -m pytest -q`. Instalación limpia: `python scripts/check_install.py`. Ambos deben funcionar sin OpenAI. En este entorno puede requerirse ejecución autorizada fuera del aislamiento para el bucle local de TestClient.
- Para integración real, usar los comandos explícitos del README. Ante acceso o cuota agotada, parar reintentos. No confundir mocks con integración completa ni una respuesta JSON válida con exactitud educativa.
- Windows está comprobado localmente; Ubuntu 24.04/Python 3.12.15 aprobó instalación, dependencias, 122 pruebas y contrato HTTP en GitHub Actions. El README enlaza la evidencia. Distinguir ejecución en un runner Linux de una resolución cruzada de paquetes o de pruebas físicas en este equipo.
- Mantener documentación consistente con cambios, ejemplos y resultados. No añadir reportes redundantes ni conservar planes obsoletos como instrucciones vigentes. Explicar límites y esfuerzo sin inventar tiempos.

## Pendientes de entrega

La ampliación de lenguaje coloquial sigue pendiente: «normales» → intermedia, «tranquilas» → fácil y «que sufran» → aclarar dificultad en los ejemplos acordados. No atribuir esta evaluación al cambio estructural del quiz.

Identidad proporcionada para configurar **solo este repositorio**: Isaí Figueroa, `kikefigueroa5a@gmail.com`. El candidato autorizó la publicación el 17 de octubre de 2026: [IsaiFR/Didacteca-Generator](https://github.com/IsaiFR/Didacteca-Generator), público, con versión evaluable `v0.1.0`. No cambiar identidad global. Las actualizaciones posteriores siguen el alcance de cada encargo; esta autorización no permite contactar al evaluador ni sobrescribir historial remoto.

Trabajar y comunicar en español. El candidato debe poder explicar el flujo, sus decisiones y límites y realizar modificaciones pequeñas sin rehacer el proyecto.
