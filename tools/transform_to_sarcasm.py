from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
import prompts.tools.transform_to_sarcasm
import os
from dotenv import load_dotenv

load_dotenv()
llm_model = os.getenv("LLM_MODEL")

@tool(
    "transform_to_sarcasm",
    description="Transform sentences to make it sarcastic, or draft amazingly sarcastic replies to a situation. We recommend you to first retrieve sarcastic content through the database via retrieve_sarcasm_patterns before using this tool, unless the task is very easy."
)
def transform_to_sarcasm(original: str, context: str = "No examples exist. Use your own imagination.") -> str:
    """
    Tool transforming a sentence to sarcasm (or replying sarcastically in a scenario) via the Ollama LLM model.

    Args:
    Original (str): Original sentences yet to be transformed or a scenario. 
    Context (str): Context to give to help the LLM on being sarcastic. Usually retrieved using RAG.

    Returns:
    Sarcastic sentences.
    """
    # Creating the model
    model = ChatOllama(model=llm_model)

    # Injecting the prompt into chain.
    prompt = ChatPromptTemplate.from_template(
       prompts.tools.transform_to_sarcasm.PROMPT
    )

    chain = prompt | model
    results = chain.invoke({"context": context, "original": original})

    return results.content