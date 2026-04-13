import os
import chromadb
from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
import re

# 1. Setup - USE THE EXACT NAME FROM YOUR OLLAMA LIST
kb_root = "./docs/"
embeddings = OllamaEmbeddings(
    model="paraphrase-multilingual:latest", # Updated with :latest
    base_url="http://127.0.0.1:11434"
)

print("📄 Initializing PNK Astro Knowledge Base Sync...")

all_sections = []
# Smaller chunks (800) prevent the Sarvam 422 "Token Overflow" error
text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=80)

# 2. Loop through folders to assign metadata automatically
for folder in os.listdir(kb_root):
    folder_path = os.path.join(kb_root, folder)
    if os.path.isdir(folder_path):
        print(f"📁 Processing folder: {folder}")
        
        # We use a broad glob but the loader_cls ensures we try to read as text
        loader = DirectoryLoader(folder_path, glob="**/*", loader_cls=TextLoader)
        try:
            docs = loader.load()
            chunks = text_splitter.split_documents(docs)
            
            for chunk in chunks:
                chunk.metadata["source_type"] = folder
                
                # Extract the number from the text to make it searchable
                if folder == "numerology":
                    numbers = re.findall(r'\d+', chunk.page_content)
                    if numbers:
                        # Save the first number found (e.g., "33") as metadata
                        chunk.metadata["number_val"] = str(numbers[0]) 
                        
                all_sections.append(chunk)
        except Exception as e:
            print(f"⚠️ Skipped some files in {folder}: {e}")

print(f"🔍 Total valid sections found: {len(all_sections)}")

# 3. Connect to Chroma and Push Data
if len(all_sections) == 0:
    print("❌ No text found! Check if your ./docs/ folder has .txt or .md files.")
else:
    try:
        client = chromadb.HttpClient(host='127.0.0.1', port=8000)
        
        # Nuclear Wipe: Force a clean start for the new 384-dimension model
        try:
            client.delete_collection("langchain")
            print("🗑️ Old collection deleted. Creating fresh 384-dim index...")
        except:
            pass

        vector_db = Chroma.from_documents(
            documents=all_sections,
            embedding=embeddings,
            collection_name="langchain",
            client=client
        )
        print(f"✅ Success! {len(all_sections)} sections synced to PNK Astro DB.")
    except Exception as e:
        print(f"❌ Error during push: {e}")