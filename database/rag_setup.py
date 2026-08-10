from dotenv import load_dotenv
from llama_parse import LlamaParse
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import LanceDB
import lancedb
from core.config import hf_embeddings

load_dotenv()

print("Extracting text from the PDF using LlamaParse (this may take a while)...")

pdf_path = "food_book.pdf"
parser = LlamaParse(
    result_type="text",
    verbose=True
)

parsed_documents = parser.load_data(pdf_path)

docs = [Document(page_content=doc.text) for doc in parsed_documents]
print(f"Extraction completed! {len(docs)} pages/sections were loaded.")
print("Splitting the text into smaller chunks...")
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)

splits = text_splitter.split_documents(docs)
print(f"Text split into {len(splits)} chunks.")
print("Loading the embedding model from the local system...")
print("Creating the LanceDB vector database...")

db_path = "./lancedb"
db = lancedb.connect(db_path)

vector_store = LanceDB.from_documents(
    documents=splits,
    embedding=hf_embeddings,
    connection=db,
    table_name="food_knowledge_base"
)

print("Success! All book data has been stored in LanceDB.")
