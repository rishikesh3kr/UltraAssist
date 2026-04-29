# rag_service/main.py
import os
import threading
import time
from pathlib import Path
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from frs_indexer import FRSIndexer
from generic_indexer import GenericIndexer
from retriever import Retriever
from datetime import datetime

def update_indexing_status(key, status, details=""):
    indexing_status[key]["status"] = status
    indexing_status[key]["details"] = details
    indexing_status[key]["last_updated"] = datetime.utcnow().isoformat()

app = FastAPI()
indexing_status = {"frs": {"status": "idle", "last_updated": None, "details": ""}, "generic": {"status": "idle", "last_updated": None, "details": ""}}

class RetrieveRequest(BaseModel):
    query: str
    department: str
    purpose: str
    top_k: int = 5
    context_top_k: int = 5

def debug_file_system():
    print("\n" + "="*50)
    print("🔍 DEBUGGING FILE SYSTEM")
    print("="*50)

    cwd = os.getcwd()
    print(f"Current Working Directory: {cwd}")

    data_dir = Path("/app/data")

    print(f"Data directory exists: {data_dir.exists()}")

    if not data_dir.exists():
        return

    for department in data_dir.iterdir():
        if not department.is_dir():
            continue

        print(f"\n📁 Department: {department.name}")

        for purpose in department.iterdir():
            if not purpose.is_dir():
                continue

            print(f"  └── 📂 Purpose: {purpose.name}")

            files = list(purpose.rglob("*"))
            print(f"      Files: {[f.name for f in files if f.is_file()]}")

def auto_index_frs():
    debug_file_system()

    update_indexing_status("frs", "running")
    
    print("\n[UltraAssist RAG - main.auto_index_frs] 🚀 Auto-indexing ALL FRS folders...")

    base_path = Path("/app/data")

    if not base_path.exists():
        print("[UltraAssist RAG - main.auto_index_frs] ❌ Data directory not found")
        update_indexing_status("frs", "error", "Directory not found")
        return

    indexer = FRSIndexer()
    total_indexed = 0

    # Traverse departments
    for department_path in base_path.iterdir():
        if not department_path.is_dir():
            continue

        department = department_path.name

        # Traverse purposes
        for purpose_path in department_path.iterdir():
            if not purpose_path.is_dir():
                continue

            purpose = purpose_path.name

            frs_path = purpose_path / "frs"

            if not frs_path.exists():
                continue

            print(f"\n[UltraAssist RAG - main.auto_index_frs] 📂 Processing: {department}/{purpose}/frs")

            result = indexer.index_folder_with_metadata(
                str(frs_path),
                department,
                purpose
            )

            indexed = result.get("indexed", 0)
            total_indexed += indexed

            print(f"[UltraAssist RAG - main.auto_index_frs] Indexed {indexed} requirements for {department}/{purpose}")

    print(f"\n[UltraAssist RAG - main.auto_index_frs] ✅ FRS auto-index complete. Total indexed: {total_indexed}")

    update_indexing_status("frs", "complete", f"Indexed {total_indexed} requirements")

def auto_index_generic():
    update_indexing_status("generic", "running")

    print("\n[UltraAssist RAG - main.auto_index_generic] 🚀 Auto-indexing ALL GENERIC documents...")

    base_path = Path("/app/data")

    if not base_path.exists():
        print("[UltraAssist RAG - main.auto_index_generic] ❌ Data directory not found")
        update_indexing_status("generic", "error", "Directory not found")
        return

    indexer = GenericIndexer()
    total_indexed = 0

    # Traverse departments
    for department_path in base_path.iterdir():
        if not department_path.is_dir():
            continue

        department = department_path.name

        # Traverse purposes
        for purpose_path in department_path.iterdir():
            if not purpose_path.is_dir():
                continue

            purpose = purpose_path.name

            if purpose == "frs":
                continue

            print(f"\n[UltraAssist RAG - main.auto_index_generic] 📂 Processing: {department}/{purpose}")

            valid_files = []

            for file in purpose_path.rglob("*"):
                if not file.is_file():
                    continue

                if "frs" in file.parts:
                    continue

                if file.suffix.lower() in [".docx", ".pdf", ".txt"]:
                    valid_files.append(file)

            if not valid_files:
                print(f"[UltraAssist RAG - main.auto_index_generic] ⚠ No valid files in {department}/{purpose}")
                continue

            print(f"[UltraAssist RAG - main.auto_index_generic] Found {len(valid_files)} files")

            for file_path in valid_files:
                try:
                    print(f"[UltraAssist RAG - main.auto_index_generic] 📄 Indexing: {file_path.name}")

                    result = indexer.index_with_metadata(
                        str(file_path),
                        department,
                        purpose
                    )

                    update_indexing_status(
                        "generic",
                        "running",
                        f"Processing {file_path.name}"
                    )

                    if result.get("status"):
                        total_indexed += result.get("chunks_indexed", 0)

                except Exception as e:
                    print(f"[UltraAssist RAG - main.auto_index_generic] ❌ Failed to index {file_path.name}: {e}")

    print(f"\n[UltraAssist RAG - main.auto_index_generic] ✅ Generic indexing complete. Total chunks indexed: {total_indexed}")

    update_indexing_status("generic", "complete", f"Indexed {total_indexed} requirements")

def startup_indexing_worker():
    print("\n[UltraAssist RAG - main.startup_indexing_worker] 🚀 Starting background indexing worker...")

    try:
        print("[UltraAssist RAG - main.startup_indexing_worker] FRS indexing started")
        auto_index_frs()
        print("[UltraAssist RAG - main.startup_indexing_worker] ✅ FRS indexing completed")
    except Exception as exc:
        update_indexing_status("frs", "error", str(exc))
        print(f"[UltraAssist RAG - main.startup_indexing_worker] ❌ FRS indexing failed: {exc}")

    try:
        print("[UltraAssist RAG - main.startup_indexing_worker] Generic indexing started")
        auto_index_generic()
        print("[UltraAssist RAG - main.startup_indexing_worker] ✅ Generic indexing completed")
    except Exception as exc:
        update_indexing_status("generic", "error", str(exc))
        print(f"[UltraAssist RAG - main.startup_indexing_worker] ❌ Generic indexing failed: {exc}")

@app.get("/indexing-status")
def get_indexing_status():
    """
    Returns current indexing status for FRS and generic pipelines
    """
    return {
    "status": "ok",
    "data": indexing_status
    }

@app.on_event("startup")
def start_background_indexing():
    print("[UltraAssist RAG - main.start_background_indexing] 🚀 Starting background indexing...")

    update_indexing_status("frs", "starting")
    update_indexing_status("generic", "starting")

    startup_indexing_worker()

    print("[UltraAssist RAG - main.start_background_indexing] Indexing completed.")

def wait_for_generic_collection(department, purpose, timeout_seconds=3):
    """
    Wait for generic collection only when needed.
    """

    if department == "validation" and purpose == "script_authoring":
        return

    if indexing_status.get("generic", {}).get("status") != "running":
        return

    from vector_store import VectorStore

    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        try:
            vs = VectorStore()
            all_generic = vs.get_all(vs.manual_collection)

            if all_generic.get("ids"):
                print("[UltraAssist RAG - main.wait_for_generic_collection] Generic collection ready.")
                return

        except Exception as exc:
            print(f"[UltraAssist RAG - main.wait_for_generic_collection] Generic readiness check failed: {exc}")

        time.sleep(0.5)

    print("[UltraAssist RAG - main.wait_for_generic_collection] Generic collection still not ready; continuing.")

@app.post("/retrieve")
def retrieve(request: RetrieveRequest):
    print("\n==============================")
    print("[UltraAssist RAG - main.retrieve] 🔎 /retrieve called")
    department = (request.department or "").strip().lower()
    purpose = (request.purpose or "").strip().lower()

    print(f"[UltraAssist RAG - main.retrieve] Query: {request.query}")
    print(f"[UltraAssist RAG - main.retrieve] Department: {department}")
    print(f"[UltraAssist RAG - main.retrieve] Purpose: {purpose}")
    print(f"[UltraAssist RAG - main.retrieve] Top K: {request.top_k}")
    print(f"[UltraAssist RAG - main.retrieve] Generic Top K: {request.context_top_k}")
    print("==============================")

    try:
        if not department or not purpose:
            return {"error": "department and purpose are required"}

        if request.context_top_k > 0:
            wait_for_generic_collection(department, purpose)

        retriever = Retriever()

        result = retriever.handle_query(
            request.query,
            department=department,
            purpose=purpose,
            top_k=request.top_k,
            context_top_k=request.context_top_k
        )

        print("[UltraAssist RAG - main.retrieve] ✅ Retrieval successful")
        return result

    except Exception as e:
        print("[UltraAssist RAG - main.retrieve] ❌ Exception occurred:", str(e))
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@app.post("/index/frs")
def index_frs(file_path: str, department: str, purpose: str):
    indexer = FRSIndexer()

    department = department.strip().lower()
    purpose = purpose.strip().lower()

    if not department or not purpose:
        return {"error": "department and purpose are required"}

    if os.path.isdir(file_path):
        return indexer.index_folder_with_metadata(
            file_path,
            department,
            purpose
        )

    return indexer.index_with_metadata(
        file_path,
        department,
        purpose
    )

@app.post("/index/frs/folder")
def index_frs_folder(folder_path: str, department: str, purpose: str):
    indexer = FRSIndexer()

    return indexer.index_folder_with_metadata(
        folder_path,
        department.strip().lower(),
        purpose.strip().lower()
    )

@app.post("/index/generic")
def index_generic(file_path: str, department: str, purpose: str):
    indexer = GenericIndexer()

    department = department.strip().lower()
    purpose = purpose.strip().lower()

    if not department or not purpose:
        return {"error": "department and purpose are required"}

    return indexer.index_with_metadata(
        file_path,
        department,
        purpose
    )

@app.post("/debug/clear_frs")
def clear_frs(department: str = None, purpose: str = None):
    from vector_store import VectorStore
    vs = VectorStore()

    if department and purpose:
        vs.frs_collection.delete(where={
            "department": department.lower(),
            "purpose": purpose.lower()
        })
        return {"status": f"FRS cleared for {department}/{purpose}"}

    vs.frs_collection.delete(where={})
    return {"status": "⚠️ Entire FRS collection cleared"}

@app.post("/debug/clear_generic")
def clear_generic(department: str = None, purpose: str = None):
    from vector_store import VectorStore
    vs = VectorStore()

    if department and purpose:
        vs.manual_collection.delete(where={
            "department": department.lower(),
            "purpose": purpose.lower()
        })
        return {"status": f"Generic cleared for {department}/{purpose}"}

    vs.manual_collection.delete(where={})
    return {"status": "⚠️ Entire generic collection cleared"}

@app.get("/debug/frs_dump")
def debug_frs_dump(department: str = None, purpose: str = None):
    from vector_store import VectorStore
    vs = VectorStore()

    where_filter = None

    if department and purpose:
        where_filter = {
            "$and": [
                {"department": department},
                {"purpose": purpose}
            ]
        }
    elif department:
        where_filter = {"department": department}
    elif purpose:
        where_filter = {"purpose": purpose}

    results = (
        vs.frs_collection.get(where=where_filter)
        if where_filter
        else vs.frs_collection.get()
    )

    return {
        "count": len(results.get("ids", [])),
        "sample_metadata": results.get("metadatas", [])[:5],
        "sample_documents": [
            doc[:500] + "..." if len(doc) > 500 else doc
            for doc in results.get("documents", [])[:2]
        ]
    }

@app.get("/debug/generic_dump")
def debug_generic_dump(department: str = None, purpose: str = None):
    from vector_store import VectorStore
    vs = VectorStore()

    where_filter = None

    if department and purpose:
        where_filter = {
            "$and": [
                {"department": department},
                {"purpose": purpose}
            ]
        }
    elif department:
        where_filter = {"department": department}
    elif purpose:
        where_filter = {"purpose": purpose}

    results = (
        vs.manual_collection.get(where=where_filter)
        if where_filter
        else vs.manual_collection.get()
    )

    return {
        "count": len(results.get("ids", [])),
        "sample_metadata": results.get("metadatas", [])[:5]
    }

@app.api_route("/health", methods=["GET", "HEAD"])
def health(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200)

    return {
        "status": "healthy",
        "indexing": {
            "frs": indexing_status.get("frs", {}).get("status"),
            "generic": indexing_status.get("generic", {}).get("status"),
        }
    }

@app.post("/debug/recreate_frs_collection")
def recreate_frs_collection():
    """
    Recreate entire FRS collection and reindex all FRS data
    """
    try:
        print("\n[UltraAssist RAG - main.recreate_frs_collection] 🔄 Recreating FRS collection...")

        from vector_store import VectorStore
        vs = VectorStore()

        try:
            vs.client.delete_collection("frs_collection")
            print("[UltraAssist RAG - main.recreate_frs_collection] 🗑️ Deleted old FRS collection")
        except Exception as e:
            print(f"[UltraAssist RAG - main.recreate_frs_collection] ℹ️ Could not delete collection: {e}")

        VectorStore._frs_collection = vs.client.get_or_create_collection("frs_collection")
        vs.frs_collection = VectorStore._frs_collection

        print("[UltraAssist RAG - main.recreate_frs_collection] ✅ Created new FRS collection")

        base_path = Path("/app/data")
        indexer = FRSIndexer()

        total_indexed = 0
        total_files = 0

        for department_path in base_path.iterdir():
            if not department_path.is_dir():
                continue

            department = department_path.name

            for purpose_path in department_path.iterdir():
                if not purpose_path.is_dir():
                    continue

                purpose = purpose_path.name
                frs_path = purpose_path / "frs"

                if not frs_path.exists():
                    continue

                print(f"[UltraAssist RAG - main.recreate_frs_collection] 📂 Reindexing {department}/{purpose}/frs")

                result = indexer.index_folder_with_metadata(
                    str(frs_path),
                    department=department,
                    purpose=purpose,
                    force_reindex=True
                )

                total_indexed += result.get("indexed", 0)
                total_files += result.get("files_processed", 0)

        return {
            "status": "collection_recreated",
            "total_indexed": total_indexed,
            "files_processed": total_files
        }

    except Exception as e:
        import traceback
        print(f"[UltraAssist RAG - main.recreate_frs_collection] ❌ Recreation error: {str(e)}")
        traceback.print_exc()
        return {"error": str(e)}
    
@app.post("/debug/recreate_frs_scoped")
def recreate_frs_scoped(department: str, purpose: str):
    from vector_store import VectorStore
    vs = VectorStore()

    vs.frs_collection.delete(where={
        "$and": [
                    {"department": department},
                    {"purpose": purpose}
                ]
    })

    indexer = FRSIndexer()

    frs_path = f"/app/data/{department}/{purpose}/frs"

    result = indexer.index_folder_with_metadata(
        frs_path,
        department=department,
        purpose=purpose,
        force_reindex=True
    )

    return {
        "status": "scoped_recreated",
        "indexed": result.get("indexed", 0)
    }
    
@app.post("/debug/recreate_generic_scoped")
def recreate_generic_scoped(department: str, purpose: str):
    from vector_store import VectorStore
    vs = VectorStore()

    vs.manual_collection.delete(where={
        "$and": [
                    {"department": department},
                    {"purpose": purpose}
                ]
    })

    indexer = GenericIndexer()

    folder_path = f"/app/data/{department}/{purpose}"

    total_indexed = 0

    for file in Path(folder_path).rglob("*"):
        if file.is_file() and file.suffix.lower() in [".docx", ".pdf", ".txt"]:
            result = indexer.index_with_metadata(
                str(file),
                department=department,
                purpose=purpose
            )
            total_indexed += result.get("chunks_indexed", 0)

    return {
        "status": "scoped_generic_recreated",
        "chunks_indexed": total_indexed
    }

@app.get("/debug/list_files")
def list_files(department: str = None, purpose: str = None):
    """
    List all files in data directory with department/purpose grouping
    """

    try:
        base_path = Path("/app/data")

        if not base_path.exists():
            return {"error": "Data directory not found"}

        response = {}

        for dept_path in base_path.iterdir():
            if not dept_path.is_dir():
                continue

            dept_name = dept_path.name.lower()

            if department and dept_name != department.lower():
                continue

            response[dept_name] = {}

            for purpose_path in dept_path.iterdir():
                if not purpose_path.is_dir():
                    continue

                purpose_name = purpose_path.name.lower()

                if purpose and purpose_name != purpose.lower():
                    continue

                files = []

                for file in purpose_path.rglob("*"):
                    if file.is_file():
                        files.append({
                            "name": file.name,
                            "relative_path": str(file.relative_to(base_path)),
                            "type": "frs" if "frs" in file.parts else "generic"
                        })

                response[dept_name][purpose_name] = {
                    "file_count": len(files),
                    "files": files[:20]  # limit output
                }

        return response

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
    
@app.post("/debug/query_generic")
def query_generic(query: str, department: str, purpose: str, top_k: int = 5):
    """
    Debug endpoint to query generic collection with filters
    """

    try:
        from vector_store import VectorStore
        from embedder import EmbeddingManager

        department = department.strip().lower()
        purpose = purpose.strip().lower()

        if not department or not purpose:
            return {"error": "department and purpose are required"}

        print("\n[UltraAssist RAG - main.query_generic] 🔍 Querying generic collection")
        print(f"[UltraAssist RAG - main.query_generic] Query: {query}")
        print(f"[UltraAssist RAG - main.query_generic] Scope: {department}/{purpose}")

        vs = VectorStore()
        embedder = EmbeddingManager()

        query_embedding = embedder.embed(query)

        results = vs.query(
            vs.manual_collection,
            query_embedding,
            top_k,
            where={
                "$and": [
                    {"department": department},
                    {"purpose": purpose}
                ]
            }
        )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        response = []

        for i in range(len(docs)):
            doc_embedding = embedder.embed(docs[i])

            similarity = sum(a * b for a, b in zip(query_embedding, doc_embedding))
            
            response.append({
                "text": docs[i],
                "metadata": metas[i],
                "similarity": similarity
            })

        return {
            "query": query,
            "scope": f"{department}/{purpose}",
            "results_count": len(response),
            "results": response,
            "similarity": similarity
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}