import mss
import mss.tools
import os
import json
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def capture_and_interpret():
    try:
        # 1. Capture full screen of monitor 1
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            os.makedirs("captures", exist_ok=True)
            img_path = os.path.join("captures", "last_capture.png")
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=img_path)

        # 2. Open and process
        image = Image.open(img_path)

        prompt = """
        Analyze this educational question. 
        Extract into valid JSON with these keys:
        - question_text: string
        - classification: (Multiple Choice, Categorization, True/False)
        - options: list of all selectable items
        - context: short conceptual hint (do not give the answer here)
        - answer: for Multiple Choice, providing the correct string
        - suggested_mapping: for Categorization, a dictionary of category names to lists of items
        - confidence: float
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, image],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        
        # Ensure we return a string, never None
        return response.text if response.text else json.dumps({"error": "Empty AI response"})

    except Exception as e:
        return json.dumps({"error": "Vision Failure", "details": str(e)})