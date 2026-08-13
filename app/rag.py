"""
Recuperación RAG simple sobre los documentos del CV.

Decisión de diseño: se usa TF-IDF + similitud coseno (scikit-learn) en vez
de un servicio de embeddings externo. El corpus es pequeño (unos pocos
documentos con el CV), así que no se justifica la latencia, el costo ni la
dependencia adicional de una API de embeddings. Si el corpus creciera
mucho, este módulo es el punto de reemplazo por Chroma/FAISS + embeddings.
"""
import glob
import os
from typing import List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


class Retriever:
    def __init__(self, data_dir=DATA_DIR):
        self.chunks = []  # type: List[str]
        self.sources = []  # type: List[str]
        self._load(data_dir)
        self.vectorizer = TfidfVectorizer(
            stop_words=None,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        self.matrix = self.vectorizer.fit_transform(self.chunks)

    def _load(self, data_dir):
        for path in sorted(glob.glob(os.path.join(data_dir, "*.md"))):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            # Se parte por sub-secciones (##) para tener chunks más finos
            for section in content.split("\n## "):
                section = section.strip()
                if not section:
                    continue
                if not section.startswith("#"):
                    section = "## " + section
                if len(section) > 30:
                    self.chunks.append(section)
                    self.sources.append(os.path.basename(path))

    def retrieve(self, query, top_k=6):
        query_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self.matrix).flatten()
        top_idx = sims.argsort()[::-1][:top_k]
        # Si la similitud es 0 para todo (pregunta muy genérica), regresa
        # los primeros chunks como contexto general en vez de nada.
        if sims[top_idx].max() == 0:
            return self.chunks[:top_k]
        return [self.chunks[i] for i in top_idx]


_retriever = None  # type: Optional[Retriever]


def get_retriever():
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever
