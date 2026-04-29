import re

class ContextAssembler:
    def __init__(self):
        self.max_total_tokens = 150000
        self.max_requirements = 30
        self.max_context_chunks = 8 
        self.chars_per_token = 4

    def estimate_tokens(self, text):
        return len(text) // self.chars_per_token

    def truncate_text(self, text, max_tokens):
        max_chars = max_tokens * self.chars_per_token

        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]
        last_period = truncated.rfind('.')

        if last_period > max_chars * 0.8:
            return truncated[:last_period + 1] + "\n[... truncated ...]"
        else:
            return truncated + "\n[... truncated ...]"

    def select_most_relevant_requirements(self, requirements, query, max_requirements):
        if len(requirements) <= max_requirements:
            return requirements

        query_lower = query.lower()

        scored = []

        for req in requirements:
            score = 0
            text = req.get("text", "").lower()
            req_id = req.get("requirement_id", "").lower()

            for word in query_lower.split():
                if len(word) > 3:
                    score += text.count(word) * 2
                    score += req_id.count(word) * 3

            score += req.get("semantic_score", 0) * 5
            score += req.get("keyword_score", 0) * 3

            scored.append((score, req))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [req for score, req in scored[:max_requirements]]

    def build(self, requirements, context_chunks, query=""):
        """
        Build final context for LLM.
        Works for BOTH:
        - FRS flow (requirements + context)
        - Generic flow (context only)
        """

        print(
            f"[UltraAssist RAG - contextAssembler.build] Building context: "
            f"{len(requirements)} requirements, {len(context_chunks)} context chunks"
        )

        # -------------------------------------------------
        # 🟢 REQUIREMENTS (FRS flow)
        # -------------------------------------------------
        selected_requirements = self.select_most_relevant_requirements(
            requirements,
            query,
            self.max_requirements
        )

        formatted_requirements = []
        requirement_text_combined = ""
        current_tokens = 0

        for i, req in enumerate(selected_requirements):
            req_id = req.get("requirement_id", f"REQ-{i+1}")
            text = req.get("text", "")
            image_context = req.get("image_context", "").strip()

            print(f"[DEBUG] Chunk {i+1} length BEFORE assembler:", len(text))
            print(f"[DEBUG] Chunk {i+1} preview:", text)

            tokens = self.estimate_tokens(text)

            formatted_requirements.append({
                "requirement_id": req_id,
                "text": text,
                "image_context": image_context,
                "image_count": req.get("image_count", 0),
                "metadata": req.get("metadata", {})
            })

            if i == 0:
                requirement_text_combined = text

            current_tokens += tokens

        # -------------------------------------------------
        # CONTEXT CHUNKS (Generic)
        # -------------------------------------------------
        remaining_tokens = self.max_total_tokens - current_tokens

        if formatted_requirements:
            context_budget = min(remaining_tokens * 0.3, 20000)
        else:
            context_budget = min(remaining_tokens * 0.8, 80000)

        formatted_context = []
        context_tokens = 0

        for i, ctx in enumerate(context_chunks[:self.max_context_chunks]):
            text = ctx.get("text", "")
            tokens = self.estimate_tokens(text)

            if context_tokens + tokens > context_budget:
                print(f"[UltraAssist RAG - contextAssembler.build] Context limit reached at chunk {i+1}")
                break

            formatted_context.append({
                "text": text,
                "metadata": ctx.get("metadata", {})
            })

            context_tokens += tokens

        total_tokens = current_tokens + context_tokens

        print(
            f"[UltraAssist RAG - contextAssembler.build] Final: "
            f"{len(formatted_requirements)} requirements, "
            f"{len(formatted_context)} context chunks "
            f"(~{total_tokens} tokens)"
        )

        return {
            "requirements": formatted_requirements,
            "context": formatted_context,   
            "primary_text": requirement_text_combined or (
                formatted_context[0]["text"] if formatted_context else ""
            )
        }