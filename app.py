"""
Ứng dụng Phân tích Cảm xúc Văn bản Tiếng Việt
Sử dụng Google Gemini API
"""

from flask import Flask, render_template, request, jsonify
import google.generativeai as genai
import os
import json
import re

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
        result_text = response.text.strip()
        
        # Trích xuất JSON từ response
        json_match = re.search(r'\{[\s\S]*\}', result_text)
        if json_match:
            result = json.loads(json_match.group())
            return {
                'success': True,
                'sentiment': result.get('sentiment', 'neutral'),
                'confidence': result.get('confidence', 50),
                'explanation': result.get('explanation', 'Không thể phân tích'),
                'keywords': result.get('keywords', [])
            }
        else:
            return {
                'success': False,
                'error': 'Không thể phân tích kết quả từ AI'
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': f'Lỗi khi gọi API: {str(e)}'
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
    
    result = analyze_sentiment(text)
    return jsonify(result)

if __name__ == '__main__':
    print("🚀 Ứng dụng Phân tích Cảm xúc Tiếng Việt")
    print("🌐 Truy cập: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)

