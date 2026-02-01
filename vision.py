import mss
import mss.tools
import os
import json
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Client setup
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# HIERARCHY: Verified from your Google Cloud Dashboard
MODEL_FALLBACKS = [
    "gemini-2.5-flash",       # Primary
    "gemini-3-flash",         # Secondary (Backup 1)
    "gemini-2.5-flash-lite"   # Tertiary (Backup 2)
]

def capture_and_interpret():
    try:
        # 1. Capture full screen
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            
            os.makedirs("captures", exist_ok=True)
            img_path = os.path.join("captures", "last_capture.png")
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=img_path)

        image = Image.open(img_path)

        prompt = """
        Analyze this educational image.
        
        INSTRUCTIONS:
        1. Identify the main content on the screen. Read content carefully.
        2. Extract fields into JSON:
           - question_text: string
           - classification: as a string, (Multiple Choice, Fill In The Blank, Categorization, True/False, Short Answer, if the type is something else infer to the best of your abilites what it is)
           - options: as a valid list of strings, write the provided posible answers for the question. For multiple choice this is the differenc choices. For T/F its T or F. For Fill In The Blank its all the words in the word bank. For Categorization is all the different prompts that need to be clasified as correct or incorrect. For short answers its NA. For a type not specified you can imply what the choices are)
           - context: as a string, A neutral, factual paragraph, explaining the concept in enough detail to clearly understand everything that is being talked about.
           - answer: Type myst be a string. Not a list, not a dict, a string. The correct answer. Just give enough information to answer the question, nothing more.
				For Multiple Choice: as a string, Restate the correct choice as is, do not change anything.
                For Fill In The Blank: as a string, Provide the order that the correct answers would fill in all of the blanks. Its of if not all the words in the word bank are used.
           - suggested_mapping: (For Categorization items) Dictionary.
           - confidence: float (0.0 to 1.0)
        
        IMPORTANT ON CONFIDENCE:
        - Be highly conservative. 
        - 1.0 is reserved for perfectly clear text and obvious answers.
        - If the text is slightly blurry, or the question is ambiguous, drop confidence to 0.7 or lower.
        - It is better to show low confidence than to be confidently wrong.
        
        Very Important that responce is in proper JSON format.
        """

        # 2. Iterative Model Fallback
        for model_name in MODEL_FALLBACKS:
            try:
                # Attempt generation
                response = client.models.generate_content(
                    model=model_name,
                    contents=[prompt, image],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                
                if response.text:
                    return response.text
                
            except Exception as e:
                # If a model fails, we log it in the terminal and try the next one
                print(f"⚠️ {model_name} failed/limited. Trying next backup...")
                continue
        
        return json.dumps({
            "error": "All models exhausted", 
            "details": "Check Dashboard limits for 2.5-flash, 3-flash, and 2.5-flash-lite."
        })

    except Exception as e:
        return json.dumps({"error": "Vision Failure", "details": str(e)})