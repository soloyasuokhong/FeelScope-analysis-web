/**
 * Vietnamese Sentiment Analysis - Frontend Logic
 * Nhóm: Minh
 */

document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const textInput = document.getElementById('textInput');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const resultSection = document.getElementById('resultSection');
    const errorSection = document.getElementById('errorSection');
    const charCount = document.querySelector('.char-count');
    const sampleBtns = document.querySelectorAll('.sample-btn');
    
    // Result elements
    const sentimentEmoji = document.getElementById('sentimentEmoji');
    const sentimentLabel = document.getElementById('sentimentLabel');
    const sentimentDisplay = document.querySelector('.sentiment-display');
    const confidenceValue = document.getElementById('confidenceValue');
    const confidenceFill = document.getElementById('confidenceFill');
    const confidenceStrength = document.getElementById('confidenceStrength');
    const explanationText = document.getElementById('explanationText');
    const keywordsList = document.getElementById('keywordsList');
    const errorText = document.getElementById('errorText');

    // Sentiment configuration
    const sentimentConfig = {
        positive: {
            emoji: '😊',
            label: 'Tích cực',
            class: 'positive'
        },
        negative: {
            emoji: '😞',
            label: 'Tiêu cực',
            class: 'negative'
        },
        neutral: {
            emoji: '😐',
            label: 'Trung tính',
            class: 'neutral'
        }
    };

    // Update character count
    textInput.addEventListener('input', function() {
        const count = this.value.length;
        charCount.textContent = `${count} / 5000`;
        
        if (count > 4500) {
            charCount.style.color = '#FF4444';
        } else if (count > 4000) {
            charCount.style.color = '#FFBB33';
        } else {
            charCount.style.color = '#999';
        }
    });

    // Sample text buttons
    sampleBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const sampleText = this.getAttribute('data-text');
            textInput.value = sampleText;
            textInput.dispatchEvent(new Event('input'));
            textInput.focus();
        });
    });

    // Analyze button click
    analyzeBtn.addEventListener('click', async function() {
        const text = textInput.value.trim();
        
        if (!text) {
            showError('Vui lòng nhập văn bản cần phân tích');
            return;
        }

        // Start loading state
        setLoading(true);
        hideResults();

        try {
            const response = await fetch('/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ text: text })
            });

            const data = await response.json();

            if (data.success) {
                showResult(data);
            } else {
                showError(data.error || 'Đã xảy ra lỗi khi phân tích');
            }
        } catch (error) {
            console.error('Error:', error);
            showError('Không thể kết nối đến server. Vui lòng thử lại.');
        } finally {
            setLoading(false);
        }
    });

    // Enter key to analyze
    textInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && e.ctrlKey) {
            analyzeBtn.click();
        }
    });

    // Set loading state
    function setLoading(isLoading) {
        if (isLoading) {
            analyzeBtn.classList.add('loading');
            analyzeBtn.disabled = true;
        } else {
            analyzeBtn.classList.remove('loading');
            analyzeBtn.disabled = false;
        }
    }

    // Hide all results
    function hideResults() {
        resultSection.classList.add('hidden');
        errorSection.classList.add('hidden');
    }

    // Show result
    function showResult(data) {
        const config = sentimentConfig[data.sentiment] || sentimentConfig.neutral;
        
        // Update sentiment display
        sentimentEmoji.textContent = config.emoji;
        sentimentLabel.textContent = config.label;
        
        // Update sentiment class
        sentimentDisplay.className = 'sentiment-display ' + config.class;
        
        // Update confidence
        const confidence = Math.round(data.confidence);
        confidenceValue.textContent = confidence + '%';
        confidenceFill.style.width = '0%';
        
        // Update confidence strength label
        let strengthLabel = 'Không chắc chắn';
        if (confidence > 85) {
            strengthLabel = 'Rất mạnh';
        } else if (confidence >= 60) {
            strengthLabel = 'Khá rõ';
        }
        confidenceStrength.textContent = strengthLabel;
        
        // Animate confidence bar
        setTimeout(() => {
            confidenceFill.style.width = confidence + '%';
        }, 100);
        
        // Update explanation
        explanationText.textContent = data.explanation;
        
        // Update keywords
        keywordsList.innerHTML = '';
        if (data.keywords && data.keywords.length > 0) {
            data.keywords.forEach((keyword, index) => {
                const tag = document.createElement('span');
                tag.className = 'keyword-tag';
                tag.textContent = keyword;
                tag.style.animationDelay = (index * 0.1) + 's';
                keywordsList.appendChild(tag);
            });
        }
        
        // Show result section
        errorSection.classList.add('hidden');
        resultSection.classList.remove('hidden');
        
        // Scroll to result
        resultSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // Show error
    function showError(message) {
        errorText.textContent = message;
        resultSection.classList.add('hidden');
        errorSection.classList.remove('hidden');
    }
});
