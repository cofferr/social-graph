# Social Graph · Curso

Análisis de grafo social de Instagram para el grupo del curso. Visualización interactiva con Sigma.js + NetworkX.

## Setup

```bash
pip install -r requirements.txt
```

## Estructura

```
social_graph/
├── app.py                    # UI principal Streamlit
├── requirements.txt
├── pipeline/
│   ├── ingestion.py          # Carga, dedup, merge de JSONs
│   └── graph_builder.py      # Construye grafo + métricas
├── viz/
│   └── renderer.py           # Componente Sigma.js
└── data/
    ├── raw/
    │   ├── following/        # ← Coloca aquí los following.json
    │   └── followers/        # ← Coloca aquí los followers.json
    ├── registry/             # Registro de archivos procesados (auto)
    └── graph_data.json       # Datos del grafo unificado (auto)
```

## Uso

### Opción 1 — Carpeta local
Coloca los archivos JSON de Instagram en la carpeta correspondiente:

- `data/raw/following/` — para archivos de seguidos (`following.json`)
- `data/raw/followers/` — para archivos de seguidores (`followers_1.json`, etc.)

Convención de nombres para auto-detectar el owner:
- `following_jorge.json` → owner = jorge
- `followers_maria.json` → owner = maria
- `following.json` → owner desconocido (se intenta inferir)

Luego presiona **Escanear carpetas** en la sidebar.

### Opción 2 — Upload en la app
Arrastra los archivos al uploader de la sidebar. Puedes declarar tu username o dejarlo vacío.

## Ejecutar

```bash
streamlit run app.py
```

## Archivos que exporta Instagram

En la app de Instagram: **Configuración → Tu actividad → Descargar tu información → Conexiones**

Archivos relevantes:
- `following.json` — a quiénes sigues
- `followers_1.json` — quiénes te siguen

## Métricas calculadas

| Métrica | Descripción |
|---|---|
| In-degree | Cuántas personas del dataset te siguen |
| Out-degree | A cuántas personas del dataset sigues |
| Mutuos | Seguimientos recíprocos |
| Betweenness | Qué tan "puente" eres entre comunidades |
| PageRank | Importancia por calidad de conexiones |
| Closeness | Qué tan cerca estás del resto de la red |
| Clustering | Qué tan conectado está tu círculo |
| Comunidad | Grupo detectado por algoritmo Louvain |

## Deduplicación

Los archivos se identifican por un hash SHA-256 del conjunto de pares `(username, timestamp)` de cada relación. Si alguien sube el mismo archivo dos veces, se detecta automáticamente como duplicado sin necesidad de IDs externos.
