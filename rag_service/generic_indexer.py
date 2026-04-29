from datetime import datetime
import os

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from embedder import EmbeddingManager
from image_analyzer import ImageAnalyzer
from vector_store import VectorStore

import fitz

def iter_block_items(parent):
    for child in parent.element.body.iterchildren():
        if child.tag.endswith("p"):
            yield Paragraph(child, parent)
        elif child.tag.endswith("tbl"):
            yield Table(child, parent)

class GenericIndexer:

    def __init__(self):
        print("[UltraAssist RAG - genericindexer.__init__] Initializing...")
        self.embedder = EmbeddingManager()
        self.image_analyzer = ImageAnalyzer()
        try:
            self.vector_store = VectorStore()
        except Exception as e:
            print("[UltraAssist RAG - genericindexer.__init__] VectorStore init failed:", e)

        self.enable_image_semantics = (
            os.getenv("ENABLE_GENERIC_IMAGE_SEMANTICS", "false").lower() == "true"
        )

        print("[UltraAssist RAG - genericindexer.__init__] Ready.")

    # ---------------------------------------------------
    # DOCX Extraction
    # ---------------------------------------------------

    def extract_docx_text(self, file_path):
        doc = Document(file_path)
        filename = os.path.basename(file_path)

        texts = []

        for block in iter_block_items(doc):
            if isinstance(block, Paragraph):
                if block.text.strip():
                    texts.append(block.text.strip())

            elif isinstance(block, Table):
                for row in block.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            texts.append(cell.text.strip())

        return "\n".join(texts)

    # ---------------------------------------------------
    # PDF Extraction
    # ---------------------------------------------------

    def extract_pdf_text(self, file_path):
        if not fitz:
            print("[UltraAssist RAG - genericindexer.extract_pdf_text] PyMuPDF not installed, skipping PDF")
            return ""

        try:
            doc = fitz.open(file_path)
            text = ""

            for page in doc:
                text += page.get_text()

            return text.strip()

        except Exception as e:
            print(f"[UltraAssist RAG - genericindexer.extract_pdf_text] ❌ PDF extraction failed: {e}")
            return ""

    # ---------------------------------------------------
    # File Router
    # ---------------------------------------------------

    def extract_text(self, file_path):
        ext = file_path.lower()

        if ext.endswith(".docx"):
            return self.extract_docx_text(file_path), "docx"

        elif ext.endswith(".pdf"):
            return self.extract_pdf_text(file_path), "pdf"

        else:
            print(f"[UltraAssist RAG - genericindexer.extract_text] ⚠️ Unsupported file type: {file_path}")
            return "", "unknown"

    # ---------------------------------------------------
    # Chunking
    # ---------------------------------------------------

    def chunk_text(self, text, chunk_size=1100, overlap=110):
        words = text.split()
        chunks = []

        step = max(chunk_size - overlap, 1)

        for i in range(0, len(words), step):
            chunk = words[i:i + chunk_size]
            chunks.append(" ".join(chunk))

        return chunks

    # ---------------------------------------------------
    # Main Index Function
    # ---------------------------------------------------

    def index_with_metadata(self, file_path, department, purpose):

        if not department or not purpose:
            raise ValueError("department and purpose are required")

        print(f"\n[UltraAssist RAG - genericindexer.index_with_metadata] 📄 Indexing: {file_path}")
        print(f"[UltraAssist RAG - genericindexer.index_with_metadata] Department: {department}, Purpose: {purpose}")

        if not os.path.exists(file_path):
            print("[UltraAssist RAG - genericindexer.index_with_metadata] ❌ File not found")
            return {"status": "File not found"}

        filename = os.path.basename(file_path)

        # Extract text
        text, doc_type = self.extract_text(file_path)

        if not text:
            print("[UltraAssist RAG - genericindexer.index_with_metadata] ⚠️ No text extracted")
            return {"status": "No text extracted"}

        # Chunking
        chunks = self.chunk_text(text)
        print(f"[UltraAssist RAG - genericindexer.index_with_metadata] Created {len(chunks)} chunks")

        ids = []
        documents = []
        metadatas = []

        document_id = f"{department}_{purpose}_{filename}"

        for i, chunk in enumerate(chunks):

            chunk_id = f"{document_id}_chunk_{i}"

            ids.append(chunk_id)
            documents.append(chunk)

            metadatas.append({
                "source_file": filename,
                "chunk_index": i,
                "type": "generic",
                "document_type": doc_type,
                "department": department,
                "purpose": purpose,
                "subtype": "generic",
                "source_path": file_path,
                "document_id": document_id,
                "indexed_at": datetime.utcnow().isoformat()
            })

        # Embed + store
        embeddings = self.embedder.embed_batch(documents)

        self.vector_store.add(
            self.vector_store.manual_collection,  # reuse same collection
            ids,
            documents,
            embeddings,
            metadatas
        )

        print(f"[UltraAssist RAG - genericindexer.index_with_metadata] ✅ Indexed {len(documents)} chunks\n")

        return {
            "status": "indexed",
            "chunks_indexed": len(documents)
        }