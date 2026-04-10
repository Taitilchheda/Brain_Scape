"""
Brain_Scape — RAG Engine

Retrieval-Augmented Generation over a vector database of clinical literature.
Forces the LLM to ground its claims in retrieved literature and cite sources.

Why RAG and not fine-tuning alone:
Fine-tuned models hallucinate clinical facts confidently. RAG forces the LLM
to ground its claims in retrieved literature and cite its sources. Clinicians
can follow a citation to the original paper — they cannot audit a fine-tuned
weight matrix.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RAGEngine:
    """
    Medical RAG system over clinical literature.

    Vector store (Pinecone/Weaviate) of peer-reviewed neurology and
    radiology papers, AHA/WHO/ESO guidelines, and case databases.
    Embedded with BioBERT/PubMedBERT for medically-accurate retrieval.
    """

    def __init__(
        self,
        vector_store: str = "weaviate",
        weaviate_url: str = "http://localhost:8080",
        pinecone_api_key: Optional[str] = None,
        pinecone_environment: Optional[str] = None,
        embedding_model: str = "pubmedbert",
        embedding_dimension: int = 768,
        top_k: int = 5,
        score_threshold: float = 0.7,
    ):
        self.vector_store = vector_store
        self.weaviate_url = weaviate_url
        self.pinecone_api_key = pinecone_api_key
        self.pinecone_environment = pinecone_environment
        self.embedding_model = embedding_model
        self.embedding_dimension = embedding_dimension
        self.top_k = top_k
        self.score_threshold = score_threshold
        self._client = None
        self._embedder = None

    def _get_client(self):
        """Lazy-initialize the vector store client."""
        if self._client is not None:
            return self._client

        if self.vector_store == "weaviate":
            import weaviate
            self._client = weaviate.Client(self.weaviate_url)
        elif self.vector_store == "pinecone":
            import pinecone
            pinecone.init(api_key=self.pinecone_api_key, environment=self.pinecone_environment)
            self._client = pinecone
        else:
            raise ValueError(f"Unknown vector store: {self.vector_store}")

        return self._client

    def _get_embedder(self):
        """Lazy-initialize the embedding model."""
        if self._embedder is not None:
            return self._embedder

        try:
            from sentence_transformers import SentenceTransformer
            model_name = {
                "pubmedbert": "neuml/pubmedbert-base-embeddings",
                "biobert": "dmis-lab/biobert-v1.1",
            }.get(self.embedding_model, self.embedding_model)
            self._embedder = SentenceTransformer(model_name)
        except ImportError:
            logger.warning("sentence-transformers not available. Using mock embeddings.")
            self._embedder = None

        return self._embedder

    def embed_text(self, text: str) -> list[float]:
        """Embed text using the configured embedding model."""
        embedder = self._get_embedder()
        if embedder is not None:
            return embedder.encode(text).tolist()
        else:
            # Mock embedding for development
            import hashlib
            hash_val = hashlib.sha256(text.encode()).hexdigest()
            return [float(int(hash_val[i:i+8], 16) % 1000) / 1000
                    for i in range(0, min(len(hash_val), self.embedding_dimension * 8), 8)][:self.embedding_dimension]

    def index_documents(self, documents: list[dict]) -> int:
        """
        Index clinical literature documents into the vector store.

        Args:
            documents: List of dicts with keys:
                - "text": document text
                - "title": paper title
                - "source": publication source
                - "year": publication year
                - "doi": DOI if available

        Returns:
            Number of documents indexed.
        """
        client = self._get_client()
        indexed = 0

        for doc in documents:
            text = doc.get("text", "")
            if not text:
                continue

            # Chunk the document
            chunks = self._chunk_text(text, chunk_size=512, overlap=64)

            for i, chunk in enumerate(chunks):
                embedding = self.embed_text(chunk)

                metadata = {
                    "title": doc.get("title", ""),
                    "source": doc.get("source", ""),
                    "year": doc.get("year", ""),
                    "doi": doc.get("doi", ""),
                    "chunk_index": i,
                    "text": chunk,
                }

                if self.vector_store == "weaviate":
                    client.data_object.create(
                        class_name="ClinicalLiterature",
                        data_object=metadata,
                        vector=embedding,
                    )
                elif self.vector_store == "pinecone":
                    import uuid
                    client.Index("brainscape-literature").upsert([
                        (str(uuid.uuid4()), embedding, metadata)
                    ])

                indexed += 1

        logger.info(f"Indexed {indexed} chunks from {len(documents)} documents.")
        return indexed

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_dict: Optional[dict] = None,
    ) -> list[dict]:
        """
        Retrieve relevant clinical literature for a query.

        Args:
            query: Search query (e.g., "hippocampal damage anterograde amnesia").
            top_k: Number of results (default from config).
            filter_dict: Optional metadata filters.

        Returns:
            List of retrieved chunks with scores and citations.
        """
        k = top_k or self.top_k
        query_embedding = self.embed_text(query)

        results = []

        try:
            if self.vector_store == "weaviate":
                client = self._get_client()
                response = (
                    client.query
                    .get("ClinicalLiterature", ["text", "title", "source", "year", "doi"])
                    .with_near_vector({"vector": query_embedding})
                    .with_limit(k)
                    .with_additional(["certainty"])
                    .do()
                )

                for item in response.get("data", {}).get("Get", {}).get("ClinicalLiterature", []):
                    certainty = item.get("_additional", {}).get("certainty", 0.0)
                    if certainty >= self.score_threshold:
                        results.append({
                            "text": item.get("text", ""),
                            "title": item.get("title", ""),
                            "source": item.get("source", ""),
                            "year": item.get("year", ""),
                            "doi": item.get("doi", ""),
                            "score": round(certainty, 4),
                        })

            elif self.vector_store == "pinecone":
                index = self._get_client().Index("brainscape-literature")
                response = index.query(
                    vector=query_embedding,
                    top_k=k,
                    include_metadata=True,
                )

                for match in response.get("matches", []):
                    if match.get("score", 0) >= self.score_threshold:
                        metadata = match.get("metadata", {})
                        results.append({
                            "text": metadata.get("text", ""),
                            "title": metadata.get("title", ""),
                            "source": metadata.get("source", ""),
                            "year": metadata.get("year", ""),
                            "doi": metadata.get("doi", ""),
                            "score": round(match.get("score", 0), 4),
                        })
        except Exception as exc:
            logger.warning(
                "RAG retrieval unavailable (%s). Returning empty retrieval context.",
                exc,
            )
            return []

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)

        logger.info(f"RAG retrieved {len(results)} chunks for query: '{query[:50]}...'")
        return results

    @staticmethod
    def _chunk_text(
        text: str, chunk_size: int = 512, overlap: int = 64
    ) -> list[str]:
        """Split text into overlapping chunks for embedding."""
        words = text.split()
        chunks = []

        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk:
                chunks.append(chunk)

        return chunks