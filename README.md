# UltraAssist

A scalable, multi-domain Retrieval-Augmented Generation (RAG) service designed to power intelligent assistants using structured (FRS/URS) and unstructured (manual/docs) data. It is powered by Open WebUI, LiteLLM, and a custom FastAPI RAG service. It leverages AWS Bedrock for state-of-the-art LLMs (like Anthropic Claude models and OSS models) to provide context-aware, document-backed assistance.

This service enables context-aware query answering by combining:

- Requirement-aware retrieval (FRS/URS)
- Semantic + keyword hybrid ranking
- Multi-source document ingestion (DOCX, PDF, TXT)
- Optional image understanding using AWS Bedrock

## Project Architecture

The project consists of three main components orchestrated via Docker Compose:

1. **LiteLLM Proxy (`litellm`)**
   - **Role:** Acts as an API gateway proxying requests to AWS Bedrock models.
   - **Configuration:** Managed via `litellm_config.yaml`.
   - **Models Supported:** `claude-4-sonnet`, `claude-4-5-haiku`, `open-ai-gpt-oss-120b` (via Bedrock).
   - **Port:** `4001`

2. **Custom RAG Service (`rag-service`)**
   - **Role:** A dedicated FastAPI backend that handles document ingestion, chunking, embedding, and intelligent retrieval.
   - **Tech Stack:** FastAPI, Sentence-Transformers, ChromaDB, Boto3, PyMuPDF.
   - **Key Capabilities:**
     - Handles various document types including PDF and DOCX.
     - Performs semantic search and hybrid ranking (`hybrid_ranker.py`, `retriever.py`).
     - Extracts and analyzes image semantics using Vision models (`image_analyzer.py`).
     - Analyzes queries and assembles contexts (`query_analyzer.py`, `context_assembler.py`).
     - Offers generic and specialized indexing (`generic_indexer.py`, `frs_indexer.py`).
   - **Port:** `8020`
   - This RAG system is domain-aware, meaning that the same service can power multiple assistants just by changing:
      - department
      - purpose

3. **Open WebUI (`open-webui`)**
   - **Role:** The frontend chat interface and primary routing layer.
   - **Capabilities:** Connected to LiteLLM for generation and the custom RAG service for knowledge retrieval. Utilizes custom pipeline functions for seamless RAG integration and generating DOCX outputs.
   - **Custom Functions:** Located in `open_webui_functions/` (e.g., `ultraassist_rag_function.py`, `format_output_and_generate_docx.py`).
   - **Port:** `3001` (mapped to `8080` internally)

## Project Structure

```text
UltraAssist/
├── docker-compose.yml       # Defines the multi-container architecture
├── Dockerfile.openwebui     # Dockerfile for Open WebUI
├── Dockerfile.rag           # Dockerfile for the custom FastAPI RAG service
├── litellm_config.yaml      # Configuration for the LiteLLM Proxy routing
├── requirements.txt         # Python dependencies for the RAG service
├── .env                     # Environment variables (AWS keys, model settings, thresholds)
├── rag_service/             # Source code for the FastAPI RAG backend
│   ├── main.py              # Entry point for the FastAPI application
│   ├── embedder.py          # Document embedding logic
│   ├── vector_store.py      # ChromaDB integration
│   ├── retriever.py         # Context retrieval
│   ├── indexers...          # FRS and Generic document indexers
│   └── ...                  # Other RAG components (Query Analyzer, Hybrid Ranker)
├── open_webui_functions/    # Custom functions injected into Open WebUI
│   ├── ultraassist_rag_function.py
│   ├── format_output_and_generate_docx.py
│   └── download_generated_docx.py
├── chunks_db/               # Persistent ChromaDB vector storage (Volume)
├── data/                    # Document data storage (Volume)
├── output/                  # Generated DOCX outputs (Volume)
├── static/                  # Static assets for the frontend (Volume)
└── functions/               # Open WebUI standard functions directory (Volume)
```

## Setup and Installation

### Prerequisites
- Docker and Docker Compose
- AWS Account with Bedrock access (Ensure valid `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`)

### Quick Start

1. **Configure Environment Variables**
   Update the `.env` file with your specific AWS credentials, LiteLLM keys, and WebUI secrets.

2. **Start the Application**
   Run the following command to build and start the containers in detached mode:
   ```bash
   docker-compose up -d --build
   ```

3. **Access the Services**
   - **Open WebUI (Frontend):** [http://localhost:3001](http://localhost:3001)
   - **RAG Service API Docs:** [http://localhost:8020/docs](http://localhost:8020/docs)
   - **LiteLLM Proxy:** [http://localhost:4001](http://localhost:4001)

## Configuration Highlights

The system behaviour is highly customizable via the `.env` file:
- **Similarity Thresholds:** Control the strictness of document retrieval (`CSV_SIMILARITY_THRESHOLD`, `PDF_SIMILARITY_THRESHOLD`).
- **Embedding Models:** Swap embedding models via `EMBEDDING_MODEL` (default: `all-MiniLM-L6-v2`).
- **Vision Semantics:** Image extraction and description generation using Bedrock Vision Models (`ENABLE_IMAGE_SEMANTICS`).

## Features

### Dual Retrieval Pipelines
#### FRS Pipeline (Structured)
- Extracts requirements from DOCX files
- Supports FRS ID, URS ID, heading-based queries
- Builds requirement-level embeddings
#### Generic Pipeline (Unstructured)
- Handles DOCX, PDF, TXT
- Chunk-based indexing for large documents

### Intelligent Query Understanding
- Detects:
   - FRS IDs (UIT-FR-*)
   - URS IDs (UIT-UR-*)
   - Heading IDs
- Falls back to semantic heading matching when needed

### Hybrid Ranking Engine
- Combines:
   Semantic similarity
   Keyword overlap
   Intent boosting (FRS/Heading match)
   Document diversity control

## Architecture Overview
```
User Query
    ↓
Query Analyzer
    ↓
Retriever
 ├── FRS Flow (structured)
 └── Generic Flow (unstructured)
    ↓
Hybrid Ranker
    ↓
Context Assembler
    ↓
LLM (via OpenWebUI / LiteLLM / Bedrock)
```
## Core Components

### Query Analyzer
Detects IDs + semantic headings

### Hybrid Ranker
Combines semantic + keyword + intent scoring

### Embedding Engine
Model: all-MiniLM-L6-v2
Dimension: 384

### Vector Store
ChromaDB (persistent)
Separate collections for structured/unstructured data

### Image Analyzer (Optional)
Uses AWS Bedrock Vision for diagram understanding

## Performance Optimisations
- Cached embeddings
- Batch processing
- Hybrid ranking
- Context compression
- Scoped filtering

## Debug & Utility APIs
|Endpoint	|Description|
| -------------------------------- | -------------------- |
|/health	|Service health|
|/indexing-status	|Indexing progress|
|/debug/frs_dump	|Inspect FRS data|
|/debug/generic_dump	|Inspect generic data|
|/debug/clear_frs	|Clear FRS collection|
|/debug/clear_generic	|Clear generic collection|
|/debug/recreate_frs_collection	|Full reindex|

