import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

def list_available_models():
    try:
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        print("--- CHECKING AVAILABLE MODELS ---")
        
        # List models that support 'generateContent'
        for model in client.models.list():
            # We only care about models that can generate content (chat/vision)
            if "generateContent" in (model.supported_actions or []):
                print(f" Found: {model.name}")
                
    except Exception as e:
        print(f" Error listing models: {e}")

if __name__ == "__main__":
    list_available_models()