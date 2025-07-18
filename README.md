
# Fluxo IA API

Arquitectura y código de la API usada en el proyecto de Fluxo para el análisis de texto que viene de PDF's no escaneados.

## Actualización 7-16

Esta actualización permite que la API tenga una busqueda más robusta, siguiendo los requerimientos que se dieron previamente.

Tambien permite la posibilidad de que haya "palabras comunes" que se van a buscar de misma forma que las especificas.

## Actualización 7-17

Esta actualización permite que la API tenga una busqueda del RFC, Cuenta Clabe y Nombre del negocio o dueño, siguiendo los requerimientos que se dieron previamente.

## Referencias de la API

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
  uvicorn Fluxo_IA_v2.main:app --reload
```
## Authors

- [@Asfilcnx3](https://github.com/Asfilcnx3)