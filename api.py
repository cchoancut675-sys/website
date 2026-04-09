from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import hashlib
import secrets
import random
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
import os

app = Flask(__name__)
CORS(app)

# ========== CONFIG ==========
ADMIN_KEY = "RyoAdmin2024@Key"  # ĐỔI MẬT KHẨU NÀY ĐI
DB_PATH = "keys.db"

# Khởi tạo mã hóa
def init_encryption():
    key_file = "secret.key"
    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            return Fernet(f.read())
    else:
        key = Fernet.generate_key()
        with open(key_file, "wb") as f:
            f.write(key)
        return Fernet(key)

cipher = init_encryption()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            key_id TEXT PRIMARY KEY,
            key_hash TEXT UNIQUE NOT NULL,
            key_full TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            used_by_ip TEXT,
            last_used TEXT
        )
    ''')
    conn.commit()
    conn.close()

def hash_key(key):
    return hashlib.sha256(key.encode()).hexdigest()

init_db()

@app.route('/api/verify', methods=['POST'])
def verify_key():
    data = request.get_json()
    if not data or 'key' not in data:
        return jsonify({"success": False, "message": "Thiếu key"}), 400
    
    key_value = data['key'].strip()
    if not key_value.startswith("ryo_"):
        key_value = f"ryo_{key_value}"
    
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    key_hash = hash_key(key_value)
    cursor.execute("SELECT key_id, expires_at, is_active, used_by_ip FROM keys WHERE key_hash = ?", (key_hash,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        return jsonify({"success": False, "message": "Key không tồn tại"})
    
    key_id, expires_at, is_active, used_ip_encrypted = result
    
    if not is_active:
        conn.close()
        return jsonify({"success": False, "message": "Key đã bị khóa"})
    
    expire_time = datetime.fromisoformat(expires_at)
    if datetime.now() > expire_time:
        conn.close()
        return jsonify({"success": False, "message": "Key đã hết hạn"})
    
    # Giải mã IP
    used_ip = None
    if used_ip_encrypted:
        try:
            used_ip = cipher.decrypt(used_ip_encrypted.encode()).decode()
        except:
            pass
    
    if used_ip and used_ip != client_ip:
        conn.close()
        return jsonify({"success": False, "message": f"Key đã dùng ở IP khác: {used_ip}"})
    
    if not used_ip:
        encrypted_ip = cipher.encrypt(client_ip.encode()).decode()
        cursor.execute("UPDATE keys SET used_by_ip = ?, last_used = ? WHERE key_hash = ?", 
                      (encrypted_ip, datetime.now().isoformat(), key_hash))
        conn.commit()
    
    conn.close()
    return jsonify({"success": True, "message": "Xác thực thành công", "expires_at": expires_at})

@app.route('/api/add_key', methods=['POST'])
def add_key():
    data = request.get_json()
    admin_key = data.get('admin_key', '')
    
    if admin_key != ADMIN_KEY:
        return jsonify({"success": False, "message": "Admin key không đúng"}), 403
    
    days = data.get('days', 30)
    key_suffix = ''.join([str(random.randint(0, 9)) for _ in range(random.randint(8, 12))])
    raw_key = f"ryo_{key_suffix}"
    key_id = secrets.token_hex(8)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO keys (key_id, key_hash, key_full, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (key_id, hash_key(raw_key), raw_key, "web_admin", datetime.now().isoformat(), 
         (datetime.now() + timedelta(days=days)).isoformat())
    )
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "key": raw_key, "expires_in": f"{days} ngày"})

@app.route('/api/list_keys', methods=['POST'])
def list_keys():
    data = request.get_json()
    admin_key = data.get('admin_key', '')
    
    if admin_key != ADMIN_KEY:
        return jsonify({"success": False, "message": "Admin key không đúng"}), 403
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT key_full, created_at, expires_at, is_active, used_by_ip FROM keys ORDER BY created_at DESC")
    keys = cursor.fetchall()
    conn.close()
    
    key_list = []
    for key in keys:
        key_full, created_at, expires_at, is_active, used_ip_encrypted = key
        
        used_ip = None
        if used_ip_encrypted:
            try:
                used_ip = cipher.decrypt(used_ip_encrypted.encode()).decode()
            except:
                used_ip = "Lỗi giải mã"
        
        status = "active" if is_active and datetime.now() < datetime.fromisoformat(expires_at) else "expired" if datetime.now() > datetime.fromisoformat(expires_at) else "inactive"
        
        key_list.append({
            "key_full": key_full,
            "created_at": created_at,
            "expires_at": expires_at,
            "status": status,
            "used_ip": used_ip or "Chưa sử dụng"
        })
    
    return jsonify({"success": True, "keys": key_list})

@app.route('/api/stats', methods=['POST'])
def get_stats():
    data = request.get_json()
    admin_key = data.get('admin_key', '')
    
    if admin_key != ADMIN_KEY:
        return jsonify({"success": False, "message": "Admin key không đúng"}), 403
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM keys")
    total_keys = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM keys WHERE is_active = 1")
    active_keys = cursor.fetchone()[0]
    
    now = datetime.now().isoformat()
    cursor.execute("SELECT COUNT(*) FROM keys WHERE expires_at < ? AND is_active = 1", (now,))
    expired_keys = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM keys WHERE used_by_ip IS NOT NULL")
    used_keys = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        "success": True,
        "stats": {
            "total_keys": total_keys,
            "active_keys": active_keys,
            "expired_keys": expired_keys,
            "used_keys": used_keys
        }
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=20251)