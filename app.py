from flask import Flask, render_template_string, request, session, jsonify
from datetime import datetime, timedelta
import secrets
import json
import subprocess
import tempfile
import os
import sys
import threading
import time
import socket

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)

# সিম্পল ইউজার স্টোরেজ
users_db = {
    'demo@hoist.com': {'name': 'Demo User', 'password': '123456', 'plan': '24h', 'created_at': str(datetime.utcnow())}
}

# ======================== HTML টেমপ্লেট ========================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IFTEKHAR 3.0 - Python Bot Hosting</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
        body {
            min-height: 100vh;
            background: linear-gradient(135deg, #0a0e2a 0%, #060b1f 100%);
            padding: 1rem;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .card {
            background: rgba(8,18,38,0.95);
            backdrop-filter: blur(16px);
            border-radius: 1.5rem;
            border: 1px solid rgba(0,255,255,0.4);
            padding: 2rem;
            margin-bottom: 1rem;
            box-shadow: 0 0 20px rgba(0,255,255,0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 2rem;
        }
        h1 {
            background: linear-gradient(135deg, #fff, #0ff, #f0f);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            font-size: 2.5rem;
        }
        .version-badge {
            display: inline-block;
            background: #ff00ff20;
            border: 1px solid #0ff;
            border-radius: 2rem;
            padding: 0.3rem 1rem;
            margin-top: 0.5rem;
            color: #0ff;
        }
        .input-field {
            width: 100%;
            background: #0a1a2ee0;
            border: 1px solid #2f6080;
            padding: 0.8rem;
            border-radius: 0.5rem;
            color: white;
            margin: 0.5rem 0;
        }
        .btn {
            background: linear-gradient(95deg, #00c6ff, #2575fc);
            border: none;
            padding: 0.8rem 1.5rem;
            border-radius: 2rem;
            color: white;
            cursor: pointer;
            margin: 0.5rem;
            font-weight: bold;
            transition: transform 0.2s;
        }
        .btn:hover {
            transform: scale(1.05);
        }
        .btn-danger { background: linear-gradient(95deg, #ff416c, #ff4b2b); }
        .btn-success { background: linear-gradient(95deg, #00b09b, #96c93d); }
        .code-editor {
            background: #0a0f1a;
            border-radius: 0.5rem;
            padding: 1rem;
            font-family: monospace;
            border: 1px solid #2f6a8a;
        }
        textarea {
            width: 100%;
            background: #010c18;
            color: #c0e0ff;
            border: none;
            font-family: monospace;
            padding: 0.5rem;
            font-size: 14px;
        }
        .output {
            background: #010a14;
            border-radius: 0.5rem;
            padding: 1rem;
            font-family: monospace;
            margin-top: 1rem;
            border-left: 3px solid #0ff;
        }
        .status {
            display: inline-block;
            padding: 0.3rem 1rem;
            border-radius: 2rem;
            font-size: 0.8rem;
        }
        .status-online { background: #28a745; color: white; }
        .url-box {
            background: #0a1a2e;
            border-radius: 0.5rem;
            padding: 0.8rem;
            text-align: center;
            margin-bottom: 1rem;
            border: 1px solid #0ff;
        }
        .url-text {
            color: #0ff;
            font-size: 1.2rem;
            font-family: monospace;
        }
    </style>
</head>
<body>
<div class="container">
    <div class="card">
        <div class="header">
            <h1>🐍 IFTEKHAR 3.0</h1>
            <div class="version-badge">⚡ NEXT GEN PYTHON BOT HOSTING ⚡</div>
            <p style="margin-top: 1rem;">আসল Python কোড রান করুন - সম্পূর্ণ ফ্রি!</p>
            <div class="url-box">
                <span style="color:#8aa9d4;">🌐 আপনার URL: </span>
                <span class="url-text" id="serverUrl">iftekhar3.0:5000</span>
            </div>
        </div>
        
        <div id="loginSection">
            <input type="email" id="loginEmail" class="input-field" placeholder="Email" value="demo@hoist.com">
            <input type="password" id="loginPassword" class="input-field" placeholder="Password" value="123456">
            <button onclick="login()" class="btn">🔐 লগইন করুন</button>
            <button onclick="showRegister()" class="btn">📝 নতুন রেজিস্টার</button>
        </div>
        
        <div id="registerSection" style="display:none;">
            <input type="text" id="regName" class="input-field" placeholder="আপনার নাম">
            <input type="email" id="regEmail" class="input-field" placeholder="Email">
            <input type="password" id="regPassword" class="input-field" placeholder="পাসওয়ার্ড">
            <button onclick="register()" class="btn btn-success">✅ রেজিস্টার করুন</button>
            <button onclick="hideRegister()" class="btn">◀️ পিছনে যান</button>
        </div>
        
        <div id="dashboard" style="display:none;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <h3>📊 IFTEKHAR 3.0 ড্যাশবোর্ড</h3>
                <button onclick="logout()" class="btn btn-danger">🚪 লগআউট</button>
            </div>
            
            <div class="card" style="margin-top: 1rem;">
                <h3>🐍 Python কোড রান করুন</h3>
                <div class="code-editor">
                    <textarea id="pythonCode" rows="12" placeholder="# আপনার Python কোড লিখুন
print('Welcome to IFTEKHAR 3.0!')
print('Python Bot Hosting')

# উদাহরণ কোড
name = 'IFTEKHAR'
version = '3.0'
print(f'Server: {name} {version}')

# লুপ
for i in range(5):
    print(f'Bot iteration {i+1}')

# ফাংশন
def calculate(a, b):
    return a + b

result = calculate(10, 20)
print(f'Result: {result}')"></textarea>
                    <button onclick="runCode()" class="btn">▶️ রান করুন</button>
                </div>
                <div id="output" class="output">
                    📤 আউটপুট এখানে দেখাবে...
                </div>
            </div>
            
            <div class="card">
                <h3>ℹ️ সার্ভার তথ্য</h3>
                <p>🚀 সার্ভার নাম: <strong>IFTEKHAR 3.0</strong></p>
                <p>🐍 Python Version: <span id="pythonVer"></span></p>
                <p>🟢 সার্ভার স্ট্যাটাস: <span class="status status-online">অনলাইন</span></p>
                <p>✅ আপনি সত্যিকারের Python কোড রান করতে পারছেন!</p>
                <p>🔗 URL: <strong>http://iftekhar3.0:5000</strong> অথবা <strong>http://localhost:5000</strong></p>
            </div>
        </div>
    </div>
</div>

<script>
    async function apiCall(url, data) {
        const res = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        return await res.json();
    }
    
    async function login() {
        const email = document.getElementById('loginEmail').value;
        const password = document.getElementById('loginPassword').value;
        const res = await apiCall('/api/login', {email, password});
        if(res.success) {
            document.getElementById('loginSection').style.display = 'none';
            document.getElementById('dashboard').style.display = 'block';
            document.getElementById('pythonVer').innerText = res.python_version;
        } else {
            alert('❌ লগইন ব্যর্থ: ' + res.message);
        }
    }
    
    async function register() {
        const name = document.getElementById('regName').value;
        const email = document.getElementById('regEmail').value;
        const password = document.getElementById('regPassword').value;
        const res = await apiCall('/api/register', {name, email, password});
        alert(res.message);
        if(res.success) hideRegister();
    }
    
    async function runCode() {
        const code = document.getElementById('pythonCode').value;
        const outputDiv = document.getElementById('output');
        outputDiv.innerHTML = '⏳ কোড রান হচ্ছে... <span style="color:#0ff;">IFTEKHAR 3.0 Engine</span>';
        const res = await apiCall('/api/run_code', {code});
        outputDiv.innerHTML = '<strong>📤 আউটপুট:</strong><br><pre style="color:#aaffaa;">' + (res.output || res.message) + '</pre>';
    }
    
    async function logout() {
        await apiCall('/api/logout', {});
        document.getElementById('loginSection').style.display = 'block';
        document.getElementById('dashboard').style.display = 'none';
    }
    
    function showRegister() {
        document.getElementById('loginSection').style.display = 'none';
        document.getElementById('registerSection').style.display = 'block';
    }
    
    function hideRegister() {
        document.getElementById('registerSection').style.display = 'none';
        document.getElementById('loginSection').style.display = 'block';
    }
    
    // Check if already logged in
    fetch('/api/check').then(res => res.json()).then(data => {
        if(data.logged_in) {
            document.getElementById('loginSection').style.display = 'none';
            document.getElementById('dashboard').style.display = 'block';
            document.getElementById('pythonVer').innerText = data.python_version;
        }
    });
</script>
</body>
</html>
'''

# ======================== রাউট এবং API ========================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/check')
def check():
    if 'user_email' in session:
        return {'logged_in': True, 'email': session['user_email'], 'python_version': sys.version.split()[0]}
    return {'logged_in': False}

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    email = data.get('email')
    if email in users_db:
        return {'success': False, 'message': 'এই ইমেইল already আছে!'}
    
    users_db[email] = {
        'name': data.get('name'),
        'password': data.get('password'),
        'plan': '24h',
        'created_at': str(datetime.utcnow())
    }
    return {'success': True, 'message': '✅ রেজিস্ট্রেশন সফল! এখন লগইন করুন।'}

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    if email in users_db and users_db[email]['password'] == password:
        session['user_email'] = email
        return {'success': True, 'message': 'লগইন সফল!', 'python_version': sys.version.split()[0]}
    return {'success': False, 'message': 'ভুল ইমেইল বা পাসওয়ার্ড!'}

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_email', None)
    return {'success': True}

@app.route('/api/run_code', methods=['POST'])
def run_code():
    if 'user_email' not in session:
        return {'message': 'প্লিজ লগইন করুন!'}
    
    code = request.json.get('code', '')
    
    if not code.strip():
        return {'message': 'কোড দিন!', 'output': ''}
    
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        os.unlink(temp_file)
        
        output = result.stdout if result.stdout else result.stderr
        if not output:
            output = '✅ কোড সফলভাবে রান হয়েছে! (কোন আউটপুট নেই)'
        
        return {'message': 'সফল!', 'output': output}
    
    except subprocess.TimeoutExpired:
        os.unlink(temp_file)
        return {'message': 'টাইমআউট!', 'output': '⏰ কোড 10 সেকেন্ডে শেষ হয়নি'}
    except Exception as e:
        return {'message': f'এরর: {str(e)}', 'output': str(e)}

if __name__ == '__main__':
    # লোকাল হোস্টের জন্য iftekhar3.0 নাম সেট করা
    try:
        # আপনার hosts ফাইলে iftekhar3.0 যোগ করার নির্দেশনা
        print("""
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║                    🚀 IFTEKHAR 3.0 - PYTHON BOT HOSTING 🚀               ║
    ╠══════════════════════════════════════════════════════════════════════════╣
    ║                                                                          ║
    ║     🌐 URL: http://iftekhar3.0:5000                                      ║
    ║     🔑 লগইন: demo@hoist.com / 123456                                    ║
    ║                                                                          ║
    ║     📝 আপনি এখন আসল Python কোড রান করতে পারবেন!                          ║
    ║                                                                          ║
    ╠══════════════════════════════════════════════════════════════════════════╣
    ║     ⚠️  iftekhar3.0 কাজ করতে hosts ফাইলে এন্ট্রি দিন:                   ║
    ║                                                                          ║
    ║     Windows: C:\\Windows\\System32\\drivers\\etc\\hosts                   ║
    ║     যোগ করুন: 127.0.0.1    iftekhar3.0                                   ║
    ║                                                                          ║
    ║     Linux/Mac: /etc/hosts                                                ║
    ║     যোগ করুন: 127.0.0.1    iftekhar3.0                                   ║
    ║                                                                          ║
    ║     🎯 অথবা সরাসরি ব্যবহার করুন: http://localhost:5000                   ║
    ║                                                                          ║
    ╚══════════════════════════════════════════════════════════════════════════╝
        """)
    except:
        pass
    
    app.run(debug=True, host='0.0.0.0', port=5000)