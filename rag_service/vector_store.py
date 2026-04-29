import os
import chromadb
from chromadb.config import Settings
import threading

os.environ["ANONYMIZED_TELEMETRY"] = "FALSE"
os.environ["CHROMA_ANONYMIZED_TELEMETRY"] = "FALSE"
os.environ["CHROMA_TELEMETRY"] = "FALSE"

class VectorStore:
    _client = None
    _lock = threading.Lock()   
    _frs_collection = None
    _manual_collection = None

    def __init__(self):
        if VectorStore._client is None:
            with VectorStore._lock:   
                if VectorStore._client is None:
                    print("[UltraAssist RAG - vectorstore.__init__] Initializing Chroma client...")
                    VectorStore._client = chromadb.PersistentClient(
                        path="chunks_db",
                        settings=Settings(anonymized_telemetry=False),
                    )
                    VectorStore._frs_collection = VectorStore._client.get_or_create_collection(
                        name="frs_collection"
                    )
                    VectorStore._manual_collection = VectorStore._client.get_or_create_collection(
                        name="manual_collection"
                    )
                    print("[UltraAssist RAG - vectorstore.__init__] Ready.")

        self.client = VectorStore._client
        self.frs_collection = VectorStore._frs_collection
        self.manual_collection = VectorStore._manual_collection

    def _collection_name(self, collection):
        if isinstance(collection, str):
            return collection
        return getattr(collection, "name", "")

    def _refresh_collection(self, collection):
        name = self._collection_name(collection)
        if not name:
            return collection

        fresh = self.client.get_or_create_collection(name=name)
        if name == "frs_collection":
            self.frs_collection = fresh
            VectorStore._frs_collection = fresh
        elif name == "manual_collection":
            self.manual_collection = fresh
            VectorStore._manual_collection = fresh
        return fresh

    def _is_missing_collection_error(self, exc):
        message = str(exc)
        return "does not exist" in message or "InvalidCollectionException" in message
    
    def add(self, collection, ids, documents, embeddings, metadatas):
        collection = self._refresh_collection(collection)
        collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas
        )
    
    def query(self, collection, embedding, top_k=5, where=None):
        collection = self._refresh_collection(collection)

        query_kwargs = {
            "query_embeddings": [embedding],
            "n_results": top_k
        }

        if where:
            query_kwargs["where"] = where

        try:
            return collection.query(**query_kwargs)
        except Exception as exc:
            if not self._is_missing_collection_error(exc):
                raise

            collection = self._refresh_collection(self._collection_name(collection))
            return collection.query(**query_kwargs)
    
    def get_by_metadata(self, collection, where_filter):
        """Enhanced metadata lookup with error handling"""
        collection = self._refresh_collection(collection)
        try:
            # Try the direct approach first
            result = collection.get(where=where_filter)
            return result
        except Exception as e:
            if self._is_missing_collection_error(e):
                try:
                    collection = self._refresh_collection(self._collection_name(collection))
                    return collection.get(where=where_filter)
                except Exception as retry_exc:
                    print(f"[UltraAssist RAG - vectorstore.get_by_metadata] Metadata retry failed: {retry_exc}")
                    return {"documents": [], "metadatas": [], "ids": []}
            print(f"[UltraAssist RAG - vectorstore.get_by_metadata] ❌ Metadata lookup failed: {e}")
            # Fallback: get all and filter manually
            try:
                all_data = collection.get()
                if not all_data.get("metadatas"):
                    return {"documents": [], "metadatas": [], "ids": []}
                
                # Manual filtering
                filtered_docs = []
                filtered_metas = []
                filtered_ids = []
                
                for i, meta in enumerate(all_data["metadatas"]):
                    # Check if all filter conditions match
                    match = True
                    for key, value in where_filter.items():
                        if meta.get(key) != value:
                            match = False
                            break
                    
                    if match:
                        filtered_docs.append(all_data["documents"][i])
                        filtered_metas.append(meta)
                        filtered_ids.append(all_data["ids"][i])
                
                return {
                    "documents": filtered_docs,
                    "metadatas": filtered_metas, 
                    "ids": filtered_ids
                }
                
            except Exception as e2:
                print(f"[UltraAssist RAG - vectorstore.get_by_metadata] ❌ Fallback also failed: {e2}")
                return {"documents": [], "metadatas": [], "ids": []}
    
    def get_all(self, collection):
        """Get all documents from a collection"""
        collection = self._refresh_collection(collection)
        try:
            return collection.get()
        except Exception as exc:
            if not self._is_missing_collection_error(exc):
                raise
            collection = self._refresh_collection(self._collection_name(collection))
            return collection.get()
