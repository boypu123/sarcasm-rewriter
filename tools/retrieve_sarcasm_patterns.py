from langchain.tools import tool, ToolRuntime
from rag import create_retriever

retriever = create_retriever(3)

@tool(
    "retrieve_sarcasm_patterns", 
    description="Retrieving sarcasm patterns from the database for most authentic sarcasm that is close to the input."
)
def retrieve_sarcasm_patterns(question: str, runtime: ToolRuntime) -> str:
    """
    Retrieving similar sarcasm from the database using RAG.

    Args:
    question (str): Input of RAG (to be searched in the database).

    Returns:
    String documents from the sarcasm database that are similar to the input.
    """
    # Initialising writer to write the stream
    writer = runtime.stream_writer

    # Retrieving via RAG

    writer("Looking up for relevant sarcasm in the database")

    docs = retriever.invoke(question)

    context = "\n\n".join(
        doc.page_content for doc in docs
    )
    
    return context