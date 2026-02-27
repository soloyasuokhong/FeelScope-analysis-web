"""
Ứng dụng Phân tích Cảm xúc Văn bản Tiếng Việt
Refactored Clean Architecture Version
"""

from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
import os
import json
import re
from typing import List, Optional, Dict, Any
from typing import Literal
from pydantic import BaseModel, ValidationError, validator, root_validator
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================
# Gemini Config
# ========================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY environment variable")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")


# ========================
# Security Layer
# ========================

DANGEROUS_INPUT_KEYWORDS: List[str] = [
    "ignore previous",
    "system prompt",
    "api key",
    "server config",
    "reveal",
    "override",
    "password",
    ".env",
    "return system",
    "print config",
]

SENSITIVE_OUTPUT_REGEXES: List[re.Pattern] = [
    re.compile(r"\b(?:sk|rk|pk|AIza)[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r'"(?:api_key|access_token|secret|password)"\s*:\s*"[A-Za-z0-9_\-]{8,}"'),
    re.compile(r"\b(?:GEMINI_API_KEY|OPENAI_API_KEY|DATABASE_URL|FLASK_ENV|SECRET_KEY)\s*=\s*.+"),
]


def contains_any_keyword(text: str, keywords: List[str]) -> bool:
    haystack = (text or "").lower()
    return any((kw or "").lower() in haystack for kw in keywords)


def check_sensitive_output(text: str) -> bool:
    for pattern in SENSITIVE_OUTPUT_REGEXES:
        if pattern.search(text or ""):
            return True
    return False


def strict_json_from_model_text(model_text: str) -> Optional[Dict[str, Any]]:
    raw = (model_text or "").strip()

    fence_match = re.match(r"^\s*```(?:json)?\s*([\s\S]*?)\s*```\s*$", raw, flags=re.IGNORECASE)
    if fence_match:
        raw = fence_match.group(1).strip()

    if raw.startswith("{") and raw.endswith("}"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None

    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        return None

    try:
        parsed = json.loads(json_match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None

    return None


# ========================
# Schema Validation Layer
# ========================

class EmotionResponse(BaseModel):
    sentiment: Literal["positive", "negative", "neutral"]
    confidence: float
    probabilities: Dict[str, float]
    explanation: Optional[str] = None
    keywords: Optional[List[str]] = None

    @validator("confidence", pre=True)
    def normalize_confidence(cls, value):
        if not isinstance(value, (int, float)):
            raise ValueError("confidence must be numeric")
        v = float(value)
        return v / 100.0 if v > 1 else v

    @validator("probabilities", pre=True)
    def validate_probabilities(cls, value):
        if not isinstance(value, dict):
            raise ValueError("probabilities must be object")

        required = ["positive", "neutral", "negative"]
        probs = {}

        for key in required:
            v = float(value.get(key, 0))
            if v < 0:
                raise ValueError("probabilities must be non-negative")
            probs[key] = v

        total = sum(probs.values())
        if total <= 0:
            raise ValueError("invalid probabilities sum")

        factor = 100.0 / total
        return {k: v * factor for k, v in probs.items()}

    @root_validator
    def sync_confidence(cls, values):
        sentiment = values.get("sentiment")
        probs = values.get("probabilities", {})
        if sentiment in probs:
            values["confidence"] = probs[sentiment] / 100.0
        return values


# ========================
# AI Layer
# ========================

def call_gemini(prompt: str) -> str:
    response = model.generate_content(prompt)
    return (response.text or "").strip()


# ========================
# Service Layer
# ========================

def sentiment_service(text: str) -> Dict[str, Any]:

    prompt = f"""
Bạn là chuyên gia phân tích cảm xúc tiếng Việt.

Văn bản:
"{text}"

Trả về JSON:
{{
    "sentiment": "positive|neutral|negative",
    "confidence": số 0-100,
    "probabilities": {{
        "positive": số,
        "neutral": số,
        "negative": số
    }},
    "explanation": "...",
    "keywords": []
}}
Chỉ trả về JSON.
"""

    try:
        result_text = call_gemini(prompt)

        if check_sensitive_output(result_text):
            return {"success": False, "error": "Phản hồi AI không hợp lệ."}

        parsed = strict_json_from_model_text(result_text)
        if parsed is None:
            return {"success": False, "error": "Phản hồi AI không hợp lệ."}

        validated = EmotionResponse(**parsed)

        return {
            "success": True,
            "sentiment": validated.sentiment,
            "confidence": validated.confidence * 100,
            "confidence_raw": validated.confidence,
            "probabilities": validated.probabilities,
            "explanation": validated.explanation or "",
            "keywords": validated.keywords or [],
        }

    except Exception as e:
        logger.error("Sentiment service error: %s", str(e))
        return {
            "success": False,
            "error": "Hệ thống tạm thời không khả dụng."
        }


# ========================
# Routes
# ========================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.get_json()
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"success": False, "error": "Vui lòng nhập văn bản."})

    if len(text) > 5000:
        return jsonify({"success": False, "error": "Văn bản quá dài."})

    if contains_any_keyword(text, DANGEROUS_INPUT_KEYWORDS):
        return jsonify({"success": False, "error": "Nội dung không hợp lệ."})

    return jsonify(sentiment_service(text))


@app.route('/generate_and_analyze', methods=['POST'])
def generate_and_analyze():
    data = request.get_json()
    prompt = (data.get("prompt") or "").strip()

    if not prompt:
        return jsonify({"success": False, "error": "Vui lòng nhập yêu cầu."})

    if len(prompt) > 500:
        return jsonify({"success": False, "error": "Yêu cầu quá dài."})

    if contains_any_keyword(prompt, DANGEROUS_INPUT_KEYWORDS):
        return jsonify({"success": False, "error": "Nội dung không hợp lệ."})

    try:
        generation_prompt = f"""
Viết nội dung theo yêu cầu sau:
"{prompt}"
Chỉ trả về nội dung văn bản.
"""

        generated_text = call_gemini(generation_prompt)

        if check_sensitive_output(generated_text):
            return jsonify({"success": False, "error": "Phản hồi AI không hợp lệ."})

        sentiment_result = sentiment_service(generated_text)

        if not sentiment_result.get("success"):
            return jsonify(sentiment_result)

        return jsonify({
            "success": True,
            "generated_text": generated_text,
            **sentiment_result
        })

    except Exception as e:
        logger.error("Generate error: %s", str(e))
        return jsonify({"success": False, "error": "Không thể tạo nội dung."})


