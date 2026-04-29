import re

class HybridRanker:
    """
    Combines semantic similarity with keyword matching and intent recognition
    to rank candidates more effectively.
    """
    
    def extract_keywords(self, text):
        stop_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through',
            'during', 'before', 'after', 'above', 'below', 'between',
            'shall', 'system'
        }

        words = re.findall(r'\b\w+\b', text.lower())
        return [w for w in words if len(w) > 2 and w not in stop_words]

    def keyword_score(self, query, text):
        query_keywords = self.extract_keywords(query)
        text_keywords = self.extract_keywords(text)

        if not query_keywords:
            return 0

        overlap = set(query_keywords) & set(text_keywords)

        # Slightly smoother scoring
        return len(overlap) / (len(query_keywords) ** 0.75)

    def rank(self, query, candidates):
        if not candidates:
            return []

        print(f"[UltraAssist RAG - hybridranker.rank] Ranking {len(candidates)} candidates for query: '{query}'")

        normalized_query = query.replace("*", " ")
        query_upper = normalized_query.upper()

        query_frs_ids = set(
            re.findall(r"UIT-FR-[A-Z]+-\d+(?=[^A-Z0-9-]|$)", query_upper)
        )
        query_heading_ids = set(
            re.findall(r"UIT-FR-[A-Z]+(?=[^A-Z0-9-]|$)", query_upper)
        )

        scored = []
        doc_seen = set()  # 🔥 prevent same doc flooding

        for candidate in candidates:
            semantic_score = candidate.get("semantic_score", 0)
            text = candidate.get("text", "")
            metadata = candidate.get("metadata", {})

            keyword_score = self.keyword_score(query, text)

            # 🔥 Adaptive weighting
            if metadata.get("type") == "frs":
                final_score = semantic_score * 3.0 + keyword_score * 1.0
            else:
                # generic docs → slightly more keyword influence
                final_score = semantic_score * 2.0 + keyword_score * 1.5

            # 🔥 Intent boost (FRS only)
            intent_boost = 0.0
            req_id = (candidate.get("requirement_id") or "").upper()

            if req_id:
                if req_id in query_frs_ids:
                    intent_boost += 2.0
                elif any(req_id.startswith(f"{hid}-") for hid in query_heading_ids):
                    intent_boost += 0.75

            final_score += intent_boost

            # 🔥 Document diversity penalty
            doc_id = metadata.get("document_id")
            if doc_id:
                if doc_id in doc_seen:
                    final_score *= 0.85  # slight penalty
                else:
                    doc_seen.add(doc_id)

            scored.append((final_score, candidate))

            print(
                f"[UltraAssist RAG - hybridranker.rank] {candidate.get('requirement_id', 'GENERIC')}: "
                f"semantic={semantic_score:.3f}, keyword={keyword_score:.3f}, "
                f"boost={intent_boost:.3f}, final={final_score:.3f}"
            )

        scored.sort(key=lambda x: x[0], reverse=True)

        ranked = [candidate for score, candidate in scored]

        if ranked:
            print(
                f"[UltraAssist RAG - hybridranker.rank] 🏆 Top result: "
                f"{ranked[0].get('requirement_id', ranked[0].get('document_id', 'Unknown'))}"
            )

        return ranked