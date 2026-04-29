import re
from embedder import EmbeddingManager
from vector_store import VectorStore

class QueryAnalyzer:
    def __init__(self, vector_store=None):
        self.embedder = EmbeddingManager()
        self.vector_store = vector_store or VectorStore()
        self._heading_cache = {}
    
    def get_all_headings(self, department=None, purpose=None):
        """
        Get unique headings scoped by department and purpose
        """

        cache_key = f"{department}_{purpose}"

        if cache_key not in self._heading_cache:
            try:
                filters = {}
                if department:
                    filters["department"] = department
                if purpose:
                    filters["purpose"] = purpose

                data = self.vector_store.get_by_metadata(
                    self.vector_store.frs_collection,
                    filters
                )

                metas = data.get("metadatas", [])
                if metas and isinstance(metas[0], list):
                    metas = metas[0]

                headings = set()

                for meta in metas:
                    heading = meta.get("heading", "").strip()
                    if heading and heading != "Unknown Section":
                        headings.add(heading)

                self._heading_cache[cache_key] = list(headings)

                print(
                    f"[UltraAssist RAG - queryanalyzer.get_all_headings] Loaded {len(headings)} headings "
                    f"for {department}/{purpose}"
                )

            except Exception as e:
                print(f"[UltraAssist RAG - queryanalyzer.get_all_headings] Error loading headings: {e}")
                self._heading_cache[cache_key] = []

        return self._heading_cache[cache_key]
    
    def find_most_similar_heading(self, query, department=None, purpose=None, top_k=3):
        """
        Find the most semantically similar heading within scoped data
        """

        headings = self.get_all_headings(department, purpose)

        if not headings:
            return []

        try:
            query_embedding = self.embedder.embed(query)[0]
            heading_embeddings = self.embedder.embed_batch(headings)

            similarities = []

            for i, heading_emb in enumerate(heading_embeddings):
                similarity = sum(a * b for a, b in zip(query_embedding, heading_emb))
                similarities.append((similarity, headings[i]))

            similarities.sort(key=lambda x: x[0], reverse=True)

            results = []

            for score, heading in similarities[:top_k]:
                heading_id = heading.split(":")[0].strip() if ":" in heading else heading

                results.append({
                    "heading": heading,
                    "heading_id": heading_id,
                    "similarity_score": score
                })

                print(f"[UltraAssist RAG - queryanalyzer.find_most_similar_heading] Semantic match: '{heading}' (score: {score:.3f})")

            return results

        except Exception as e:
            print(f"[UltraAssist RAG - queryanalyzer.find_most_similar_heading] Error in semantic heading matching: {e}")
            return []
    
    def analyze(self, query, department=None, purpose=None):
        normalized_query = query.replace("*", " ")
        query_upper = normalized_query.upper()

        frs_ids = re.findall(r"UIT-FR-[A-Z]+-\d+(?=[^A-Z0-9-]|$)", query_upper)
        urs_ids = re.findall(r"UIT-UR-[A-Z]+-\d+(?=[^A-Z0-9-]|$)", query_upper)
        heading_ids = re.findall(r"UIT-FR-[A-Z]+(?=[^A-Z0-9-]|$)", query_upper)

        semantic_headings = []

        # 🔥 Only do semantic heading analysis in FRS scope
        if (
            not frs_ids
            and not urs_ids
            and not heading_ids
            and department == "validation"
            and purpose == "script_authoring"
        ):
            semantic_headings = self.find_most_similar_heading(
                query,
                department=department,
                purpose=purpose
            )

        print(f"[UltraAssist RAG - queryanalyzer.] Query: {query}")
        print(f"[UltraAssist RAG - queryanalyzer.] FRS IDs: {frs_ids}")
        print(f"[UltraAssist RAG - queryanalyzer.] URS IDs: {urs_ids}")
        print(f"[UltraAssist RAG - queryanalyzer.] Direct Heading IDs: {heading_ids}")
        print(f"[UltraAssist RAG - queryanalyzer.] Semantic Headings: {len(semantic_headings)}")

        return {
            "frs_ids": frs_ids,
            "urs_ids": urs_ids,
            "heading_ids": heading_ids,
            "semantic_headings": semantic_headings,
            "query_text": query
        }
