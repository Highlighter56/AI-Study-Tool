import mss
import mss.tools
import os
import json
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv
from database import get_setting

load_dotenv()

# Client setup
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# Default fallback order for question extraction (text/vision-capable models only).
# Excludes TTS, embedding, image generation, video generation, robotics, and tooling models.
DEFAULT_MODEL_FALLBACKS = [
    "gemini-2.5-flash",       # Primary fast default
    "gemini-2.5-pro",         # Higher quality fallback
    "gemini-3-flash",         # Fast backup
    "gemini-3-pro",           # Higher quality backup
    "gemini-3.1-pro",         # High reasoning fallback
    "gemini-2-flash",         # Legacy fast fallback
    "gemini-2-flash-exp",     # Experimental fallback
    "gemini-2-pro-exp",       # Experimental pro fallback
    "gemini-2.5-flash-lite",  # Low-cost final fallback
]


def get_model_fallbacks():
    override = os.getenv("OTTO_MODEL_FALLBACKS", "").strip()
    if override:
        models = [item.strip() for item in override.split(",") if item.strip()]
        return models or DEFAULT_MODEL_FALLBACKS

    db_override = str(get_setting("model_fallbacks", "") or "").strip()
    if db_override:
        models = [item.strip() for item in db_override.split(",") if item.strip()]
        return models or DEFAULT_MODEL_FALLBACKS

    return DEFAULT_MODEL_FALLBACKS


def probe_models(model_names):
    probe_image = Image.new("RGB", (4, 4), color=(255, 255, 255))
    probe_prompt = "Return strict JSON: {\"ok\": true}"
    results = []

    for model_name in model_names:
        name = str(model_name or "").strip()
        if not name:
            continue
        try:
            response = client.models.generate_content(
                model=name,
                contents=[probe_prompt, probe_image],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            ok = bool(getattr(response, "text", "").strip())
            results.append({
                "model": name,
                "ok": ok,
                "error": "" if ok else "Empty response text"
            })
        except Exception as exc:
            results.append({
                "model": name,
                "ok": False,
                "error": str(exc)
            })

    return results


def _inject_model_used(raw_text, model_name):
    content = (raw_text or "").strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        payload = json.loads(content)
    except Exception:
        return raw_text

    if isinstance(payload, dict):
        payload["model_used"] = model_name
        return json.dumps(payload)
    return raw_text

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
                    "question_type": "MULTIPLE_CHOICE|TRUE_FALSE|FILL_IN_THE_BLANK|CATEGORIZATION|ORDERING|SHORT_ANSWER|OTHER",
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
                - ORDERING -> {"ordered_items": ["first", "second", "third"]}
                - SHORT_ANSWER -> {"short_answer": "string"}
                - OTHER -> {"other_answer": "string"}

                Rules:
                - Return strict JSON only. No markdown, no code fences, no commentary.
                - options must always be a JSON array of strings (empty array is allowed).
                - answer must always be a string summary of the final answer.
                - context must be one study-friendly paragraph that naturally includes key facts needed to derive the answer.
                - do not write "the answer is ..." inside context; weave supporting facts into the explanation.
                - For CATEGORIZATION, suggested_mapping must mirror answer_payload.categories.
                - If uncertain, still return schema-compliant JSON and lower confidence.

                Confidence policy:
                - Be conservative and calibrated to readability and ambiguity.
                - Use 1.0 only for perfectly clear text and unambiguous answer.
                - Slight blur/partial occlusion/ambiguity should reduce confidence significantly.
        """

        # 2. Iterative Model Fallback
        model_fallbacks = get_model_fallbacks()
        for model_name in model_fallbacks:
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
                    return _inject_model_used(response.text, model_name)
                
            except Exception as e:
                # If a model fails, we log it in the terminal and try the next one
                print(f"⚠️ {model_name} failed/limited. Trying next backup...")
                continue
        
        return json.dumps({
            "error": "All models exhausted", 
            "details": f"All fallbacks failed. Tried: {', '.join(model_fallbacks)}"
        })

    except Exception as e:
        return json.dumps({"error": "Vision Failure", "details": str(e)})