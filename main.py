from langchain.agents import create_agent
from langchain_ollama import ChatOllama
import prompts.agent
import tools
import os
from dotenv import load_dotenv
from langchain.messages import AIMessage, HumanMessage

load_dotenv()

# Variables for creating the agent
model = ChatOllama(model=os.getenv("LLM_MODEL") or os.getenv("llm_model"))
SYSTEM_PROMPT = prompts.agent.PROMPT
tools = [tools.gather_sarcasm_feedback, tools.retrieve_sarcasm_patterns, tools.transform_to_sarcasm]


agent = create_agent(
    model = model,
    tools = tools,
    system_prompt = SYSTEM_PROMPT
)

if __name__ == "__main__":
    to_be_transformed = input("Enter a sentence to be transformed/scenario: ")

    stream = agent.stream_events(
        {"messages": {"role": "user", "content": to_be_transformed}},
        version = "v3"
    )

    for snapshot in stream.values:
        latest_message = snapshot["messages"][-1]
        if latest_message.content:
            if isinstance(latest_message, HumanMessage):
                print(f"User: {latest_message.content}")
            elif isinstance(latest_message, AIMessage):
                print(f"AI: {latest_message.content}")
        elif latest_message.tool_calls:
            print(f"Calling tools: {[tc['name'] for tc in latest_message.tool_calls]}")


