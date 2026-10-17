# Didacteca Generator

API en Python/FastAPI para responder preguntas, generar quizzes y preparar actividades utilizando exclusivamente una sección del Context Service de Didacteca. La versión **0.1.1** conserva las tres capacidades, LaTeX y extracción con citas obligatorias, y añade controles defensivos de entrada, recursos y proveedores.

Pasan **210 pruebas automatizadas**. La instalación limpia de 0.1.1 está comprobada en Windows/Python 3.12.14; el workflow comprueba cada publicación en Windows y Ubuntu 24.04. La evidencia con servicios reales y sus límites se detalla abajo. Repositorio público: [IsaiFR/Didacteca-Generator](https://github.com/IsaiFR/Didacteca-Generator). Versión reforzada: `v0.1.1`; la entrega inicial `v0.1.0` se conserva.

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

Resultado comprobado en Windows/Python 3.12.14 para 0.1.1: instalación correcta, dependencias sin incompatibilidades, **210 pruebas aprobadas en 3,95 s** y contrato HTTP aprobado. [Informe de instalación](output/install-check-windows.json).

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
| `MAX_CONTEXT_RESPONSE_BYTES` | 524288, antes de cargar el JSON externo. |
| `MAX_REQUEST_BODY_BYTES` | 65536, bytes reales del cuerpo HTTP. |
| `REQUEST_BODY_TIMEOUT_SECONDS` | 10, tiempo para recibir el cuerpo completo. |
| `MAX_CONCURRENT_EXECUTIONS` | 4 solicitudes simultáneas por proceso. |
| `RATE_LIMIT_REQUESTS` | 30 solicitudes por cliente en la ventana. |
| `RATE_LIMIT_WINDOW_SECONDS` | 60 |
| `RATE_LIMIT_MAX_CLIENTS` | 1024 entradas máximas; se puede reducir. |

Son límites operativos elegidos para esta prueba. No son equivalencias pedagógicas ni límites oficiales del modelo. Superarlos produce un resultado explícito, sin reducir cantidades o cambiar la petición silenciosamente.

La prueba original indica Context Service por HTTP. En la comprobación esa dirección redirigió perdiendo método o cuerpo; HTTPS directo funcionó y permanece configurable. No se envía la clave de OpenAI a ese servicio. OpenAI usa su base oficial fija `https://api.openai.com/v1`; un `OPENAI_BASE_URL` heredado no redirige esta integración.

Después de configurar la credencial:

```text
python -m uvicorn didacteca_ai.main:app --app-dir src --host 127.0.0.1 --port 8000 --no-proxy-headers
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
| 400 / 408 / 413 / 415 | JSON inválido/ambiguo, recepción lenta, cuerpo excesivo o tipo de contenido no admitido. |
| 422 | Entrada inválida, aclaración, conflicto de reglas, contenido vacío/insuficiente/excesivo o rechazo del modelo; distinguir por código. |
| 404 | `BOOK_NOT_FOUND`, `SECTION_NOT_FOUND`. |
| 429 | Límite temporal por cliente; incluye `Retry-After`. |
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

### Seguridad y alcance de las verificaciones

La versión reforzada conserva los cuatro campos y los éxitos del contrato. Añade controles antes de consumir proveedores:

| Superficie | Defensa implementada |
| --- | --- |
| Identificadores manipulados, rutas o URL | Solo letras ASCII, números, `_` y `-`, sin normalización ni sustitución, con límite de longitud. |
| Prompt injection directa | Rechazo local de algunas órdenes explícitas para anular reglas, suplantar roles, revelar secretos o ejecutar comandos. Inspección Unicode sobre una copia; conserva la petición y sus citas originales. |
| Contenido del libro no confiable | Se mantiene como referencia en mensajes separados, sin herramientas, acceso a archivos ni claves dentro del prompt. La evidencia interna no cambia el esquema público. |
| Cuerpo excesivo o ambiguo | Límite de bytes reales, incluso sin Content-Length; JSON obligatorio, sintaxis válida y claves únicas. |
| Subidas lentas y saturación | Timeout de recepción, máximo de solicitudes simultáneas y límite temporal por cliente con memoria acotada. |
| Respuesta externa excesiva | Lectura por stream con límite de bytes, timeout y cierre; se rechaza compresión inesperada antes de leerla. |
| Interpretación por el navegador | Respuestas JSON con `nosniff` y `no-store`. Un frontend futuro debe escapar HTML y sanear Markdown; el JSON no habilita HTML confiable. |
| Dependencias | Auditoría con `pip-audit` en CI; versiones fijadas y corrección de la vulnerabilidad conocida de pytest mediante 9.0.3. |

**SQL injection:** esta aplicación no tiene base de datos, consultas SQL ni ejecución de código del usuario. Los identificadores válidos se envían como datos JSON, nunca como SQL, rutas o comandos. No se bloquean palabras SQL dentro de preguntas educativas. Si posteriormente se añade una base de datos, deberá utilizar consultas parametrizadas; no confiar en listas de palabras prohibidas. Esto no evalúa la seguridad interna del Context Service. [OWASP: SQL injection](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html).

El filtro de prompt injection es conservador y parcial: admite ejemplos citados para analizarlos y no detecta todas las reformulaciones, codificaciones ni ataques indirectos. Sus pruebas con dobles verifican rechazo y flujo, no inmunidad semántica del modelo real. Se mantiene la defensa por capas, las salidas estrictas y el presupuesto de llamadas. [OWASP: prompt injection](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html).

Los límites HTTP son **por proceso**. La ventana por cliente es fija y se identifica mediante la IP del transporte ASGI; clientes detrás de NAT pueden compartirla. Un despliegue con varios workers o instancias necesita controles compartidos. El comando de arranque usa `--no-proxy-headers` para impedir que cabeceras reenviadas alteren esa identidad; habilitarlas exige definir proxies confiables. No añadir confianza global en `X-Forwarded-For`. La app permanece ligada a loopback y no incorpora autenticación: para exponerla a Internet se requieren controles de acceso, TLS y límites en un proxy apropiado.

Errores nuevos: `INVALID_JSON` y `DUPLICATE_JSON_KEYS` (400), `REQUEST_BODY_TIMEOUT` (408), `REQUEST_BODY_TOO_LARGE` (413), `UNSUPPORTED_MEDIA_TYPE` (415), `REQUEST_RATE_LIMITED` (429), `EXECUTION_CAPACITY_REACHED` y `CLIENT_CAPACITY_REACHED` (503). Los rechazos temporales incluyen `Retry-After` y conservan `ErrorResponse`; ocurren antes de OpenAI. [OWASP: seguridad REST](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html).

Las pruebas adversariales se ejecutan localmente con proveedores de prueba. Incluyen inyección, suplantación, SQL/rutas en identificadores, fuentes envenenadas como datos, cuerpos fragmentados, JSON ambiguo, saturación, desconexiones y cancelación. No se atacaron Didacteca ni OpenAI, no se consumió la API para esta ampliación y no equivale a un pentest profesional ni a una certificación de seguridad.

La auditoría inicial encontró CVE-2025-71176 en pytest 8.4.2; se actualizó a 9.0.3. La auditoría posterior, con `pip-audit` 2.10.1 y los 35 paquetes fijados, no encontró vulnerabilidades conocidas: [informe](output/dependency-audit.json). Es una comprobación de avisos conocidos en la fecha de ejecución, no una garantía sobre vulnerabilidades desconocidas. [Aviso de pytest](https://github.com/advisories/GHSA-6w46-j5rx-g56g).

Para repetir la auditoría en un entorno de herramientas separado, instalar `pip-audit==2.10.1` y ejecutar:

```text
python -m pip_audit -r requirements.txt --no-deps --disable-pip
```

El archivo de requisitos fija también las dependencias transitivas. `--no-deps` evita resolver e instalar el proyecto durante el análisis; no demuestra integridad criptográfica de los paquetes. La auditoría necesita consultar el servicio de avisos y no modifica las credenciales de la app.

### Pruebas automatizadas

```text
python -m pytest -q
```

La suite de 0.1.1 aprobó **210 pruebas en 3,10 s**, con Python 3.12.14 y pytest 9.0.3: 88 casos adicionales respecto de la entrega inicial. Cubre contratos, tres capacidades, seis tipos de actividad, aclaraciones, límites, proveedores, reparación acotada, concurrencia, referencias, rúbrica, LaTeX y controles de seguridad. Las regresiones de extracción comprueban valor/cita obligatorios, ausencia como `null`, tipos estrictos, normalización, rechazo de citas inventadas y compatibilidad del esquema con el SDK. Las nuevas pruebas incluyen prefijos/montajes ASGI y rechazo de compresión antes de leer el contexto.

La instalación limpia repitió las 210 pruebas en 3,95 s. Se conserva una advertencia conocida de Starlette/TestClient sobre `httpx`; no produjo fallos. En el entorno aislado de desarrollo se requirió permitir el bucle local de TestClient; pytest no usa proveedores reales.

Con Uvicorn 0.1.1 en el puerto local también se comprobaron cinco rechazos por HTTP: tipo no JSON (415), claves repetidas (400), SQL en identificador (422), orden directa de prompt injection (422) y cuerpo excesivo (413), todos con cabeceras defensivas. [Informe HTTP local](output/security-http-check.json). Una consulta normal a Context Service recuperó los 835 caracteres de la sección de prueba con el nuevo cliente sin compresión. No se llamó a OpenAI para esta ampliación; las muestras educativas siguientes corresponden a 0.1.0, no acreditan una nueva evaluación semántica del modelo bajo 0.1.1.

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

Los documentos finales son este README, [contexto y límites](CONTEXTO_LIMITES_Y_OBJETIVOS.md), [diseño técnico](PLAN_TECNICO.md) e [instrucciones de agentes](AGENTS.md). Los informes actuales y ejemplos útiles permanecen en `output/`; los artefactos reemplazados se retiraron.

Esfuerzo aproximado de la implementación inicial y LaTeX: **una hora y media*.

Repositorio público: [IsaiFR/Didacteca-Generator](https://github.com/IsaiFR/Didacteca-Generator). La versión reforzada se identifica mediante [v0.1.1](https://github.com/IsaiFR/Didacteca-Generator/tree/v0.1.1); la entrega inicial [v0.1.0](https://github.com/IsaiFR/Didacteca-Generator/tree/v0.1.0) conserva su historial. Para reproducir una versión, clonar y seleccionar su tag. Los resultados por commit y la auditoría están en [GitHub Actions](https://github.com/IsaiFR/Didacteca-Generator/actions). `.env` y el entorno virtual no forman parte de la entrega; cada instalación configura su credencial localmente.
