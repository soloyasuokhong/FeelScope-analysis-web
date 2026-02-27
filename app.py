"""
Ứng dụng Phân tích Cảm xúc Văn bản Tiếng Việt
Sử dụng Google Gemini API
"""

from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
import os
import json
import re
from typing import List, Optional, Dict, Any
from typing import Literal
from pydantic import BaseModel, ValidationError, validator
import logging

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Lấy API key từ biến môi trường
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Kiểm tra trước khi cấu hình
if not GEMINI_API_KEY:
    raise ValueError("Missing GEMINI_API_KEY environment variable")

# Cấu hình Gemini
genai.configure(api_key=GEMINI_API_KEY)

# Khởi tạo model Gemini (sử dụng gemini-1.5-flash có quota cao hơn)
model = genai.GenerativeModel('gemini-2.5-flash')

# ========================
# Security: Prompt-Injection Guards (3 layers)
# ========================
# Layer 1: Input guard keywords (case-insensitive)
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

# Layer 3: Output guard patterns (regex, tránh false positive với từ đơn lẻ)
SENSITIVE_OUTPUT_REGEXES: List[re.Pattern] = [
    # API key-like tokens (ví dụ: sk-..., AIza..., chuỗi dài base64-ish)
    re.compile(r"\b(?:sk|rk|pk|AIza)[A-Za-z0-9_\-]{16,}\b"),
    # JSON config dump chứa khóa nhạy cảm
    re.compile(r'"(?:api_key|access_token|secret|password)"\s*:\s*"[A-Za-z0-9_\-]{8,}"'),
    # Biến môi trường / cấu hình nhạy cảm dạng KEY=VALUE
    re.compile(r"\b(?:GEMINI_API_KEY|OPENAI_API_KEY|DATABASE_URL|FLASK_ENV|SECRET_KEY)\s*=\s*.+"),
    # System prompt / instruction dump rõ ràng
    re.compile(r"begin\s+system\s+prompt", re.IGNORECASE),
    re.compile(r"do\s+not\s+share\s+this\s+prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+a\s+large\s+language\s+model", re.IGNORECASE),
]


def contains_any_keyword(text: str, keywords: List[str]) -> bool:
    """
    Layer 1/3 helper — kiểm tra keyword không phân biệt hoa thường.
    """
    haystack = (text or "").lower()
    for kw in keywords:
        if (kw or "").lower() in haystack:
            return True
    return False


def check_sensitive_output(text: str) -> bool:
    """
    Layer 3: kiểm tra output model có lộ thông tin nhạy cảm (API key, config dump...).
    Không match các từ đơn lẻ bình thường để tránh false positive.
    """
    haystack = text or ""
    for pattern in SENSITIVE_OUTPUT_REGEXES:
        if pattern.search(haystack):
            return True
    return False


def strict_json_from_model_text(model_text: str) -> Optional[Dict[str, Any]]:
    """
    Layer 2: Strict JSON output parsing.
    Accept only pure JSON (optionally wrapped in ```json ... ```), no extra text.
    KHÔNG raise exception — trả về None nếu không parse được.
    """
    raw = (model_text or "").strip()

    # Allow a single fenced code block: ```json {..} ```
    fence_match = re.match(r"^\s*```(?:json)?\s*([\s\S]*?)\s*```\s*$", raw, flags=re.IGNORECASE)
    if fence_match:
        raw = fence_match.group(1).strip()

    # Trường hợp lý tưởng: toàn bộ chuỗi là JSON object
    if raw.startswith("{") and raw.endswith("}"):
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
        if isinstance(parsed, dict):
            return parsed
        return None

    # Nếu có text bao quanh, thử trích JSON đầu tiên dạng {...}
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        return None

    try:
        parsed = json.loads(json_match.group(0))
    except Exception:
        return None

    if not isinstance(parsed, dict):
        return None

    return parsed


class EmotionResponse(BaseModel):
    """
    Layer 2: Schema validation cho phản hồi AI.
    Model nội bộ, không làm thay đổi JSON trả ra frontend.
    """

    sentiment: Literal["positive", "negative", "neutral"]
    confidence: float  # luôn chuẩn hóa về khoảng [0, 1]

    @validator("confidence", pre=True)
    def normalize_and_check_range(cls, value: Any) -> float:
        """
        Nhận 0–1 hoặc 0–100, chuẩn hóa về 0–1 và validate trong model.
        """
        if not isinstance(value, (int, float)):
            raise ValueError("confidence must be numeric")
        v = float(value)
        if v < 0:
            raise ValueError("confidence must be non-negative")
        if v <= 1.0:
            norm = v
        elif v <= 100.0:
            norm = v / 100.0
        else:
            raise ValueError("confidence out of expected range")
        if not 0.0 <= norm <= 1.0:
            raise ValueError("confidence must be between 0 and 1 after normalization")
        return norm


def analyze_sentiment(text):
    """
    Phân tích cảm xúc văn bản tiếng Việt sử dụng Gemini API
    Trả về: sentiment (positive/negative/neutral), confidence, explanation
    """
    
    prompt = f"""Bạn là một chuyên gia phân tích cảm xúc văn bản tiếng Việt. 
Hãy phân tích đoạn văn bản sau và xác định cảm xúc của nó.

Văn bản cần phân tích:
"{text}"

Hãy trả về kết quả theo định dạng JSON như sau (chỉ trả về JSON, không có text khác):
{{
    "sentiment": "positive" hoặc "negative" hoặc "neutral",
    "confidence": số từ 0 đến 100 (độ tin cậy phần trăm),
    "explanation": "giải thích ngắn gọn bằng tiếng Việt tại sao bạn phân loại như vậy",
    "keywords": ["từ khóa 1", "từ khóa 2"] (các từ/cụm từ thể hiện cảm xúc chính)
}}

Lưu ý:
- positive: cảm xúc tích cực, vui vẻ, hài lòng, yêu thích
- negative: cảm xúc tiêu cực, buồn, tức giận, không hài lòng  
- neutral: trung tính, không thể hiện cảm xúc rõ ràng
"""
    
    try:
        response = model.generate_content(prompt)
        result_text = (response.text or "").strip()
        logger.info("Gemini call succeeded, output length=%d", len(result_text))

        # Layer 3 — OUTPUT GUARD: chặn khi có pattern thực sự nhạy cảm
        if check_sensitive_output(result_text):
            logger.warning("Validation error: sensitive pattern detected in model output")
            return {"success": False, "error": "Phản hồi AI không hợp lệ."}

        # Layer 2 — STRICT JSON PARSING: chỉ parse JSON thuần (hoặc fenced JSON)
        result = strict_json_from_model_text(result_text)
        if result is None:
            logger.warning("Validation error: cannot parse strict JSON from model output")
            return {"success": False, "error": "Phản hồi AI không hợp lệ."}

        # Robust schema validation dùng Pydantic (single source of truth)
        try:
            validated = EmotionResponse(
                sentiment=result.get("sentiment"),
                confidence=result.get("confidence"),
            )
        except (ValidationError, ValueError) as ve:
            logger.warning("EmotionResponse validation failed: %s", ve)
            return {"success": False, "error": "Phản hồi AI không hợp lệ."}

        # Nếu hợp lệ: giữ sentiment, chuyển confidence về phần trăm cho frontend
        sentiment = validated.sentiment
        confidence_percent = validated.confidence * 100.0

        return {
            'success': True,
            'sentiment': sentiment,
            'confidence': confidence_percent,
            'confidence_raw': validated.confidence,
            'explanation': result.get('explanation', 'Không thể phân tích'),
            'keywords': result.get('keywords', []),
        }

    except Exception as e:
        error_message = str(e)
        logger.error("Gemini API error: %s", error_message)

        # Xử lý riêng lỗi quota
        if "429" in error_message or "quota" in error_message.lower():
            return {
                'success': False,
                'error': "Bạn đã gửi quá nhiều yêu cầu. Vui lòng đợi khoảng 1 phút rồi thử lại."
            }

        # Lỗi chung
        return {
            'success': False,
            'error': "Hệ thống đang quá tải hoặc tạm thời không khả dụng. Vui lòng thử lại sau."
        }

@app.route('/')
def index():
    """Trang chủ"""
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    """API endpoint để phân tích cảm xúc"""
    data = request.get_json()
    text = data.get('text', '').strip()
    
    if not text:
        return jsonify({
            'success': False,
            'error': 'Vui lòng nhập văn bản cần phân tích'
        })
    
    if len(text) > 5000:
        return jsonify({
            'success': False,
            'error': 'Văn bản quá dài (tối đa 5000 ký tự)'
        })

    # Layer 1 — INPUT GUARD: chặn keyword nguy hiểm trước khi gọi Gemini
    if contains_any_keyword(text, DANGEROUS_INPUT_KEYWORDS):
        return jsonify({
            'success': False,
            'error': 'Nội dung không hợp lệ.'
        })
    
    result = analyze_sentiment(text)
    return jsonify(result)



