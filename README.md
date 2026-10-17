# Didacteca Generator

API en Python/FastAPI para responder preguntas, generar quizzes y preparar actividades utilizando exclusivamente una sección del Context Service de Didacteca. La versión local **0.1.0** implementa las tres capacidades, formato matemático LaTeX y extracción de controles con citas obligatorias unidas a sus valores.

Pasan **122 pruebas automatizadas**. La instalación desde copia limpia está comprobada en Windows/Python 3.12.14 y en Ubuntu 24.04/Python 3.12.15 mediante GitHub Actions. La evidencia con servicios reales y sus límites se detalla abajo. Repositorio público: [IsaiFR/Didacteca-Generator](https://github.com/IsaiFR/Didacteca-Generator). Versión de entrega: `v0.1.0`.

## Instalación

Requiere **Python 3.12**. Desde la raíz del proyecto:

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
```

Si no se permite activar el entorno, invocar directamente `.\.venv\Scripts\python.exe` en los comandos siguientes, sin cambiar la política del sistema.

Linux/Bash, con Python 3.12 y su módulo `venv` instalados:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
```

Si falta `venv` o `ensurepip`, instalar el paquete de entornos virtuales correspondiente a Python 3.12 mediante el gestor de la distribución. Las 35 dependencias están fijadas en `requirements.txt`. No se requieren ejecutables ni rutas de Windows en la aplicación.

### Comprobar desde una copia limpia

```text
python scripts/check_install.py
```

El script copia código, pruebas, requisitos, `pytest.ini` y `.env.example` a una carpeta temporal propia. No copia `.env` ni reutiliza `.venv`. Crea otro entorno, instala dependencias, ejecuta `pip check`, pytest y un chequeo de OpenAPI/rechazo de solicitud incompleta con un servicio de prueba. Requiere acceso al índice de paquetes, pero no llama a Context Service ni OpenAI. Limpia su carpeta temporal y guarda `output/install-check-<sistema>.json`; `--report` permite otra ruta.

Resultado comprobado en Windows/Python 3.12.14: instalación correcta, dependencias sin incompatibilidades, **122 pruebas aprobadas en 3,09 s** y contrato HTTP aprobado. [Informe de instalación](output/install-check-windows.json).

[El workflow de pruebas](.github/workflows/tests.yml) ejecuta lo mismo en Windows y Ubuntu 24.04 con Python 3.12 en push, pull request o ejecución manual; no necesita secretos ni despliega. La [comprobación real en Ubuntu](https://github.com/IsaiFR/Didacteca-Generator/actions/runs/39063231559/job/117485376389) aprobó la instalación limpia, `pip check`, **122 pruebas en 1,63 s** y el contrato HTTP con Python 3.12.15, sobre el código del tag `v0.1.0`. El equipo local no tiene Linux: la ejecución se hizo en el runner de GitHub, no se deduce de una resolución cruzada de paquetes. Las acciones utilizadas están documentadas en [checkout](https://github.com/actions/checkout) y [setup-python](https://github.com/actions/setup-python).

## Configuración y arranque

**El repositorio excluye `.env` y entrega `.env.example` sin claves.** Para usar los proveedores, configurar localmente `OPENAI_API_KEY` con la credencial entregada por Didacteca o proporcionarla mediante una variable de entorno. No pegarla en el chat, escribirla en código ni incluir `.env` en Git. Las pruebas automatizadas no requieren credencial. Sin configurarla, el arranque normal de la API no queda habilitado.

| Variable | Valor inicial |
| --- | --- |
| `PROVIDED_SERVICE_BASE_URL` | `https://temp.didacteca.site` |
| `OPENAI_API_KEY` | Vacía; requerida para la ejecución real. |
| `OPENAI_MODEL` | `gpt-4.1-mini` |
| `MAX_INSTRUCTIONS_CHARS` | 6000 |
| `MAX_IDENTIFIER_CHARS` | 128 |
| `MAX_QUIZ_QUESTIONS` | 10; mínimo 1. |
| `MAX_TEAM_SIZE` | 8; mínimo 2 en equipo. |
| `MAX_ACTIVITY_MINUTES` | 120; mínimo 1 minuto entero. |
| `MAX_CONTEXT_CHARS` | 60000; sin truncamiento. |
| `CONTEXT_TIMEOUT_SECONDS` | 10 |
| `AI_TIMEOUT_SECONDS` | 30 por llamada. |
| `EXECUTION_TIMEOUT_SECONDS` | 110 para toda la ejecución. |
| `EXTRACTION_MAX_OUTPUT_TOKENS` | 2000 |
| `GENERATION_MAX_OUTPUT_TOKENS` | 8000 |
| `MAX_REPAIRS_PER_EXECUTION` | 1, tope global. |
| `MAX_MODEL_CALLS_PER_EXECUTION` | 3, tope global. |

Son límites operativos elegidos para esta prueba. No son equivalencias pedagógicas ni límites oficiales del modelo. Superarlos produce un resultado explícito, sin reducir cantidades o cambiar la petición silenciosamente.

La prueba original indica Context Service por HTTP. En la comprobación esa dirección redirigió perdiendo método o cuerpo; HTTPS directo funcionó y permanece configurable. No se envía la clave de OpenAI a ese servicio. OpenAI usa su base oficial fija `https://api.openai.com/v1`; un `OPENAI_BASE_URL` heredado no redirige esta integración.

Después de configurar la credencial:

```text
python -m uvicorn didacteca_ai.main:app --app-dir src --host 127.0.0.1 --port 8000
```

Probar en [Swagger local](http://127.0.0.1:8000/docs). No se requiere frontend. Se puede añadir `--reload` para desarrollo.

## Solicitudes

`POST /execute` recibe exactamente **cuatro campos**: `action`, `book_id`, `section_id` e `instructions`, todos cadenas no vacías. Los controles pedagógicos se expresan dentro de `instructions`; no existen propiedades públicas adicionales para cantidad, dificultad o modalidad.

Chat requiere pregunta y público opcional:

```json
{
  "action": "chat",
  "book_id": "book_001",
  "section_id": "section_04",
  "instructions": "¿Qué indica el discriminante sobre las soluciones reales de una ecuación cuadrática?"
}
```

Quiz requiere cantidad, dificultad única y público:

```json
{
  "action": "quiz",
  "book_id": "book_001",
  "section_id": "section_04",
  "instructions": "Genera exactamente 2 preguntas de dificultad intermedia sobre el discriminante para estudiantes de segundo año de bachillerato."
}
```

La dificultad se gradúa dentro de la sección: fácil reconoce/aplica directamente; intermedia aplica y relaciona varios pasos; difícil analiza, justifica o detecta errores. No se añade teoría de otra etapa escolar. Las cuatro opciones son distintas y `correct_answer` coincide exactamente con una de ellas.

Actividad requiere público, tipo, modalidad y duración; en equipo, cantidad de integrantes:

```json
{
  "action": "activity",
  "book_id": "book_001",
  "section_id": "section_04",
  "instructions": "Crea una actividad evaluativa en equipos de 3 integrantes, de 20 minutos, sobre el discriminante para estudiantes de segundo año de bachillerato."
}
```

Tipos: diagnóstica, comprensión, aplicación, análisis, evaluativa y diseño. Todos admiten modalidad individual o en equipo. La dificultad de actividad no se exige ni está calibrada. La evaluativa incluye una tabla de rúbrica cuyos máximos suman 10 dentro de `expected_result`; el docente asigna los puntajes. No hay corrección automática.

Si falta un dato obligatorio, se solicita aclaración sin inventarlo. Ejemplo: una actividad en equipo sin cantidad de integrantes devuelve `missing_fields: ["team_size"]`. El cliente envía después una solicitud completa nueva; no se conserva historial conversacional.

Bash:

```bash
curl -X POST http://127.0.0.1:8000/execute \
  -H 'Content-Type: application/json' \
  -d '{"action":"chat","book_id":"book_001","section_id":"section_04","instructions":"¿Qué es el discriminante?"}'
```

PowerShell:

```powershell
$requestBody = '{"action":"chat","book_id":"book_001","section_id":"section_04","instructions":"¿Qué es el discriminante?"}'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/execute' -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($requestBody))
```

### Matemáticas en LaTeX

Las fórmulas se conservan dentro de las cadenas públicas con `\(...\)` en línea y `\[...\]` en bloque. Ejemplo serializado:

```json
{"answer":"La fórmula es \\(x = \\frac{-b \\pm \\sqrt{b^{2}-4ac}}{2a}\\)."}
```

Las barras dobles son escapes JSON; la cadena analizada contiene una barra por comando. El frontend debe reconocer y renderizar los delimitadores. Swagger muestra las cadenas. Al combinar Markdown y matemáticas se deben proteger las fórmulas de los escapes de Markdown.

En tablas se usa solo notación en línea sin saltos ni `|` literal; utilizar `\mid`, `\vert` o `\lvert...\rvert`. La clave del quiz conserva exactamente el texto y LaTeX de la opción. La validación revisa delimitadores, anidamiento, fragmentos vacíos, llaves y algunas marcas TeX evidentes sin delimitar. No compila TeX ni verifica exactitud matemática; tampoco reconoce todas las fórmulas escritas como texto libre.

## Respuestas y errores

Los éxitos HTTP 200 conservan los campos del ejercicio, sin envoltorio ni evidencia interna:

| Acción | Campos |
| --- | --- |
| Chat | `action`, `answer`. |
| Quiz | `action`, `title`, `instructions`, `questions`; cada pregunta: `question`, `options`, `correct_answer`, `explanation`. |
| Actividad | `action`, `title`, `objective`, `instructions` (lista), `estimated_time_minutes` (entero), `expected_result` (cadena). |

Ejemplo de aclaración:

```json
{
  "status": "needs_clarification",
  "action": "activity",
  "error": {
    "code": "MISSING_PARAMETERS",
    "message": "Completa los controles pedagógicos que faltan en instructions.",
    "details": {
      "missing_fields": ["team_size"],
      "conflicting_fields": [],
      "invalid_fields": [],
      "constraints": ["Completa los controles pedagógicos requeridos para la acción seleccionada."]
    }
  }
}
```

Los nombres de controles en `details` indican datos dentro de `instructions`, no propiedades nuevas. `action` es `null` cuando no se reconoce una acción válida. El cliente decide por `status`, `code` y listas estructuradas, sin interpretar el mensaje literal.

| HTTP | Uso |
| --- | --- |
| 422 | Entrada inválida, aclaración, conflicto de reglas, contenido vacío/insuficiente/excesivo o rechazo del modelo; distinguir por código. |
| 404 | `BOOK_NOT_FOUND`, `SECTION_NOT_FOUND`. |
| 502 | Respuesta externa incompatible o salida del modelo inválida tras la recuperación disponible. |
| 503 | Proveedor no disponible, acceso/modelo no habilitado, cuota o frecuencia limitada. |
| 504 | Timeout de contexto, IA o ejecución total. |
| 500 | Fallo interno inesperado con respuesta saneada. |

No se devuelven recursos parciales ni se completa contenido insuficiente con conocimiento externo. Los mensajes HTTP no exponen stacktraces, claves ni cuerpos de errores de proveedores. El mapeo detallado está en [PLAN_TECNICO.md](PLAN_TECNICO.md).

## Arquitectura y decisiones

El flujo valida la entrada, extrae controles, recupera la sección, genera, valida y proyecta la salida pública. Usa clientes asíncronos concretos sustituibles por dobles. No incluye buscador, base vectorial, persistencia ni framework de agentes.

La extracción ahora recibe cada dato junto a una cita obligatoria, por ejemplo `"question_count": {"value": 2, "quote": "2 preguntas"}`. `ParsedInstructionsWire` se normaliza al contrato interno existente y se comprueba que las citas aparezcan literalmente en la solicitud. Esto corrige la omisión estructural de evidencia que provocaba fallos del quiz; no garantiza interpretación semántica correcta.

Para generar se envía la sección completa y fragmentos numerados sin pérdida, de hasta 800 caracteres. El modelo devuelve `source_id` existentes. La evidencia del usuario no se reenvía como fuente temática. La existencia de un ID no demuestra que cada afirmación esté sustentada.

Se hacen dos llamadas normales al modelo y como máximo una reparación global, con tope de tres llamadas. Si se repara extracción, no queda otra reparación para generación. El SDK no hace reintentos automáticos. No se reparan cuota, acceso, transporte, faltantes ni insuficiencia. Structured Outputs asegura estructura, pero las respuestas aún pueden contener errores: [documentación oficial](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

### ¿Cómo dividimos el problema?

Contratos y errores definen la interfaz; configuración reúne límites; clientes aíslan proveedores; el servicio controla ejecución; validaciones y rúbrica revisan y proyectan el resultado. Las funciones compartidas permiten las tres capacidades sin duplicar integraciones.

### ¿Por qué esta arquitectura?

Permite probar fallos sin red y separar interpretación de generación. Python conserva decisiones verificables como cantidades, opciones, referencias y puntajes. La separación es pequeña pero permite explicar y modificar el código.

### ¿Qué situaciones consideramos problemáticas?

Datos faltantes o incompatibles, identificadores inexistentes, contenido vacío/insuficiente, instrucciones incrustadas, errores externos y borradores con esquema o relaciones inválidas. Todos reciben tratamiento explícito; ninguno se convierte en éxito ficticio.

### ¿Qué limitaciones tiene la solución?

Interpretación y generación probabilísticas; validar JSON o IDs no demuestra exactitud educativa ni dificultad calibrada. El tiempo de actividad es una estimación. La disponibilidad y permisos de proveedores son dependencias externas. No hay frontend ni corrección de trabajos, y la evaluación educativa real es una muestra pequeña. La muestra de actividad también incluyó menciones de `source_id` dentro de los pasos: los campos internos se retiran del esquema público, pero el texto generado todavía requiere revisión editorial.

### ¿Qué mejoraríamos con más tiempo?

Ampliar evaluaciones con docentes, calibrar dificultad y rúbricas con respuestas reales y medir latencia y consumo. La ampliación coloquial acordada sigue pendiente: «normales» → intermedia, «tranquilas» → fácil y «formales» → pedir dificultad. Se requiere interpretación contextual y pruebas de negaciones/conflictos; no sustituciones ciegas. «Ejercicios» bajo `action=quiz` conserva cuatro opciones y no habilita un formato abierto. Otro corpus o RAG sería un alcance diferente.

### ¿Cómo evaluaríamos el funcionamiento?

Pruebas de contratos, aclaraciones, fallos y recuperación con dobles; comprobaciones reales con ambos servicios; revisión manual de exactitud, sustento, distractores, instrucciones, tiempo y rúbrica. Las comprobaciones estructurales no sustituyen evaluación semántica ni demuestran resistencia general a inyecciones.

## Pruebas y evidencia

```text
python -m pytest -q
```

La suite actual aprobó **122 pruebas en 2,58 s**, con Python 3.12.14. Cubre contratos, tres capacidades, seis tipos de actividad, aclaraciones, límites, proveedores, reparación acotada, concurrencia, referencias, rúbrica y LaTeX. Las regresiones de extracción comprueban valor/cita obligatorios, ausencia como `null`, tipos estrictos, normalización, rechazo de citas inventadas y compatibilidad del esquema con el SDK.

La instalación limpia repitió las 122 pruebas en 3,09 s. Se conserva una advertencia conocida de Starlette/TestClient sobre `httpx`; no produjo fallos. En el entorno aislado de desarrollo se requirió permitir el bucle local de TestClient; pytest no usa proveedores reales.

La comprobación siguiente es **opcional y consume la credencial temporal**. Se ejecuta separadamente de pytest, con ambos clientes reales y sin imprimir claves:

```text
python scripts/smoke_live.py --check-latex --include-edge-cases --output output/smoke-current.json --resources-output output/current-examples.json
```

Tras el cambio de extracción, la corrida completa aprobó **5/6 casos**: chat y quiz devolvieron 200; solicitud sin libro, información ausente e intento de cambiar reglas recibieron los rechazos esperados. La actividad devolvió 502 `MODEL_OUTPUT_INVALID`. [Informe completo](output/smoke-current.json) y [respuestas exitosas](output/current-examples.json). El quiz produjo dos preguntas intermedias, opciones y claves coincidentes, con LaTeX validado; sus discriminantes 12 y 0 se revisaron manualmente. La corrida no acredita ausencia de fallos del modelo.

Para diagnosticar solo un caso fallido sin repetir los demás:

```text
python scripts/smoke_live.py --diagnostics --check-latex --case actividad_evaluativa_equipo_de_tres --output output/activity-check.json --resources-output output/activity-example.json
```

El diagnóstico registra únicamente los casos fijos de quiz/actividad y comentarios de validación saneados. No imprime la clave ni cabeceras. No repetir ejecuciones para conseguir una corrida sin fallos; conservar la evidencia y declarar límites.

La comprobación posterior de la actividad aprobó: 200 en 17,73 s, equipos de tres, fases de 5+10+5 minutos y rúbrica de 3+3+2+2. La extracción produjo todos sus controles y citas correctamente. Se usó una reparación de generación por TeX fuera de delimitadores, con tres llamadas totales. [Informe del caso](output/activity-check.json) y [actividad resultante](output/activity-example.json). La corrida completa conserva el 5/6 original; no se sustituye por este resultado posterior. No se afirma que se identificó la causa exacta del primer fallo porque esa corrida no registraba diagnóstico detallado.

## Entrega

Los documentos finales son este README, [contexto y límites](CONTEXTO_LIMITES_Y_OBJETIVOS.md), [diseño técnico](PLAN_TECNICO.md) e [instrucciones de agentes](AGENTS.md). El PDF original y el punto de retorno temporal se retiraron después de consolidar sus requisitos y decisiones. Los informes actuales y ejemplos útiles permanecen en `output/`; los artefactos reemplazados se retiraron.

Esfuerzo aproximado de la implementación inicial y LaTeX: **una hora y media**, sin contar la pausa por tokens. Planeación, preparación de instalación/CI y corrección final de extracción no se cronometraron. La cifra es una estimación de sesión, no un registro de horas; las cuatro horas del ejercicio son orientativas.

Repositorio público: [IsaiFR/Didacteca-Generator](https://github.com/IsaiFR/Didacteca-Generator). La entrega evaluable está identificada mediante el tag [v0.1.0](https://github.com/IsaiFR/Didacteca-Generator/tree/v0.1.0). Para reproducirla, clonar el repositorio, seleccionar ese tag y seguir la instalación de este documento. `.env` y el entorno virtual no forman parte de la entrega; cada instalación debe configurar su credencial localmente.
