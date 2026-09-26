from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama.embeddings import OllamaEmbeddings
from langchain_chroma import Chroma
import os
from dotenv import load_dotenv
from pathlib import Path

# Loading the environment variables for embedding models
load_dotenv()
embedding_model = os.getenv("EMBEDDING_MODEL")

# Importing the text
documents = []

for file in Path('./knowledge').glob('*.txt'):
    loader = TextLoader(str(file), encoding="utf-8")
    documents.extend(loader.load())

# Chunking the documents using RecursiveCharacterTextSplitter
splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100
)
chunks = splitter.split_documents(documents)

# Embeddings
embeddings = OllamaEmbeddings(
    model=embedding_model
)

vector_store = Chroma(
    collection_name="sarcasm_patterns",
    embedding_function=embeddings,
    persist_directory="./chroma_db"
)

batch_size = 100

# If already embedded, we want to skip embedding
if vector_store._collection.count() == 0:
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]

        print(
            f"Embedding chunks {i + 1}-{i + len(batch)} "
            f"/ {len(chunks)}"
        )

        vector_store.add_documents(batch)

def create_retriever(rag_search_kwargs: int):
    """
    Creating a retriever for RAG. 
    
    Args:
        rag_search_kwargs (int): Top-K results to pass in as context
    
    Returns:
        VectorStoreRetriever: A retriever based on the data
    """

    return vector_store.as_retriever(
        search_kwargs={"k": rag_search_kwargs}
    )