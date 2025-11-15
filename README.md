# AI-QA-PG

**AI-Powered Question Answering System for Construction Documents**

A Retrieval-Augmented Generation (RAG) system designed for construction teams to search and query PDF documents (permits, specifications, drawings, RFIs) with precise citations and answers.

## Overview

AI-QA-PG is a full-stack application that enables natural language querying of construction documents. It uses hybrid search (BM25 + vector similarity), reranking, and large language models to provide accurate answers with page-level citations and bounding box coordinates.

### Key Features

- **Document Ingestion**: Upload PDF documents with automatic text extraction, OCR for scanned pages, and table extraction
- **Hybrid Search**: Combines BM25 keyword search with k-NN vector search using HNSW algorithm
- **Vision LLM**: Processes architectural drawings, diagrams, and image-based content
- **Intelligent Reranking**: Uses Cohere Rerank for improved result relevance
- **Answer Generation**: Provides contextualized answers with precise citations
- **Chat Interface**: ChatGPT-style UI with conversation history and streaming responses
- **Dashboard**: PDF upload interface with real-time ingestion progress and API health monitoring
- **Query Suggestions**: Automatically suggests alternative phrasings when queries return no results

## Architecture

### Technology Stack

**Backend:**
- Python 3.11+ with FastAPI
- PostgreSQL for metadata and conversations
- OpenSearch for vector search and full-text search
- PyMuPDF for PDF processing
- Unstructured.io for complex table extraction

**Frontend:**
- Next.js 14 with React 18
- TypeScript
- Tailwind CSS
- PDF.js for document viewing

**AI/ML:**
- Naga AI API
- Gemini embeddings (gemini-embedding-001, 3072 dimensions)
- Claude Haiku 4.5 for answer generation 
- GPT-4o-mini for vision tasks
- Cohere for reranking

### System Components

```
API (FastAPI)
├── Ingestion Pipeline
│   ├── PDF extraction (PyMuPDF)
│   ├── Table of Contents parsing
│   ├── Vision LLM processing
│   ├── Table extraction (Unstructured.io)
│   ├── Text chunking
│   ├── Embedding generation
│   └── OpenSearch indexing
│
├── Search & Retrieval
│   ├── Hybrid search (BM25 + k-NN)
│   ├── Table search
│   ├── TOC-aware routing
│   └── Cohere reranking
│
└── Question Answering
    ├── Context building
    ├── LLM generation
    ├── Citation extraction
    └── Query suggestions

Frontend (Next.js)
├── Chat interface with streaming
├── Dashboard with PDF upload
├── PDF viewer with citation highlighting
└── Notification system
```

## Prerequisites

### Software Requirements

- **Python 3.11 or higher**
- **Node.js 18 or higher**
- **PostgreSQL 15**
- **OpenSearch 2.x**

### API Keys Required

You will need API keys for the following services:

- **Naga AI** - For LLM and embedding API
- **Cohere** - For reranking
- **OpenAI/Gemini/Claude** (optional) - Individual API Keys if you don't want to use Naga AI API Keys

## Quick Start (Automated Setup)

### Option 1: Automated Installation (Recommended)

The easiest way to get started is using our automated setup scripts:

**macOS/Linux:**

```bash
git clone <repository-url>
cd AI-QA-PG
./setup-macos.sh
```

**Windows:**

```batch
git clone <repository-url>
cd AI-QA-PG
setup-windows.bat
```

The setup script will:
- Check for required software (Python, Node.js, PostgreSQL, OpenSearch)
- Install all backend and frontend dependencies
- Create data directories
- Set up environment variables
- Initialize database schema
- Create OpenSearch indices
- Generate a start script for easy launching

After setup completes, just run:

**macOS/Linux:** `./start.sh`

**Windows:** `start.bat`

Then open `http://localhost:3000` in your browser.

### Option 2: Manual Installation

If you prefer to install manually or need more control:

#### 1. Clone the Repository

```bash
git clone <repository-url>
cd AI-QA-PG
```

#### 2. Configure Environment Variables

```bash
cp infra/.env.example infra/.env
```

Edit `infra/.env` with your API keys:

```env
NAGA_API_KEY=your_naga_api_key_here
COHERE_API_KEY=your_cohere_api_key_here
POSTGRES_DSN=postgresql://username@localhost:5432/ai_qa_pg
```

#### 3. Install Dependencies

**Backend:**
```bash
cd api
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

**Frontend:**
```bash
cd app
npm install
cd ..
```

#### 4. Setup Services

**PostgreSQL:**
```bash
createdb ai_qa_pg
psql ai_qa_pg < api/db/schema.sql
```

**OpenSearch (using Docker):**
```bash
docker run -d -p 9200:9200 -e "discovery.type=single-node" opensearchproject/opensearch:2.11.0
```

**Create Indices:**
```bash
cd api
source venv/bin/activate
python search/create_index.py
python search/create_table_index.py
```

#### 5. Start the Application

**Terminal 1 - Backend:**
```bash
cd api
source venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 - Frontend:**
```bash
cd app
npm run dev
```

Open `http://localhost:3000` in your browser

## Usage

### Uploading Documents

1. Navigate to the Dashboard at `http://localhost:3000/dashboard`
2. Click "Choose File" and select a PDF document
3. Enter the project details:
   - Project ID (e.g., "project_001")
   - Document Type (e.g., "permit", "specification", "drawing")
   - Discipline (e.g., "architectural", "structural", "mechanical")
4. Click "Upload & Ingest"
5. Monitor the progress bar for ingestion status

### Asking Questions

1. Navigate to the Chat interface at `http://localhost:3000/chat`
2. Select a project from the dropdown
3. Type your question (e.g., "What are the fire resistance requirements for wall W1A?")
4. Press Enter or click Send
5. View the answer with citations
6. Click on citations to view the source document with highlighted sections

### API Endpoints

**Document Management:**
- `POST /admin/upload-pdf` - Upload and ingest PDF
- `GET /admin/documents` - List all documents
- `DELETE /documents/{doc_id}` - Delete a document

**Query & Search:**
- `POST /qa` - Ask a question (non-streaming)
- `POST /qa/stream` - Ask a question (streaming response)
- `POST /search` - Search documents

**System:**
- `GET /health` - API health check
- `GET /health/status` - Detailed service status
- `GET /projects/list` - List all projects

API documentation is available at `http://localhost:8000/docs`

## Configuration

### LLM Models

The system supports multiple LLM providers and models. Edit `infra/.env`:

**For Claude Haiku (Fast, Recommended):**
```env
LLM_PROVIDER=naga
LLM_MODEL=claude-haiku-4.5
```

**For GPT-4o (Higher Quality):**
```env
LLM_PROVIDER=naga
LLM_MODEL=gpt-4o
```

**For Cohere Command R (Optimized for RAG):**
```env
LLM_PROVIDER=cohere
LLM_MODEL=command-r-08-2024
COHERE_API_KEY=your_cohere_api_key
```

### Vision LLM

The system uses a separate model for processing images, drawings, and diagrams:

```env
USE_VISION_LLM=true
VISION_LLM_PROVIDER=naga
VISION_LLM_MODEL=gpt-4o-mini
VISION_MIN_IMAGE_COVERAGE=0.20
```

Vision LLM triggers when image coverage exceeds 20% of a page.

### Feature Flags

```env
USE_VISION_LLM=true          # Enable vision processing for images
USE_UNSTRUCTURED=true        # Enable table extraction via Unstructured.io
USE_PYMUPDF_TABLE_PARSER=false  # PyMuPDF table parser (alternative)
```

## Project Structure

```
AI-QA-PG/
├── api/                      # Backend FastAPI application
│   ├── core/                 # Configuration and settings
│   ├── db/                   # Database schemas and migrations
│   ├── ingest/               # Document ingestion pipeline
│   ├── llm/                  # LLM and embedding clients
│   ├── qa/                   # Question answering logic
│   ├── search/               # Search and retrieval
│   └── main.py               # FastAPI application entry point
│
├── app/                      # Frontend Next.js application
│   ├── app/                  # Next.js pages (chat, dashboard, viewer)
│   ├── components/           # React components
│   ├── lib/                  # API client and utilities
│   └── public/               # Static assets
│
├── infra/                    # Infrastructure configuration
│   ├── .env.example          # Environment variables template
│   └── docker-compose.yml    # Docker configuration (optional)
│
└── data/                     # Data directories
    ├── uploads/              # Uploaded PDF files
    └── extracts/             # Temporary extraction files
```

## Development

### Running Tests

```bash
cd api
pytest
```


### Adding New LLM Providers

1. Create a new client class in `api/llm/chat.py`
2. Implement the `chat()` and `stream()` methods
3. Update `get_chat_client()` factory function
4. Add configuration in `api/core/settings.py`

## Project Workflow

This section describes how the system processes documents and answers questions, including the intelligent query suggestion feature.

### 1. Document Ingestion Pipeline

When a PDF is uploaded through the dashboard or API:

**Step 1: Upload & Validation**
- User uploads PDF via `/dashboard` or `/admin/upload-pdf` endpoint
- System validates file type and saves to `data/uploads/` directory
- Metadata (project_id, doc_type, discipline) is recorded in PostgreSQL

**Step 2: Text Extraction**
- PyMuPDF extracts native text from PDF
- For scanned pages, OCR is triggered (Tesseract)
- Page-level text is stored with page numbers

**Step 3: Table of Contents (TOC) Parsing**
- System detects and parses TOC structure
- Page ranges are mapped to sections (e.g., "Fire Resistance" -> pages 45-52)
- TOC data is stored for query routing

**Step 4: Vision LLM Processing**
- If page has >20% image coverage, Vision LLM is triggered
- GPT-4o-mini analyzes architectural drawings, diagrams, and visual elements
- Extracts structured data: dimensions, labels, specifications
- Searchable text is generated from visual content

**Step 5: Table Extraction**
- Unstructured.io processes tables on each page
- Complex tables (Fire Resistance, Sound Transmission) are parsed
- Table rows are stored separately in `table_rows_v2` index

**Step 6: Text Chunking**
- Text is split into semantic chunks (max 800 chars)
- Each chunk retains:
  - Page number
  - Bounding box coordinates
  - Section (from TOC)
  - Source (native text, OCR, vision, or table)

**Step 7: Embedding Generation**
- Each chunk is embedded using Naga AI (text-embedding-3-large, 3072 dimensions)
- Embeddings are stored in OpenSearch with chunk metadata

**Step 8: Indexing**
- Chunks are indexed in OpenSearch `chunks_v2` (k-NN optimized)
- BM25 and HNSW vector indices are created
- Document status is updated to "completed" in PostgreSQL

**Progress Tracking:**
- Real-time progress updates are sent to frontend
- Background task continues even if user navigates away
- Notification is sent when ingestion completes

### 2. Question Answering Workflow

When a user asks a question in the chat interface:

**Step 1: Query Processing**
- User types question and selects project/filters
- Frontend sends request to `/qa/stream` endpoint
- System generates query embedding (3072-d vector)

**Step 2: TOC-Aware Routing**
- Query is matched against TOC entries
- If match found (e.g., "fire resistance" -> TOC section), page ranges are boosted
- This improves precision by prioritizing relevant document sections

**Step 3: Hybrid Search (Parallel Execution)**
- Two searches run simultaneously:
  - **Document Search:** BM25 + k-NN vector search on `chunks_v2`
  - **Table Search:** Hybrid search on `table_rows_v2`
- Top 64 document chunks and top 20 table rows are retrieved
- Results are combined into a single candidate pool

**Step 4: Reranking**
- Cohere Rerank v3 rescores all candidates
- Cross-encoder model evaluates query-chunk relevance
- Top 15 most relevant chunks are selected

**Step 5: Context Building**
- Selected chunks are formatted with metadata:
  ```
  [1] doc_id=abc123 page=10 section="Fire Resistance" bbox=[100,200,400,500]
  Text: "Wall W1A requires 1-hour fire resistance rating..."
  ```
- Context is limited to fit within LLM token limits

**Step 6: Answer Generation (Streaming)**
- System sends context + query to LLM (Claude Haiku 4.5 by default)
- LLM generates answer in JSON format:
  ```json
  {
    "answer": "Wall W1A requires...",
    "citations": [
      {"doc_id": "abc123", "page_number": 10, "snippet": "...", "bbox": [100,200,400,500]}
    ]
  }
  ```
- Answer is streamed token-by-token to frontend
- User sees real-time progress: "Searching..." -> "Ranking..." -> "Generating..." -> Answer

**Step 7: Citation Enrichment**
- Bounding boxes are attached to citations
- Frontend displays clickable citations with page numbers
- Clicking a citation opens PDF viewer with highlighted region

**Step 8: Response Delivery**
- Final answer is saved to conversation history (PostgreSQL)
- User can continue asking follow-up questions
- Conversation context is maintained

### 3. Intelligent Query Suggestions

When the LLM returns "Not found in the project documents," the system automatically generates alternative query suggestions:

**Step 1: Detection**
- System detects "Not found" response from LLM
- Query suggestion pipeline is triggered

**Step 2: Suggestion Generation**
- System generates 3 alternative phrasings using LLM:
  - Original: "What is the fire rating for wall W1A?"
  - Alternatives:
    1. "What are the fire resistance requirements for wall W1A?"
    2. "What is the hourly fire resistance rating for wall W1A?"
    3. "What fire protection is specified for wall W1A?"

**Step 3: Suggestion Testing (Sequential)**
- Each alternative query is tested against the system:
  - Run hybrid search
  - Rerank results
  - Generate answer with LLM
- Only suggestions that return valid answers (not "Not found") are kept

**Step 4: Result Caching**
- Working suggestions are cached with:
  - Alternative query text
  - Answer preview (first 150 characters)
  - Citation count
  - Full answer and citations (pre-fetched)

**Step 5: Frontend Display**
- Frontend displays suggestion cards:
  ```
  "Try asking instead:"
  
  1. What are the fire resistance requirements for wall W1A?
     Preview: "Wall W1A requires a 1-hour fire resistance rating..."
     (3 citations)
  ```
- User can click a suggestion to instantly see the answer (no re-query needed)

**Step 6: User Experience**
- Suggestions appear within 2-3 seconds of "Not found" response
- Clicking a suggestion displays the cached answer immediately
- This helps users discover information even with imperfect queries


## License

Unauthorized copying, distribution, or use is prohibited.

## Support

For setup assistance:
- Run the automated setup script (`setup-macos.sh` or `setup-windows.bat`)
- Check the manual installation instructions in this README
- Review the API documentation at `http://localhost:8000/docs`

