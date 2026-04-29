from embedder import EmbeddingManager
from vector_store import VectorStore
from query_analyzer import QueryAnalyzer
from requirement_graph import RequirementGraph
from hybrid_ranker import HybridRanker
from context_assembler import ContextAssembler
import re


class Retriever:

    def __init__(self):

        self.embedder = EmbeddingManager()
        self.vector_store = VectorStore()

        self.query_analyzer = QueryAnalyzer(self.vector_store)
        self.graph = RequirementGraph(self.vector_store)
        self.ranker = HybridRanker()
        self.assembler = ContextAssembler()
        self.manual_similarity_threshold = 0.4
        self.filter = {}

    def build_requirement_result(self,requirement_id,text,metadata=None,semantic_score=0,keyword_score=0):
        metadata = metadata or {}

        return {
            #Core identifiers
            "requirement_id": requirement_id,  # still used for FRS
            "document_id": metadata.get("document_id"),
            "source_file": metadata.get("source_file"),

            #Content
            "text": text,

            #Scoring
            "semantic_score": semantic_score,
            "keyword_score": keyword_score,

            #Metadata
            "metadata": metadata,
            "department": metadata.get("department"),
            "purpose": metadata.get("purpose"),
            "type": metadata.get("type"),
            "subtype": metadata.get("subtype"),

            #Image context (FRS-specific but safe fallback)
            "image_context": metadata.get("image_summary", ""),
            "image_count": metadata.get("image_count", 0),
        }

    # ---------------------------------------------------
    # Semantic Search
    # ---------------------------------------------------

    def semantic_search(self, query, top_k):
        print(f"[UltraAssist RAG - retriever.semantic_search] Performing semantic search for: '{query}'")

        embedding = self.embedder.embed(query)

        # Get more results for better ranking
        search_k = min(top_k * 4, 25)

        results = self.vector_store.query(
            self.vector_store.frs_collection,
            embedding,
            search_k,
            where=self.filter  # ✅ use centralized filter
        )

        docs = results.get("documents", [[]])
        metas = results.get("metadatas", [[]])

        if not docs or not docs[0]:
            print("[UltraAssist RAG - retriever.semantic_search] No semantic results found")
            return []

        documents = docs[0]
        metadatas = metas[0]

        requirements = []

        for i in range(len(documents)):
            metadata = metadatas[i]
            req_id = metadata.get("requirement_id", f"unknown_{i}")
            req_text = documents[i]

            # Compute similarity (can optimize later)
            req_embedding = self.embedder.embed(req_text)
            similarity = sum(a * b for a, b in zip(embedding, req_embedding))

            requirements.append(
                self.build_requirement_result(
                    req_id,
                    req_text,
                    metadata=metadata,
                    semantic_score=similarity,
                    keyword_score=0,
                )
            )

            print(f"[UltraAssist RAG - retriever.semantic_search] Semantic candidate {i+1}: {req_id} (similarity: {similarity:.3f})")

        requirements.sort(key=lambda x: x["semantic_score"], reverse=True)

        return requirements[:top_k]

    # ---------------------------------------------------
    # Section Retrieval
    # ---------------------------------------------------

    def retrieve_by_heading_id(self, heading_id, department=None, purpose=None):
        filter_criteria = {
            "$and": [
                {"heading_id": heading_id},
                {"department": department},
                {"purpose": purpose}
            ]
        }

        data = self.vector_store.get_by_metadata(
            self.vector_store.frs_collection,
            filter_criteria
        )

        docs = data.get("documents", [])
        metas = data.get("metadatas", [])

        if not docs:
            print("[UltraAssist RAG - retriever.retrieve_by_heading_id] No heading-based results found")
            return []

        # Handle nested Chroma format
        if isinstance(docs[0], list):
            docs = docs[0]
            metas = metas[0]

        requirements = []

        for i in range(len(docs)):
            metadata = metas[i]
            req_id = metadata.get("requirement_id", f"unknown_{i}")
            req_text = docs[i]

            requirements.append(
                self.build_requirement_result(
                    req_id,
                    req_text,
                    metadata=metadata,
                    semantic_score=1,   # heading match = high confidence
                    keyword_score=1,
                )
            )

        print(f"[UltraAssist RAG - retriever.retrieve_by_heading_id] Retrieved {len(requirements)} requirements for heading: {heading_id}")

        return requirements

    # ---------------------------------------------------
    # Manual Evidence Helpers
    # ---------------------------------------------------

    def build_contextual_query(self, user_query, ranked_requirements, max_requirements=3):
        """
        Build enriched query using top retrieved structured results (FRS if available).
        Falls back to raw query if no structured context exists.
        """

        context_chunks = []

        for req in ranked_requirements[:max_requirements]:
            text = req.get("text", "").strip()
            if text:
                context_chunks.append(text)

        # If no structured context, return original query
        if not context_chunks:
            return user_query.strip()

        combined = user_query + "\n\n" + "\n\n".join(context_chunks)

        return combined.strip()

    def split_sentences(self, text):
        raw_sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
        sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 10]
        return sentences

    def extract_keywords(self, text):
        stop_words = {
        "the", "and", "or", "but", "for", "with", "from", "that", "this",
        "are", "was", "were", "have", "has", "had", "shall", "must", "system"
        }
        words = re.findall(r"\b[a-zA-Z0-9_-]+\b", text.lower())
        return {w for w in words if len(w) > 2 and w not in stop_words}

    def extract_relevant_evidence(self, chunk_text, contextual_query_text, max_sentences=4):
        """
        Extract most relevant sentences from a chunk using hybrid scoring
        (semantic similarity + keyword overlap)
        """

        sentences = self.split_sentences(chunk_text)

        if not sentences:
            return chunk_text.strip()

        # Compute query embedding once
        query_embedding = self.embedder.embed(contextual_query_text)
        query_keywords = self.extract_keywords(contextual_query_text)

        scored = []

        for idx, sentence in enumerate(sentences):
            sent_embedding = self.embedder.embed(sentence)

            # Semantic similarity
            semantic_score = sum(a * b for a, b in zip(query_embedding, sent_embedding))

            # Keyword overlap
            sent_keywords = self.extract_keywords(sentence)
            overlap = len(query_keywords & sent_keywords)
            keyword_score = overlap / max(len(query_keywords), 1)

            # Hybrid scoring
            final_score = (semantic_score * 2.0) + keyword_score

            scored.append((final_score, idx, sentence))

        # Sort by relevance
        scored.sort(key=lambda x: x[0], reverse=True)

        # Pick top N but preserve original order
        top = scored[:max_sentences]
        top_sorted_by_order = sorted(top, key=lambda x: x[1])

        evidence = " ".join([s for _, _, s in top_sorted_by_order]).strip()

        return evidence if evidence else chunk_text.strip()

    # ---------------------------------------------------
    # Manual Context Retrieval
    # ---------------------------------------------------

    def retrieve_context(self, contextual_query_text, top_k=5, similarity_threshold=None):
        """
        Retrieve relevant contextual chunks from generic collection using hybrid filtering.
        """
        print("[UltraAssist RAG - retriever.retrieve_context] QUERY:", contextual_query_text[:100])
        threshold = self.manual_similarity_threshold if similarity_threshold is None else similarity_threshold

        query_embedding = self.embedder.embed(contextual_query_text)
        search_k = max(top_k * 3, top_k)

        results = self.vector_store.query(
            self.vector_store.manual_collection,  # generic collection
            query_embedding,
            search_k,
            where=self.filter
        )

        print("[UltraAssist RAG - retriever.retrieve_context] RAW DOCS:", len(results.get("documents", [[]])[0]))

        docs = results.get("documents", [[]])
        metas = results.get("metadatas", [[]])

        if not docs or not docs[0]:
            print("[UltraAssist RAG - retriever.retrieve_context] No contextual results found")
            return []

        documents = docs[0]
        metadatas = metas[0]

        candidates = []
        fallback_candidates = []

        for i in range(len(documents)):
            chunk_text = documents[i]
            chunk_meta = metadatas[i]

            # Compute similarity
            chunk_embedding = self.embedder.embed(chunk_text)
            similarity = sum(a * b for a, b in zip(query_embedding, chunk_embedding))

            item = {
                "text": chunk_text,
                "metadata": {
                    **chunk_meta,
                    "similarity": similarity,
                    "is_compressed_evidence": True
                }
            }

            fallback_candidates.append(item)

            if similarity >= threshold:
                candidates.append(item)

        # Sort by similarity
        candidates.sort(key=lambda x: x["metadata"].get("similarity", 0), reverse=True)
        selected = candidates[:top_k]

        # Fallback if nothing meets threshold
        if not selected and fallback_candidates:
            fallback_candidates.sort(
                key=lambda x: x["metadata"].get("similarity", 0),
                reverse=True
            )
            selected = fallback_candidates[:top_k]

            print(
                f"[UltraAssist RAG - retriever.retrieve_context] Context fallback selected: {len(selected)} "
                f"(threshold={threshold}, requested_top_k={top_k})"
            )

            for item in selected:
                item["metadata"]["selected_without_threshold"] = True

        print(
            f"[UltraAssist RAG - retriever.retrieve_context] Context selected: {len(selected)} "
            f"(threshold={threshold}, requested_top_k={top_k})"
        )

        return selected

    # ---------------------------------------------------
    # Hybrid Retrieval
    # ---------------------------------------------------

    def hybrid_retrieve(self, query, top_k):
        """
        Hybrid retrieval combining semantic search with lightweight deduplication.
        """

        semantic_results = self.semantic_search(query, top_k * 2)

        merged = {}

        for r in semantic_results:
            rid = r.get("requirement_id")

            if rid not in merged:
                merged[rid] = r  # ✅ keep full object (with metadata)

        results = list(merged.values())

        # Optional: sort again by semantic score
        results.sort(key=lambda x: x.get("semantic_score", 0), reverse=True)

        return results[:top_k]

    # ---------------------------------------------------
    # Main Query Handler
    # ---------------------------------------------------

    def handle_query(self, query, department=None, purpose=None, top_k=5, context_top_k=5):
        print(f"\n[UltraAssist RAG - retriever.handle_query] Processing query: '{query}'")

        if department and purpose:
            self.filter = {
                "$and": [
                    {"department": department},
                    {"purpose": purpose}
                ]
            }
        elif department:
            self.filter = {"department": department}
        elif purpose:
            self.filter = {"purpose": purpose}
        else:
            self.filter = {}

        print(f"[UltraAssist RAG - retriever.handle_query] Active filter: {self.filter}")

        if department == "validation" and purpose == "script_authoring":
            analysis = self.query_analyzer.analyze(query, department, purpose)
        else:
            analysis = {
                "frs_ids": [],
                "urs_ids": [],
                "heading_ids": [],
                "semantic_headings": [],
                "query_text": query
            }
        print(f"[UltraAssist RAG - retriever.handle_query] Analysis result: {analysis}")

        # =====================================================
        # 🔵 GENERIC FLOW (Everything except validation/script_authoring)
        # =====================================================
        if not (department == "validation" and purpose == "script_authoring"):
            print("[UltraAssist RAG - retriever.handle_query] Using GENERIC retrieval flow")

            contextual_query = query.strip()

            print("[UltraAssist RAG - retriever.handle_query] Filter:", self.filter)

            context = self.retrieve_context(
                contextual_query,
                top_k=context_top_k
            )

            return self.assembler.build([], context, query)

        # =====================================================
        # 🟢 FRS FLOW (ONLY validation/script_authoring)
        # =====================================================
        print("[UltraAssist RAG - retriever.handle_query] Using FRS retrieval flow")

        requirements = []

        # -----------------------------
        # Priority 1: Direct FRS ID
        # -----------------------------
        if analysis["frs_ids"]:
            frs_id = analysis["frs_ids"][0]
            print(f"[UltraAssist RAG - retriever.handle_query] Direct FRS ID lookup: {frs_id}")

            frs = self.graph.get_frs(frs_id, department, purpose)

            if frs and frs.get("documents"):
                meta = (frs.get("metadatas") or [{}])[0]

                if (
                    meta.get("department") != department or
                    meta.get("purpose") != purpose
                ):
                    print("[UltraAssist RAG - retriever.handle_query] ❌ FRS filtered out due to mismatch")
                    frs = None

            if frs and frs.get("documents"):
                requirements = [
                    self.build_requirement_result(
                        frs_id,
                        frs["documents"][0],
                        metadata=(frs.get("metadatas") or [{}])[0],
                        semantic_score=1,
                        keyword_score=1,
                    )
                ]
            else:
                print(f"[UltraAssist RAG - retriever.handle_query] FRS not found: {frs_id}")

        # -----------------------------
        # Priority 2: URS ID
        # -----------------------------
        elif analysis["urs_ids"]:
            print(f"[UltraAssist RAG - retriever.handle_query] Direct URS lookup: {analysis['urs_ids'][0]}")

            data = self.graph.get_by_urs(analysis["urs_ids"][0], department, purpose)

            for i in range(len(data.get("documents", []))):
                meta = data["metadatas"][i]

                if (
                    meta.get("department") != department or
                    meta.get("purpose") != purpose
                ):
                    continue

                requirements.append(
                    self.build_requirement_result(
                        meta.get("requirement_id"),
                        data["documents"][i],
                        metadata=meta,
                        semantic_score=1,
                        keyword_score=1,
                    )
                )

        # -----------------------------
        # Priority 3: Heading
        # -----------------------------
        elif analysis["heading_ids"]:
            print(f"[UltraAssist RAG - retriever.handle_query] Direct heading lookup: {analysis['heading_ids'][0]}")
            requirements = self.retrieve_by_heading_id(analysis["heading_ids"][0], department, purpose)

        # -----------------------------
        # Priority 4: Semantic
        # -----------------------------
        else:
            print(f"[UltraAssist RAG - retriever.handle_query] Starting semantic search for: '{query}'")

            semantic_candidates = self.semantic_search(query, top_k * 2)

            print(f"[UltraAssist RAG - retriever.handle_query] Semantic search found {len(semantic_candidates)} candidates")

            semantic_quality_threshold = 0.4

            high_quality = [
                r for r in semantic_candidates
                if r.get("semantic_score", 0) > semantic_quality_threshold
            ]

            if high_quality:
                requirements = high_quality[:top_k]
            else:
                requirements = semantic_candidates[:top_k] if semantic_candidates else []

        print(f"[UltraAssist RAG - retriever.handle_query] Final requirements: {len(requirements)}")

        # -----------------------------
        # Ranking + Context Building
        # -----------------------------
        ranked_requirements = self.ranker.rank(query, requirements)

        contextual_query = self.build_contextual_query(
            query,
            ranked_requirements
        )

        context = self.retrieve_context(
            contextual_query,
            top_k=context_top_k
        )

        return self.assembler.build(ranked_requirements, context, query)