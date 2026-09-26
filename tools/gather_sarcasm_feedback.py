from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pydantic import BaseModel
import os
import prompts.tools.gather_sarcasm_feedback
from dotenv import load_dotenv

load_dotenv()
llm_model = os.getenv("LLM_MODEL")

class FeedbackFormat(BaseModel):
    ratings: int
    feedback: str

@tool(
    "gather_sarcasm_feedback",
    description="Gathering feedback on the sarcasm generated"
)
def gather_sarcasm_feedback(sentences: str) -> str:
    """
    Rating how sarcastic a sentence is, and gives feedback via Ollama LLM.

    Args:
    sentences (str): Sentences to be given feedback on.

    Returns:
    Feedback following FeedbackFormat.
    """
    # Creating model
    model = ChatOllama(model=llm_model)
    structured_feedback_model = model.with_structured_output(FeedbackFormat)

    # We are gathering sarcasm feedback, so we need to inject the prompt into the chain
    prompt = ChatPromptTemplate.from_template(prompts.tools.gather_sarcasm_feedback.PROMPT)

    chain = prompt | model
    return chain.invoke({"sentences": sentences})