from sentence_transformers import SentenceTransformer
from functools import lru_cache
import threading
import os

class EmbeddingManager:
    _model = None
    _lock = threading.Lock()

    def __init__(self):

        if EmbeddingManager._model is None:

            with EmbeddingManager._lock:

                if EmbeddingManager._model is None:

                    print("[UltraAssist RAG embedder.__init__] Loading embedding model...")

                    device = os.getenv("EMBEDDING_DEVICE", "cpu")

                    EmbeddingManager._model = SentenceTransformer(
                        "sentence-transformers/all-MiniLM-L6-v2",
                        device=device
                    )

                    print(f"[UltraAssist RAG - embedder.__init__] Model loaded on {device}.")

        self.model = EmbeddingManager._model

    # ---------------------------------------------------
    # Cached embedding
    # ---------------------------------------------------

    @lru_cache(maxsize=3000)  
    def _cached_embed(self, text):
        embedding = self.model.encode(text, normalize_embeddings=True)

        if isinstance(embedding, list):
            # case: [[...]]
            if len(embedding) == 1 and isinstance(embedding[0], (list, tuple)):
                embedding = embedding[0]

        elif hasattr(embedding, "shape"):
            # numpy array
            if len(embedding.shape) > 1:
                embedding = embedding[0]

        # Final safety: convert to flat list
        embedding = list(embedding)

        if len(embedding) != 384:
            raise ValueError(f"❌ Invalid embedding dimension: {len(embedding)}")

        return tuple(embedding)

    # ---------------------------------------------------
    # Public embedding API
    # ---------------------------------------------------

    def embed(self, text):
        if not text:
            return []

        if isinstance(text, list):   
            text = text[0]

        normalized = text.strip().lower()

        embedding = self.model.encode(normalized, normalize_embeddings=True)

        if hasattr(embedding, "tolist"):
            embedding = embedding.tolist()

        if isinstance(embedding[0], list):
            embedding = embedding[0]

        return embedding

    # ---------------------------------------------------
    # Batch embedding
    # ---------------------------------------------------

    def embed_batch(self, texts, batch_size=64):

        if not texts:
            return []

        normalized = [t.strip().lower() for t in texts]

        embeddings = self.model.encode(
            normalized,
            batch_size=batch_size,
            show_progress_bar=True,
            normalize_embeddings=True 
        )

        return embeddings.tolist()