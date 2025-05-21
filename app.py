from flask import Flask, render_template, request, jsonify, session
import random
import string
import json
import os
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = os.urandom(24)  # 用于会话管理

# 配置文件路径
RULES_FILE = "cipher_rules.json"
HISTORY_FILE = "cipher_history.json"

# 加密模式
MODES = {
    "substitution": {"en": "Substitution Mode", "zh": "替换模式"},
    "shift": {"en": "Shift Mode", "zh": "移位模式"},
    "mixed": {"en": "Mixed Mode", "zh": "混合模式"}
}

# 错误消息
ERROR_MESSAGES = {
    "empty_text": {"en": "Please enter text to process", "zh": "请输入要处理的文本"},
    "missing_rule": {"en": "Please provide rule number", "zh": "请提供规则编号"},
    "invalid_rule": {"en": "Invalid rule number", "zh": "无效的规则编号"},
    "encrypt_fail": {"en": "Encryption failed", "zh": "加密失败"},
    "decrypt_fail": {"en": "Decryption failed", "zh": "解密失败"}
}

# 更可靠的规则生成
def generate_rule(mode="substitution", shift_value=0):
    if mode == "substitution":
        # 创建字符列表并打乱顺序
        chars = list(string.printable)
        shuffled = chars.copy()
        
        # 确保没有字符映射到自身
        while True:
            random.shuffle(shuffled)
            if all(original != mapped for original, mapped in zip(chars, shuffled)):
                break
        
        return {"mode": mode, "mapping": {original: mapped for original, mapped in zip(chars, shuffled)}}
    
    elif mode == "shift":
        # 移位模式 (类似凯撒密码)
        if shift_value == 0:
            shift_value = random.randint(1, 25)
        return {"mode": mode, "shift": shift_value}
    
    elif mode == "mixed":
        # 混合模式：先替换再偏移
        chars = list(string.printable)
        shuffled = chars.copy()
        random.shuffle(shuffled)
        shift_value = random.randint(1, 25)
        
        return {
            "mode": mode, 
            "mapping": {original: mapped for original, mapped in zip(chars, shuffled)},
            "shift": shift_value
        }

# 加载或创建规则
def load_rules():
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# 保存新规则
def save_new_rule(rule):
    rules = load_rules()
    rules.append(rule)
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    return len(rules) - 1  # 返回新规则的索引

# 加载历史记录
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# 保存历史记录
def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

# 添加历史记录
def add_history(operation, input_text, output_text, rule_index, user_id):
    history = load_history()
    history.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "operation": operation,  # 支持中英文操作名称
        "input": input_text,
        "output": output_text,
        "rule_index": rule_index,
        "user_id": user_id
    })
    if len(history) > 1000:  # 限制历史记录数量
        history = history[-1000:]
    save_history(history)

# 获取请求的语言
def get_language(request):
    # 尝试从请求参数、cookie或header中获取语言设置
    lang = request.args.get('lang') or request.cookies.get('lang')
    if not lang:
        accept_languages = request.headers.get('Accept-Language', '')
        if 'zh' in accept_languages:
            lang = 'zh'
        else:
            lang = 'en'
    return lang if lang in ['en', 'zh'] else 'en'

# 加密函数
def encrypt_text(text, mode="substitution", rule_index=None, shift_value=0):
    rules = load_rules()
    
    # 创建新规则
    if rule_index is None:
        rule = generate_rule(mode, shift_value)
        rule_index = save_new_rule(rule)
    else:
        if rule_index >= len(rules):
            return "无效的规则编号！", -1
        rule = rules[rule_index]
    
    # 根据模式执行加密
    if rule["mode"] == "substitution":
        encrypted = [rule["mapping"].get(char, char) for char in text]
        result = "".join(encrypted)
    
    elif rule["mode"] == "shift":
        result = ""
        shift = rule["shift"]
        for char in text:
            if char.isalpha():
                ascii_offset = ord('a') if char.islower() else ord('A')
                # 字母移位
                result += chr((ord(char) - ascii_offset + shift) % 26 + ascii_offset)
            else:
                result += char
    
    elif rule["mode"] == "mixed":
        # 先替换再移位
        temp = ""
        for char in text:
            temp += rule["mapping"].get(char, char)
            
        result = ""
        shift = rule["shift"]
        for char in temp:
            if char.isalpha():
                ascii_offset = ord('a') if char.islower() else ord('A')
                result += chr((ord(char) - ascii_offset + shift) % 26 + ascii_offset)
            else:
                result += char
    
    return result, rule_index

# 解密函数
def decrypt_text(encrypted_text, rule_index):
    rules = load_rules()
    if not rules or rule_index >= len(rules):
        return "无效的规则编号！"
    
    rule = rules[rule_index]
    result = ""
    
    # 根据模式执行解密
    if rule["mode"] == "substitution":
        reverse_map = {v: k for k, v in rule["mapping"].items()}
        decrypted = [reverse_map.get(char, char) for char in encrypted_text]
        result = "".join(decrypted)
    
    elif rule["mode"] == "shift":
        shift = rule["shift"]
        for char in encrypted_text:
            if char.isalpha():
                ascii_offset = ord('a') if char.islower() else ord('A')
                # 反向移位
                result += chr((ord(char) - ascii_offset - shift) % 26 + ascii_offset)
            else:
                result += char
    
    elif rule["mode"] == "mixed":
        # 先反向移位
        temp = ""
        shift = rule["shift"]
        for char in encrypted_text:
            if char.isalpha():
                ascii_offset = ord('a') if char.islower() else ord('A')
                temp += chr((ord(char) - ascii_offset - shift) % 26 + ascii_offset)
            else:
                temp += char
        
        # 再反向替换
        reverse_map = {v: k for k, v in rule["mapping"].items()}
        decrypted = [reverse_map.get(char, char) for char in temp]
        result = "".join(decrypted)
    
    return result

# 确保用户有ID
def get_user_id():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

# 根据用户ID获取历史记录
def get_user_history(user_id):
    all_history = load_history()
    return [h for h in all_history if h.get('user_id') == user_id]

# 路由
@app.route('/')
def index():
    user_id = get_user_id()
    return render_template('index.html', modes=MODES)

# API 路由 - 加密
@app.route('/api/encrypt', methods=['POST'])
def api_encrypt():
    # 获取语言首选项
    lang = request.json.get('lang', 'en')
    if lang not in ['en', 'zh']:
        lang = 'en'
        
    data = request.json
    text = data.get('text', '')
    mode = data.get('mode', 'substitution')
    
    if not text:
        return jsonify({'error': ERROR_MESSAGES["empty_text"][lang]}), 400
    
    user_id = get_user_id()
    result, rule_index = encrypt_text(text, mode)
    
    # 添加到历史记录，根据语言保存操作名称
    operation = "Encrypt" if lang == "en" else "加密"
    add_history(operation, text, result, rule_index, user_id)
    
    return jsonify({
        'result': result,
        'rule_index': rule_index,
        'mode': mode
    })

# API 路由 - 解密
@app.route('/api/decrypt', methods=['POST'])
def api_decrypt():
    # 获取语言首选项
    lang = request.json.get('lang', 'en')
    if lang not in ['en', 'zh']:
        lang = 'en'
        
    data = request.json
    text = data.get('text', '')
    rule_index = data.get('rule_index')
    
    if not text:
        return jsonify({'error': ERROR_MESSAGES["empty_text"][lang]}), 400
    
    if rule_index is None:
        return jsonify({'error': ERROR_MESSAGES["missing_rule"][lang]}), 400
    
    try:
        rule_index = int(rule_index)
    except ValueError:
        return jsonify({'error': ERROR_MESSAGES["invalid_rule"][lang]}), 400
    
    user_id = get_user_id()
    result = decrypt_text(text, rule_index)
    
    # 添加到历史记录，根据语言保存操作名称
    operation = "Decrypt" if lang == "en" else "解密"
    add_history(operation, text, result, rule_index, user_id)
    
    return jsonify({
        'result': result
    })

# 历史记录路由
@app.route('/history')
def history():
    user_id = get_user_id()
    user_history = get_user_history(user_id)
    return render_template('history.html', history=user_history)

# API 路由 - 获取历史记录
@app.route('/api/history')
def api_history():
    user_id = get_user_id()
    user_history = get_user_history(user_id)
    return jsonify(user_history)

if __name__ == '__main__':
    app.run(debug=True) 