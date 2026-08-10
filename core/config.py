from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings
import lancedb
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "models", "bge-small-en-v1.5")
LANCEDB_PATH = os.path.join(BASE_DIR, "data", "lancedb")

load_dotenv()

llm = ChatOpenAI(
    base_url="https://ai-gateway.mohaymen.ir/v1",
    model="openai/gpt-5.5",
    temperature=0
)

hf_embeddings = HuggingFaceEmbeddings(
    model_name=MODEL_PATH,
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True}
)

def get_lancedb_connection():
    return lancedb.connect(LANCEDB_PATH)
