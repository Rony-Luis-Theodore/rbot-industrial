# Comparación: Arquitectura Hexagonal vs Estilo Chatbot UCV

Documento para el equipo R-Bot. Ambas versiones conviven en el repo.

---

## Dónde está cada una

| Versión | Carpeta | Puerto | Cómo arrancar |
|---------|---------|--------|---------------|
| **A — Hexagonal** | `backend/` + `frontend/` | **8000** | `cd backend && uvicorn app.main:app --reload --port 8000` |
| **B — UCV-style** | `rbot-ucv-style/` | **8001** | `cd rbot-ucv-style && python app.py` |
| Original compañero | `CHATBOT_UCV-master/` | 8000 | Chatbot RAG UCV (Ollama) — no es R-Bot |

---

## Diagrama de flujo

### Versión A (Hexagonal)

```
Frontend modular (js/components/*)
        ↓ POST /api/v1/chat
Router delgado (api/v1/chat.py)
        ↓
ChatOrchestrator (services/)
        ↓              ↓
LLMService (interface)  ROSService (interface)
        ↓              ↓
adapters/llm/mock       adapters/ros/mock
```

### Versión B (UCV-style, como el chatbot del compañero)

```
static/index.html (todo en un archivo)
        ↓ POST /api/chat + history
app.py  (FastAPI + AgentState + nodos)
        ↓
classify → ros | directo | fuera
             ↓
        execute_ros (mock) / direct / out_of_scope
```

En el chatbot UCV original, la rama `ros` era `rag` (ChromaDB + Ollama).

---

## Tabla de diferencias

| Aspecto | Hexagonal (A) | UCV-style (B) |
|---------|---------------|---------------|
| Archivos backend | Muchos, por capa | Principalmente `app.py` |
| Separación LLM/ROS | Interfaces + adapters | Funciones/nodos en el mismo archivo |
| Versionado API | `/api/v1/...` | `/api/...` |
| Historial chat | No (aún) | Sí, en el navegador |
| Badge de modo | Metadatos intent en JSON | Badge visual ROS/DIRECTO/FUERA |
| Cambiar proveedor LLM | `.env` + factory | Reescribir `classify_node` |
| Trabajo en paralelo (equipo) | Mejor (pocos conflictos) | Peor (todos tocan `app.py`) |
| Velocidad de prototipo | Más setup | Más rápida |
| Escalabilidad | Alta | Limitada |
| Comentarios / onboarding | Exhaustivos por capa | Un README + docstrings en `app.py` |

---

## Qué tomó prestado del chatbot UCV

1. **Grafo de decisión**: clasificar → enrutar → responder  
2. **Historial en el cliente** enviado en cada `POST /api/chat`  
3. **UI de chat monolítica** (HTML+CSS+JS inline) con typewriter y badges  
4. **`profile.json`** para especialidad y mensaje fuera de dominio  
5. **Versión terminal** (`chat.py`)  
6. **Un solo proceso** FastAPI que sirve API + estáticos  

---

## Recomendación para el equipo

- Usar **A (hexagonal)** como base oficial del proyecto universitario (LLM y ROS2 reales).  
- Usar **B (UCV-style)** para:
  - Entender el enfoque de tu compañero
  - Prototipar UX de chat rápido
  - Comparar complejidad vs claridad en presentaciones

Cuando elijan una, pueden migrar ideas (p. ej. historial del navegador o badges de modo) de B hacia A sin mezclar carpetas.
