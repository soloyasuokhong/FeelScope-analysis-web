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

app = Flask(__name__)

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

# Layer 3: Output guard keywords (case-insensitive)
SENSITIVE_OUTPUT_KEYWORDS: List[str] = ["system", "api", "key", "config", "prompt"]


def contains_any_keyword(text: str, keywords: List[str]) -> bool:
    """
    Layer 1/3 helper — kiểm tra keyword không phân biệt hoa thường.
    """
    haystack = (text or "").lower()
    for kw in keywords:
        if (kw or "").lower() in haystack:
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

    if not (raw.startswith("{") and raw.endswith("}")):
        return None

    try:
        parsed = json.loads(raw)
    except Exception:
        return None

    if not isinstance(parsed, dict):
        return None

    return parsed


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

        # Layer 3 — OUTPUT GUARD: chặn nếu raw response chứa keyword nhạy cảm
        if contains_any_keyword(result_text, SENSITIVE_OUTPUT_KEYWORDS):
            return {"success": False, "error": "Phản hồi AI không hợp lệ."}

        # Layer 2 — STRICT JSON PARSING: chỉ parse JSON thuần (hoặc fenced JSON)
        result = strict_json_from_model_text(result_text)
        if result is None:
            return {"success": False, "error": "Phản hồi AI không hợp lệ."}

        # Validate required keys
        if "sentiment" not in result or "confidence" not in result:
            return {"success": False, "error": "Phản hồi AI không hợp lệ."}

        sentiment = result.get('sentiment', 'neutral')
        confidence = result.get('confidence', 50)
        if (not isinstance(sentiment, str)) or (sentiment not in {"positive", "negative", "neutral"}):
            return {"success": False, "error": "Phản hồi AI không hợp lệ."}
        if (not isinstance(confidence, (int, float))) or confidence < 0 or confidence > 100:
            return {"success": False, "error": "Phản hồi AI không hợp lệ."}

        return {
            'success': True,
            'sentiment': sentiment,
            'confidence': confidence,
            'explanation': result.get('explanation', 'Không thể phân tích'),
            'keywords': result.get('keywords', []),
        }
            
    except Exception as e:
        error_message = str(e)
        print("Gemini API error:", error_message)  # chỉ log nội bộ

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



