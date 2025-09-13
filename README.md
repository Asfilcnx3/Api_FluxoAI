
# Fluxo IA API

Arquitectura y código de la API usada en el proyecto de Fluxo para el análisis de texto que viene de PDF's no escaneados.

## Actualización 7-16 a 9-6

- Esta actualización permite que la API tenga una busqueda más robusta, siguiendo los requerimientos que se dieron previamente.
  Tambien permite la posibilidad de que haya "palabras comunes" que se van a buscar de misma forma que las especificas.

- Esta actualización permite que la API tenga una busqueda del RFC, Cuenta Clabe y Nombre del negocio o dueño, siguiendo los requerimientos que se dieron previamente.

- Esta actualización refactorizó todo el código, agregando mejoras a la lectura de los campos clave sin contar con los de extracción por regex, se modificó el endpoint principal para poder tener mejor control sobre los errores, documentos y el tipo de documento. Se eliminaron varias funciones y se agregaron muchas otras. Se agregó también las funciones asincronas para poder hacer varias llamadas a la API de forma paralela.

- Esta actualiazción agregó varias cosas como: el proceso en paralelo en el CPU de los documentos escaneados, resolución de errores como documentos con contraseña, extracción de texto más rapido, cambio de una librería que hacía un problema en el test, nuevos conceptos que puede buscar la API dentro de los diferentes bancos, un segundo modelo que mejore la visualización de los datos de la caratula, el primer modelo se le dió mejor calidad de imagen y un mejor prompt, también se agregó una validación con regex para mayor precisión.

- El ocr que se usa es Pytesseract con Tesseract-OCR

- Esta actualización agregó más robustes a los bancos 'Azteca', 'Inbursa', 'Afirme', 'BBVA', 'Multiva' e 'Intercam', mejorando la forma en la que algunos detectan transacciones y creando un soporte para bancos sin descripción anteriores como intercam e inbursa. La actualización trae consigo 2 bugs posibles, uno en BBVA con un inicio de concepto que puede ser el mismo que otros pero sin ser necesario escanear y eso causa fallos mínimos (no detectar 1 o 2 conceptos por PDF) y el otro es con el banco AFIRME, el error es a proposito ya que el banco tiene un tipo de outlier y en ese pdf la fecha y descripcion están volteadas.

- En esta actualización se agrega un router a la API para el mismo cliente pero con otras reglas de negocio para la extracción, estas nuevas reglas que sigue son para un negocio llamado "NomiFlash". Este router es asincrono, lo que hace que se analicen las llamadas en paralelo por la API de OpenAI, los parametros a analizar son 3 y siguen reglas de negocio al finalizar la estracción.

- Esta actualización agrega la lectura de QR por medio de una librería que maneja imagenes, se cambió un poco la forma de analizar cada estado de cuentas y el resultado se agregó lo que el qr trae por defecto.

- Esta actualización agrega un nuevo tipo de lógica que mejora el json structure para la salida de datos, mejora la lógica interna y ya no se bloquea el proceso si tiene menos de 250,000 pesos.
Mejora la validación de pydantic.

- Se agrega una validación para que el servidor no se caiga al analizar muchos documentos TPV analizados. Se agregó un campo de analisis general para el cliente. se agregó una mejor validación pydantic para los modelos que se están trabajando.

## REESTRUCTURA TOTAL 9-12

- Cada vez hay más requerimientos fuertes dentro del proyecto, por lo tanto se tomó la decisión de reestructurar todo el proyecto de forma completa.

  Se agregaron los siguientes campos:
    - Endpoint para Constancias de Situación Fiscal
    - El endpoint main se reestructuró y se creó el Endpoint "Fluxo"
    - Reestructuración de funciones clave como "leer_texto_pdf" que ahora se unieron 3 funciones en la misma. [leer el código para leer los cambios]
    - Reestructuración de las carpetas y módulos completos del proyecto para un manejo más sencillo
    - Cambio en el .env y en el responses.py
    - Se agregó settings para poder verificar los campos clave dentro de .env
    - Se agregaron los routers dentro de la carpeta "endpoints"
    - Se agregaron los tests
    - Se agregaron principiosd CI/CD para la implementación en Git
    - El código y su estructura ahora sigue las mejores prácticas y estructura para la API.

## Referencias de la API

### Variables de entorno

La API usa "load_dotenv", asi que las variables de entorno para que funcione todo el código que debes tener son las siguientes:

#### --- API Configuration ---
API_V1_STR=/api/v1

APP_VERSION=1.1.3

PROJECT_NAME=Extracción de Texto de PDFs con IA

DEV_NAME=Abraham - KiaB

#### --- OpenAI Configuration ---
OPENAI_API_KEY_FLUXO=

FLUXO_MODEL=gpt-5

OPENAI_API_KEY_NOMI=

NOMI_MODEL=gpt-5

#### --- OpenRouter Configuration ---
OPENROUTER_API_KEY=

OPENROUTER_BASE_URL=

#### --- Environment ---
ENVIRONMENT="development"

#### --- DEVELOPMENT SETTINGS ---
DEBUG=true

LOG_LEVEL="INFO"

#### Home

```http
  GET /
```

| Parameter | Type     | Description                |
| :-------- | :------- | :------------------------- |
| `None` | `None` | `Saludo de bienvenida` |

#### Procesar los PDF's

```http
  POST /procesar_pdf/
```

| Parameter | Type     | Description                       |
| :-------- | :------- | :-------------------------------- |
| `Archivo` | `Archivo`| **Obligatorio**. Archivo en formato PDF |

## Para correrlo localmente en Docker

Clona el proyecto

```bash
  git clone https://github.com/Asfilcnx3/Api_FluxoAI.git fluxo-api
```

Ve al directorio del proyecto

```bash
  cd my-project
```

entra a vs code

```bash
  code .
```

Abre docker 

```bash
  --  Tienes que abrir docker desktop y asegurarte que esté el "Engine Runing" --
```

Inicia el servidor - En la terminal de vscode

```bash
  docker-compose up
```
## Despligue sin Docker

Para desplegar este proyecto sin docker corre

Clona el proyecto

```bash
  git clone https://github.com/Asfilcnx3/Api_FluxoAI.git fluxo-api
```

Ve al directorio del proyecto

```bash
  cd my-project
```

entra a vs code

```bash
  code .
```

crea el entorno virtual (terminal de vscode)

```bash
  python -m venv venv
```

Activa el proceso para el entorno (en windows)

```bash
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

Activa el entorno (en windows)

```bash
  venv/scripts/activate
```

Instala todas las dependencias

```bash
  pip install -r requirements.txt
```

Activa el servidor localmente

```bash
  uvicorn Fluxo_IA_visual.main:app --reload
```
## Authors

- [@Asfilcnx3](https://github.com/Asfilcnx3) -- Abraham from KiaB