class RequirementGraph:
    def __init__(self, vector_store):
        self.vector_store = vector_store
    
    def get_frs(self, frs_id, department=None, purpose=None):
        print(f"[UltraAssist RAG - requirementgraph.get_frs] Looking up FRS: {frs_id}")

        try:
            filters = {"requirement_id": frs_id}

            if department:
                filters["department"] = department
            if purpose:
                filters["purpose"] = purpose

            result = self.vector_store.get_by_metadata(
                self.vector_store.frs_collection,
                filters
            )

            print(
                f"[UltraAssist RAG - requirementgraph.get_frs] Found {len(result.get('documents', []))} "
                f"documents for {frs_id}"
            )

            return result

        except Exception as e:
            print(f"[UltraAssist RAG - requirementgraph.get_frs] ❌ FRS lookup failed for {frs_id}: {e}")
            return {"documents": [], "metadatas": [], "ids": []}
    
    def get_by_urs(self, urs_id, department=None, purpose=None):
        print(f"[UltraAssist RAG - requirementgraph.get_by_urs] Looking up URS: {urs_id}")

        try:
            filters = {"urs_id": urs_id}

            if department:
                filters["department"] = department
            if purpose:
                filters["purpose"] = purpose

            result = self.vector_store.get_by_metadata(
                self.vector_store.frs_collection,
                filters
            )

            print(
                f"[UltraAssist RAG - requirementgraph.get_by_urs] Found {len(result.get('documents', []))} "
                f"documents for URS {urs_id}"
            )

            return result

        except Exception as e:
            print(f"[UltraAssist RAG - requirementgraph.get_by_urs] ❌ URS lookup failed for {urs_id}: {e}")
            return {"documents": [], "metadatas": [], "ids": []}
    
    def get_by_heading(self, heading_id, department=None, purpose=None):
        print(f"[UltraAssist RAG - requirementgraph.get_by_heading] Looking up heading: {heading_id}")

        try:
            filters = {"heading_id": heading_id}

            if department:
                filters["department"] = department
            if purpose:
                filters["purpose"] = purpose

            result = self.vector_store.get_by_metadata(
                self.vector_store.frs_collection,
                filters
            )

            docs = result.get("documents", [])
            metas = result.get("metadatas", [])

            if docs and isinstance(docs[0], list):
                docs = docs[0]
                metas = metas[0]

            matched = []

            for i in range(len(docs)):
                matched.append({
                    "requirement_id": metas[i]["requirement_id"],
                    "text": docs[i],
                    "metadata": metas[i]
                })

            print(f"[UltraAssist RAG - requirementgraph.get_by_heading] Found {len(matched)} documents for heading {heading_id}")

            return matched

        except Exception as e:
            print(f"[UltraAssist RAG - requirementgraph.get_by_heading] ❌ Heading lookup failed: {e}")
            return []