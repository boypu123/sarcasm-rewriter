from langchain_ollama import OllamaEmbeddings

e = OllamaEmbeddings(
    model="nomic-embed-text",
    base_url="http://127.0.0.1:11434"
)

texts = [chunk.page_content for chunk in chunks]

print("chunks:", len(texts))

result = e.embed_documents(texts)

print("embeddings:", len(result))