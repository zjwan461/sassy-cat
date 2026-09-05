from langchain_openai import ChatOpenAI
import os

chat_llm = ChatOpenAI(
    base_url=os.getenv("LLM_BASE_URL", "http://localhost:8080/v1"),
    api_key=os.getenv("LLM_API_KEY", "sk-xxx"),
    model=os.getenv("LLM_MODEL_NAME", "Qwen3.6-35B"),
    max_completion_tokens=131072
)
