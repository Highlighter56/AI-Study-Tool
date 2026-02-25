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
                Analyze this educational screenshot and return ONLY valid JSON.

                REQUIRED OUTPUT SCHEMA (all keys required):
                {
                    "question_text": "string",
                    "question_type": "MULTIPLE_CHOICE|TRUE_FALSE|FILL_IN_THE_BLANK|CATEGORIZATION|SHORT_ANSWER|OTHER",
                    "classification": "human readable label",
                    "options": ["string"],
                    "context": "string",
                    "answer": "string",
                    "suggested_mapping": {"category": ["item"]},
                    "answer_payload": {},
                    "confidence": 0.0
                }

                answer_payload MUST match question_type:
                - MULTIPLE_CHOICE -> {"selected_option": "exact option text"}
                - TRUE_FALSE -> {"is_true": true|false}
                - FILL_IN_THE_BLANK -> {"blanks": ["answer1", "answer2"]}
                - CATEGORIZATION -> {"categories": {"category": ["item"]}}
                - SHORT_ANSWER -> {"short_answer": "string"}
                - OTHER -> {"other_answer": "string"}

                Rules:
                - Return strict JSON only. No markdown, no code fences, no commentary.
                - options must always be a JSON array of strings (empty array is allowed).
                - answer must always be a string summary of the final answer.
                - For CATEGORIZATION, suggested_mapping must mirror answer_payload.categories.
                - If uncertain, still return schema-compliant JSON and lower confidence.

                Confidence policy:
                - Be conservative and calibrated to readability and ambiguity.
                - Use 1.0 only for perfectly clear text and unambiguous answer.
                - Slight blur/partial occlusion/ambiguity should reduce confidence significantly.
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