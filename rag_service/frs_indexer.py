import json

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from datetime import datetime
from embedder import EmbeddingManager
from image_analyzer import ImageAnalyzer
from vector_store import VectorStore
import os
import re

def iter_block_items(parent):
    """
    Iterate through paragraphs and tables in document order.
    """
    for child in parent.element.body.iterchildren():
        if child.tag.endswith("p"):
            yield Paragraph(child, parent)
        elif child.tag.endswith("tbl"):
            yield Table(child, parent)

class FRSIndexer:
    def __init__(self):
        print("[UltraAssist RAG - frsindexer.__init__] Initializing...")
        self.embedder = EmbeddingManager()
        self.image_analyzer = ImageAnalyzer()
        try:
            self.vector_store = VectorStore()
        except Exception as e:
            print("[UltraAssist RAG - frsindexer.__init__] VectorStore init failed:", e)
        self._image_summary_cache = {}
        print("[UltraAssist RAG - frsindexer.__init__] Ready.")
    
    def normalize_heading(self, text):
        # Remove numbering like "2.1.1.6"
        text = re.sub(r"^\d+(\.\d+)*\s*", "", text)
        return text.strip()
    
    def extract_heading_id(self, heading):
        if ":" in heading:
            return heading.split(":")[0].strip()
        return heading
    
    def clean_requirement_id(self, req_id):
        """Clean requirement ID by removing newlines and extra spaces"""
        if not req_id:
            return ""
        return re.sub(r'\s+', ' ', req_id.strip())

    def extract_images_from_container(self, container):
        images = []
        rels = getattr(container.part, "related_parts", {})
        paragraphs = [container] if isinstance(container, Paragraph) else getattr(container, "paragraphs", [])

        for paragraph in paragraphs:
            for run in paragraph.runs:
                blips = run._element.xpath(
                    ".//*[local-name()='blip' and namespace-uri()='http://schemas.openxmlformats.org/drawingml/2006/main']"
                )
                for blip in blips:
                    embed = blip.get(
                        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
                    )
                    if not embed or embed not in rels:
                        continue
                    image_part = rels[embed]
                    images.append({
                        "relationship_id": embed,
                        "filename": os.path.basename(str(getattr(image_part, "partname", "image"))),
                        "content_type": getattr(image_part, "content_type", ""),
                        "bytes": image_part.blob,
                    })

        unique = {}
        for image in images:
            unique[image["relationship_id"]] = image
        return list(unique.values())

    def extract_images_from_run(self, run, rels):
        images = []
        blips = run._element.xpath(
            ".//*[local-name()='blip' and namespace-uri()='http://schemas.openxmlformats.org/drawingml/2006/main']"
        )
        for blip in blips:
            embed = blip.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
            )
            if not embed or embed not in rels:
                continue
            image_part = rels[embed]
            images.append({
                "relationship_id": embed,
                "filename": os.path.basename(str(getattr(image_part, "partname", "image"))),
                "content_type": getattr(image_part, "content_type", ""),
                "bytes": image_part.blob,
            })
        return images

    def summarize_images(self, images, filename, frs_id, heading, department, purpose):
        summaries = []
        for idx, image in enumerate(images, start=1):
            cache_key = image["relationship_id"]
            analysis = self._image_summary_cache.get(cache_key)
            if analysis is None:
                analysis = self.image_analyzer.summarize_image(
                    image["bytes"],
                    file_name=filename,
                    frs_id=frs_id,
                    heading=heading,
                    department=department,
                    purpose=purpose
                )
                self._image_summary_cache[cache_key] = analysis
            summaries.append({
                "image_index": idx,
                "filename": image["filename"],
                "content_type": image["content_type"],
                "base32": self.image_analyzer.encode_base32(image["bytes"]),
                "summary": analysis.get("summary", ""),
                "analysis_status": analysis.get("status", "unknown"),
            })
        return summaries

    def build_image_context_text(self, image_summaries):
        lines = []
        for image in image_summaries:
            summary = image.get("summary", "").strip()
            if not summary:
                continue
            lines.append(
                f"Image {image['image_index']} ({image.get('filename', 'embedded image')}):\n{summary}"
            )
        return "\n\n".join(lines)

    def build_inline_paragraph_content(self, paragraph, filename, frs_id, heading, department, purpose):
        parts = []
        current_text = []
        image_summaries = []
        rels = getattr(paragraph.part, "related_parts", {})

        for run in paragraph.runs:
            if run.text:
                current_text.append(run.text)

            run_images = self.extract_images_from_run(run, rels)
            if not run_images:
                continue

            text_chunk = "".join(current_text).strip()
            if text_chunk:
                parts.append(text_chunk)
                current_text = []

            summaries = self.summarize_images(
                run_images,
                filename=filename,
                frs_id=frs_id,
                heading=heading,
                department=department,
                purpose=purpose
            )
            image_summaries.extend(summaries)
            image_text = self.build_image_context_text(summaries)
            if image_text:
                parts.append("Diagram Context:\n" + image_text)

        trailing_text = "".join(current_text).strip()
        if trailing_text:
            parts.append(trailing_text)

        if not parts and paragraph.text.strip():
            parts.append(paragraph.text.strip())

        return "\n".join(parts).strip(), image_summaries

    def build_inline_cell_content(self, cell, filename, frs_id, heading, department, purpose):
        paragraph_texts = []
        image_summaries = []

        for paragraph in cell.paragraphs:
            paragraph_text, paragraph_images = self.build_inline_paragraph_content(
                paragraph,
                filename=filename,
                frs_id=frs_id,
                heading=heading,
                department=department,
                purpose=purpose
            )
            if paragraph_text:
                paragraph_texts.append(paragraph_text)
            image_summaries.extend(paragraph_images)

        if not paragraph_texts and cell.text.strip():
            paragraph_texts.append(cell.text.strip())

        return "\n".join(paragraph_texts).strip(), image_summaries

    def build_requirement_document(self, record):
        parts = [
            f"Section: {record['heading']}",
            f"URS ID: {record['urs_id']}",
            f"FRS ID: {record['frs_id']}",
            "Requirement:",
            record["description"],
        ]
        return "\n".join(parts)

    def get_existing_requirement_ids(self, department, purpose):
        """
        Get all existing requirement IDs scoped to a specific department and purpose
        """
        try:
            results = self.vector_store.get_by_metadata(
            self.vector_store.frs_collection,
            {
                "$and": [
                    {"department": department},
                    {"purpose": purpose}
                ]
            }
            )

            ids = results.get("ids", [])
            return set(ids) if ids else set()

        except Exception as exc:
            print(f"[UltraAssist RAG - frsindexer.get_existing_requirement_ids] Failed to preload existing IDs for "
                f"{department}/{purpose}: {exc}")
            return set()


    def index_folder_with_metadata(self, folder_path, department, purpose, force_reindex=False):
        print(f"\n[UltraAssist RAG - frsindexer.index_folder_with_metadata] Indexing folder: {folder_path}")
        if not os.path.exists(folder_path):
            return {"status": "Folder not found", "indexed": 0}

        files = sorted(
            os.path.join(folder_path, file_name)
            for file_name in os.listdir(folder_path)
            if file_name.lower().endswith(".docx")
        )
        if not files:
            return {"status": "No DOCX files found", "indexed": 0}

        indexed_total = 0
        file_results = []
        for file_path in files:
            result = self.index_with_metadata(file_path, department, purpose, force_reindex=force_reindex)
            file_results.append({"file": os.path.basename(file_path), **result})
            indexed_total += result.get("indexed", 0)

        return {
            "status": "complete",
            "indexed": indexed_total,
            "files_processed": len(files),
            "file_results": file_results,
        }
    
    def index_with_metadata(self, file_path, department, purpose, force_reindex=False):
        if not department or not purpose:
            raise ValueError("department and purpose are required for indexing")
        
        print(f"\n[UltraAssist RAG - frsindexer.index_with_metadata] 📄 Indexing file: {file_path}")
        print(f"[UltraAssist RAG - frsindexer.index_with_metadata] Department: {department}, Purpose: {purpose}")
        if not os.path.exists(file_path):
            print("[UltraAssist RAG - frsindexer.index_with_metadata] ❌ File not found.")
            return {"status": "File not found"}
        
        doc = Document(file_path)
        filename = os.path.basename(file_path)
        current_heading = "Unknown Section"
        requirement_records = []
        active_requirement_record = None
        
        existing_requirement_ids = (
            set() if force_reindex 
            else self.get_existing_requirement_ids(department, purpose)
        )
        
        # Parse document blocks
        for block in iter_block_items(doc):
            # Detect heading
            if isinstance(block, Paragraph):
                text = block.text.strip()
                style = (block.style.name or "").lower()
                
                # More flexible heading detection
                is_heading = (
                    len(text) >= 3 and (
                        "heading" in style or
                        text[0].isdigit() or
                        re.match(r"^\d+(\.\d+)*\s", text)
                    )
                )
                
                if is_heading:
                    cleaned = self.normalize_heading(text)
                    # Accept any heading that mentions UIT-FR or archival concepts
                    if ("uit-fr" in cleaned.lower() or 
                        "archiv" in cleaned.lower() or
                        "data" in cleaned.lower()):
                        current_heading = cleaned
                        active_requirement_record = None
                        print(f"[UltraAssist RAG - frsindexer.index_with_metadata] 📍 Found heading: {current_heading}")
                elif active_requirement_record:
                    paragraph_content, paragraph_images = self.build_inline_paragraph_content(
                        block,
                        filename=filename,
                        frs_id=active_requirement_record["frs_id"],
                        heading=current_heading,
                        department=department,
                        purpose=purpose
                    )
                    if paragraph_content:
                        active_requirement_record["description"] = (
                            active_requirement_record["description"].rstrip()
                            + "\n"
                            + paragraph_content
                        ).strip()
                    if paragraph_images:
                        active_requirement_record["image_summaries"].extend(paragraph_images)

            # Process requirement tables
            elif isinstance(block, Table):
                headers = [c.text.strip().lower() for c in block.rows[0].cells]
                print(f"[UltraAssist RAG - frsindexer.index_with_metadata] 📊 Table headers: {headers}")
                
                frs_col = None
                urs_col = None  
                desc_col = None
                
                for i, header in enumerate(headers):
                    if "frs" in header.lower():
                        frs_col = i
                    elif "urs" in header.lower():
                        urs_col = i
                    elif "description" in header.lower():
                        desc_col = i
                
                print(f"[UltraAssist RAG - frsindexer.index_with_metadata] Column mapping - FRS: {frs_col}, URS: {urs_col}, Desc: {desc_col}")
                
                if frs_col is None or desc_col is None:
                    continue
                
                for row in block.rows[1:]:
                    cells = [c.text.strip() for c in row.cells]
                    if len(cells) <= max(frs_col, desc_col):
                        continue
                    
                    # Clean the IDs to remove newlines and extra spaces
                    frs_id = self.clean_requirement_id(cells[frs_col])
                    description_cell = row.cells[desc_col]
                    description, inline_image_summaries = self.build_inline_cell_content(
                        description_cell,
                        filename=filename,
                        frs_id=frs_id,
                        heading=current_heading,
                        department=department,
                        purpose=purpose
                    )
                    if not description:
                        description = cells[desc_col].strip()
                    urs_id = (
                        self.clean_requirement_id(cells[urs_col])
                        if urs_col is not None and urs_col < len(cells)
                        else ""
                    )
                    
                    if not frs_id or not description:
                        continue
                    
                    # Additional validation for proper FRS ID format
                    if not re.match(r"UIT-FR-[A-Z]+-\d+", frs_id):
                        print(f"[UltraAssist RAG - frsindexer.index_with_metadata] ⚠️ Skipping invalid FRS ID: '{frs_id}'")
                        continue
                    
                    if not force_reindex and frs_id in existing_requirement_ids:
                        print(f"[UltraAssist RAG - frsindexer.index_with_metadata] Skipping existing early: {frs_id}")
                        continue

                    record = {
                        "heading": current_heading,
                        "urs_id": urs_id,
                        "frs_id": frs_id,
                        "description": description,
                        "image_summaries": inline_image_summaries,
                    }
                    requirement_records.append(record)
                    active_requirement_record = record
        
        print(f"[UltraAssist RAG - frsindexer.index_with_metadata] 🔍 Extracted {len(requirement_records)} raw requirements")
        
        if not requirement_records:
            return {"status": "No requirements found", "indexed": 0}
        
        # Remove duplicates
        unique = {}
        for r in requirement_records:
            if r["frs_id"] not in unique:
                unique[r["frs_id"]] = r
        
        print(f"[UltraAssist RAG - frsindexer.index_with_metadata] Unique requirements: {len(unique)}")
        
        documents = []
        ids = []
        metadatas = []
        embedding_texts = []
        
        # Build embedding records
        for frs_id, record in unique.items():
            
            heading = record["heading"]
            heading_id = self.extract_heading_id(heading)
            
            embedding_text = self.build_requirement_document(record)
            image_context = self.build_image_context_text(record.get("image_summaries", []))
            
            embedding_texts.append(embedding_text)
            documents.append(embedding_text)
            ids.append(frs_id)
            metadatas.append({
                "requirement_id": frs_id,
                "urs_id": record["urs_id"],
                "heading": heading,
                "heading_id": heading_id,
                "source_file": filename,
                "type": "frs",
                "department": department,
                "purpose": purpose,
                "subtype": "requirement_table",
                "source_path": file_path,
                "has_image_context": bool(image_context),
                "image_summary": image_context[:4000],
                "image_count": len(record.get("image_summaries", [])),
                "image_payloads_base32": json.dumps(
                    [image["base32"] for image in record.get("image_summaries", [])]
                ),
                "indexed_at": datetime.utcnow().isoformat()
            })
        
        if not embedding_texts:
            print("[UltraAssist RAG - frsindexer.index_with_metadata] ✅ All requirements already indexed")
            return {"status": "no_new_data", "indexed": 0}
        
        print(f"[UltraAssist RAG - frsindexer.index_with_metadata] Generating embeddings for {len(embedding_texts)} requirements...")
        embeddings = self.embedder.embed_batch(embedding_texts)
        
        self.vector_store.add(
            self.vector_store.frs_collection,
            ids,
            documents,
            embeddings,
            metadatas
        )
        
        print(f"[UltraAssist RAG - frsindexer.index_with_metadata] ✅ Indexed {len(documents)} requirements")
        
        return {
            "status": "complete",
            "indexed": len(documents)
        }
