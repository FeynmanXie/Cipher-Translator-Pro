from flask import Flask, render_template, request, jsonify, session
import random
import string
import json
import os
from datetime import datetime
import uuid
from supabase import create_client
from dotenv import load_dotenv

app = Flask(__name__)
app.secret_key = os.urandom(24)  # 用于会话管理

# 加载环境变量
load_dotenv()

# Supabase配置
SUPABASE_URL = "https://kjjnxkbvzjqlwecsssfr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imtqam54a2J2empxbHdlY3Nzc2ZyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDc5MjYwMTIsImV4cCI6MjA2MzUwMjAxMn0.iYka9HU_Ux2Via_1juqPa4cK9XeqluqsWkNHbj9k0NY"

# 初始化Supabase客户端
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 表名
RULES_TABLE = "cipher_rules"
HISTORY_TABLE = "cipher_history"
DEVICES_TABLE = "devices"

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

# 从数据库加载规则
def load_rules():
    try:
        response = supabase.table(RULES_TABLE).select("*").execute()
        return response.data
    except Exception as e:
        print(f"Error loading rules: {e}")
        # 如果数据库操作失败，返回内存中的规则（如果有）
        return getattr(app, 'memory_rules', [])

# 保存新规则到数据库
def save_new_rule(rule):
    try:
        # 将规则转换为JSON字符串
        rule_json = json.dumps(rule)
        # 插入规则并获取返回的数据
        response = supabase.table(RULES_TABLE).insert({"rule_data": rule_json}).execute()
        # 返回新插入规则的ID
        if response.data and len(response.data) > 0:
            return response.data[0]['id']
    except Exception as e:
        print(f"Error saving rule: {e}")
        # 如果数据库操作失败，备用方案是使用内存存储
        if not hasattr(app, 'memory_rules'):
            app.memory_rules = []
        app.memory_rules.append(rule)
        return len(app.memory_rules) - 1
    
    return -1

# 从数据库加载历史记录
def load_history():
    response = supabase.table(HISTORY_TABLE).select("*").execute()
    return response.data

# 获取或创建设备ID
def get_device_id():
    if 'device_id' not in session:
        # 生成一个新的设备ID
        device_id = str(uuid.uuid4())

        try:
            # 尝试保存到数据库
            response = supabase.table(DEVICES_TABLE).insert({
                "device_id": device_id,
                "created_at": datetime.now().isoformat()
            }).execute()

            # 检查插入是否成功
            if response.data and len(response.data) > 0:
                session['device_id'] = device_id
                print(f"Successfully saved new device ID: {device_id}")
            else:
                # 插入失败，不设置session，返回None
                print(f"Failed to save new device ID {device_id} to database.")
                return None

        except Exception as e:
            # 如果插入发生异常，打印错误，不设置session，返回None
            print(f"Error saving device ID: {e}")
            return None

    # 如果session中已有device_id，直接返回
    return session.get('device_id')

# 添加历史记录到数据库 (修改以处理get_device_id返回None的情况)
def add_history(operation, input_text, output_text, rule_index, device_id):
    # 如果无法获取有效的device_id，则只使用内存存储
    if device_id is None:
        print("Warning: No valid device ID available, using memory history only.")
        if not hasattr(app, 'memory_history'):
            app.memory_history = []
        app.memory_history.append({
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "input_text": input_text,
            "output_text": output_text,
            "rule_id": rule_index,
            "device_id": "unknown" # 使用一个占位符或标记
        })
        return

    # 准备历史记录数据
    history_data = {
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "input_text": input_text,
        "output_text": output_text,
        "rule_id": rule_index,
        "device_id": device_id
    }

    try:
        # 插入数据到数据库
        supabase.table(HISTORY_TABLE).insert(history_data).execute()
        print(f"Successfully added history record for device ID: {device_id}")
    except Exception as e:
        print(f"Error adding history to database: {e}")
        # 如果数据库操作失败，备用方案是使用内存存储
        if not hasattr(app, 'memory_history'):
            app.memory_history = []
        app.memory_history.append(history_data)

# 根据设备ID获取历史记录
def get_device_history(device_id):
    try:
        response = supabase.table(HISTORY_TABLE).select("*").eq("device_id", device_id).execute()
        return response.data
    except Exception as e:
        print(f"Error getting history: {e}")
        # 如果数据库操作失败，返回内存中的历史记录（如果有）
        memory_history = getattr(app, 'memory_history', [])
        return [h for h in memory_history if h.get('device_id') == device_id]

# 获取规则详情
def get_rule_by_id(rule_id):
    try:
        # 先尝试从数据库获取
        response = supabase.table(RULES_TABLE).select("*").eq("id", rule_id).execute()
        if response.data and len(response.data) > 0:
            rule_data = response.data[0]
            # 将JSON字符串转换回Python对象
            return json.loads(rule_data['rule_data'])
    except Exception as e:
        print(f"Error getting rule: {e}")
        
    # 如果从数据库获取失败，尝试从内存中获取
    memory_rules = getattr(app, 'memory_rules', [])
    if isinstance(rule_id, int) and 0 <= rule_id < len(memory_rules):
        return memory_rules[rule_id]
    
    return None

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
    # 创建新规则
    if rule_index is None:
        rule = generate_rule(mode, shift_value)
        rule_index = save_new_rule(rule)
    else:
        rule = get_rule_by_id(rule_index)
        if not rule:
            return "无效的规则编号！", -1
    
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
    rule = get_rule_by_id(rule_index)
    if not rule:
        return "无效的规则编号！"
    
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

# 路由
@app.route('/')
def index():
    device_id = get_device_id()
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
    
    device_id = get_device_id()
    result, rule_index = encrypt_text(text, mode)
    
    # 添加到历史记录，根据语言保存操作名称
    operation = "Encrypt" if lang == "en" else "加密"
    add_history(operation, text, result, rule_index, device_id)
    
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
    
    device_id = get_device_id()
    result = decrypt_text(text, rule_index)
    
    # 添加到历史记录，根据语言保存操作名称
    operation = "Decrypt" if lang == "en" else "解密"
    add_history(operation, text, result, rule_index, device_id)
    
    return jsonify({
        'result': result
    })

# 历史记录路由
@app.route('/history')
def history():
    device_id = get_device_id()
    device_history = get_device_history(device_id)
    return render_template('history.html', history=device_history)

# API 路由 - 获取历史记录
@app.route('/api/history')
def api_history():
    device_id = get_device_id()
    device_history = get_device_history(device_id)
    return jsonify(device_history)

# API 路由 - 清空历史记录
@app.route('/api/clear_history', methods=['POST'])
def api_clear_history():
    # 获取设备ID
    device_id = get_device_id()
    
    # 如果无法获取设备ID，返回错误
    if device_id is None:
        print("Clear history failed: Unable to get device ID.")
        return jsonify({'success': False, 'message': 'Unable to get device ID'}), 400

    print(f"Attempting to clear history for device ID: {device_id}")

    try:
        # 从数据库中删除该设备的所有历史记录
        # 在 v2.x 中，成功的 delete() 通常返回 APIResponse 对象，
        # 如果数据库层面有错误（如RLS策略限制），会抛出异常。
        response = supabase.table(HISTORY_TABLE).delete().eq('device_id', device_id).execute()

        # 如果 execute() 没有抛出异常，认为请求已成功发送到 Supabase
        print(f"Supabase delete request sent successfully for device ID: {device_id}. Response data: {response.data}, Count: {response.count}")
        # 您可以使用 print(json.dumps(response.__dict__, indent=2, default=str)) 来调试查看原始结构

        # 清空内存中的历史记录 (可选，如果使用内存备用存储的话)
        if hasattr(app, 'memory_history'):
             # 只保留不匹配当前device_id的记录
             app.memory_history = [h for h in getattr(app, 'memory_history', []) if h.get('device_id') != device_id]
             print(f"Cleared memory history for device ID: {device_id}")

        # 返回成功响应
        return jsonify({'success': True, 'message': '历史记录清除请求已处理'}), 200

    except Exception as e:
        # 捕获数据库操作或程序内部异常
        print(f"Error clearing history from database for device ID {device_id}: {e}")
        return jsonify({
            "success": False,
            "message": "执行历史记录清除操作时发生错误",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True) 