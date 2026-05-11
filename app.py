from flask import Flask, render_template_string, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import secrets
import json
import subprocess
import tempfile
import os
import sys
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hoisting.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# সার্ভার স্টেট
server_status = {'is_running': False, 'start_time': None, 'active_bots': []}

# ======================== ডাটাবেস মডেল ========================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    plan = db.Column(db.String(20), default='24h')
    plan_activated_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    code_files = db.Column(db.Text, default='[]')  # JSON ফাইল স্টোরেজ
    bot_processes = db.Column(db.Text, default='[]')

class BotProcess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    bot_name = db.Column(db.String(200))
    filename = db.Column(db.String(200))
    pid = db.Column(db.Integer)
    status = db.Column(db.String(20), default='stopped')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ======================== HTML টেমপ্লেট ========================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hoisting Bot Server | IFTEKHAR - Real Python Runner</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
        body {
            min-height: 100vh;
            background: linear-gradient(135deg, #0a0e2a 0%, #060b1f 100%);
            padding: 1rem;
        }
        .cyber-bg {
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background-image: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,255,255,0.03) 2px, rgba(0,255,255,0.03) 4px);
            pointer-events: none;
            z-index: 0;
        }
        .container { position: relative; z-index: 10; max-width: 1400px; margin: 0 auto; }
        
        .auth-card {
            background: rgba(8,18,38,0.95);
            backdrop-filter: blur(16px);
            border-radius: 2rem;
            border: 1px solid rgba(0,255,255,0.4);
            max-width: 480px;
            margin: 8vh auto;
            padding: 2rem;
        }
        .iftekhar-logo {
            font-size: 2rem;
            font-weight: 800;
            text-align: center;
            background: linear-gradient(135deg, #fff, #0ff, #f0f);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
        }
        .tab-switch { display: flex; gap: 1rem; margin: 1.5rem 0; border-bottom: 1px solid #2f4a7a; }
        .tab-btn { flex: 1; background: none; border: none; padding: 0.8rem; color: #8aa9d4; font-weight: 600; cursor: pointer; }
        .tab-btn.active { color: #0ff; border-bottom: 2px solid #0ff; }
        .auth-form { display: none; }
        .auth-form.active { display: block; }
        .input-field {
            width: 100%; background: #0a1a2ee0; border: 1px solid #2f6080;
            padding: 0.8rem; border-radius: 1rem; color: white; margin: 0.5rem 0 1rem;
        }
        .auth-btn {
            width: 100%; background: linear-gradient(95deg, #00c6ff, #2575fc);
            border: none; padding: 0.8rem; border-radius: 1.5rem;
            font-weight: bold; color: white; cursor: pointer;
        }
        
        .dashboard {
            display: none;
            background: rgba(6,14,28,0.92);
            backdrop-filter: blur(12px);
            border-radius: 1.5rem;
            border: 1px solid #2f6a8a;
            overflow: hidden;
        }
        .dashboard-header {
            display: flex; justify-content: space-between; align-items: center;
            flex-wrap: wrap; padding: 1.2rem 1.8rem;
            background: #030e1ce0; border-bottom: 1px solid #2f6080;
        }
        .plan-selector {
            padding: 1rem 1.8rem; background: #051020aa;
            border-bottom: 1px solid #2f4a6a;
            display: flex; gap: 1rem; flex-wrap: wrap;
        }
        .plan-badge {
            background: #0a1a2e; padding: 0.5rem 1.2rem;
            border-radius: 2rem; cursor: pointer;
            border: 1px solid #3a6a8a;
        }
        .plan-badge.active-plan { background: #0ff22a; border-color: #0ff; color: #000; font-weight: bold; }
        .main-layout { display: flex; flex-wrap: wrap; }
        .sidebar {
            width: 260px; background: #020c1ae0;
            border-right: 1px solid #2f6080; padding: 1rem 0;
        }
        .sidebar-item {
            padding: 0.8rem 1.5rem; cursor: pointer;
            color: #bbd4ff; border-left: 3px solid transparent;
        }
        .sidebar-item:hover, .sidebar-item.active {
            background: #0f2a4a; border-left-color: #0ff; color: #0ff;
        }
        .content-area { flex: 1; padding: 1.8rem; min-height: 550px; }
        .action-buttons { display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
        .action-btn {
            background: #1f4f6f; border: none; padding: 0.7rem 1.5rem;
            border-radius: 2rem; color: white; cursor: pointer;
            font-weight: bold;
        }
        .action-btn.danger { background: #dc3545; }
        .action-btn.success { background: #28a745; }
        .action-btn.warning { background: #ffc107; color: #000; }
        .action-btn.primary { background: #007bff; }
        .info-card {
            background: #0a1430aa;
            border-radius: 1rem;
            padding: 1.2rem;
            margin-bottom: 1.2rem;
        }
        .server-status-card {
            background: #0a1a3a;
            border-radius: 1rem;
            padding: 1rem;
            margin-bottom: 1.5rem;
            text-align: center;
        }
        .status-badge {
            display: inline-block;
            padding: 0.3rem 1rem;
            border-radius: 2rem;
            font-size: 0.8rem;
            font-weight: bold;
        }
        .status-running { background: #28a745; color: white; }
        .status-stopped { background: #dc3545; color: white; }
        .code-editor {
            background: #0a0f1a;
            border-radius: 0.8rem;
            padding: 1rem;
            font-family: 'Fira Code', monospace;
            border: 1px solid #2f6a8a;
        }
        .toast-msg {
            position: fixed;
            bottom: 20px;
            right: 20px;
            padding: 0.8rem 1.5rem;
            border-radius: 2rem;
            z-index: 100;
            color: white;
            font-weight: bold;
        }
        .logout-btn { background: #ff5566aa; padding: 0.4rem 1rem; border-radius: 2rem; cursor: pointer; }
        .output-area {
            background: #010a14;
            border-radius: 0.5rem;
            padding: 1rem;
            font-family: monospace;
            font-size: 0.8rem;
            margin-top: 1rem;
            max-height: 200px;
            overflow-y: auto;
        }
    </style>
</head>
<body>
<div class="cyber-bg"></div>
<div class="container">
    <div id="authCard" class="auth-card">
        <div class="iftekhar-logo">⚡ IFTEKHAR ⚡</div>
        <div style="text-align: center; color: #8ac4ff;">PYTHON BOT HOSTING SERVER</div>
        <div class="demo-note" style="background:#ffc10720; padding:0.5rem; border-radius:0.5rem; margin-bottom:1rem;">
            📢 <strong>ডেমো লগইন:</strong> demo@hoist.com / 123456
        </div>
        <div class="tab-switch">
            <button class="tab-btn active" data-tab="login">🔐 লগইন</button>
            <button class="tab-btn" data-tab="register">📝 রেজিস্টার</button>
        </div>
        <div id="loginForm" class="auth-form active">
            <form id="loginAuthForm">
                <input type="email" id="loginEmail" class="input-field" placeholder="Gmail" value="demo@hoist.com">
                <input type="password" id="loginPassword" class="input-field" placeholder="পাসওয়ার্ড" value="123456">
                <button type="submit" class="auth-btn">🚀 প্রবেশ করুন</button>
            </form>
        </div>
        <div id="registerForm" class="auth-form">
            <form id="registerAuthForm">
                <input type="text" id="regName" class="input-field" placeholder="নাম">
                <input type="email" id="regEmail" class="input-field" placeholder="Gmail">
                <input type="password" id="regPassword" class="input-field" placeholder="পাসওয়ার্ড">
                <button type="submit" class="auth-btn">✅ একাউন্ট তৈরি</button>
            </form>
        </div>
    </div>

    <div id="dashboard" class="dashboard">
        <div class="dashboard-header">
            <div><h2 style="color:#aaf0ff;">🐍 PYTHON BOT HOSTING</h2><small>IFTEKHAR | আসল Python কোড রান করান</small></div>
            <div><span id="userEmailDisplay"></span><button id="logoutMainBtn" class="logout-btn">⛁ লগআউট</button></div>
        </div>
        <div class="plan-selector" id="planSelector">
            <div class="plan-badge" data-plan="24h">⏱️ ২৪ ঘন্টা (ফ্রি)</div>
            <div class="plan-badge" data-plan="7d">📅 ৭ দিন (ফ্রি)</div>
            <div class="plan-badge" data-plan="1m">🌟 ১ মাস (ফ্রি)</div>
        </div>
        <div class="main-layout">
            <div class="sidebar">
                <div class="sidebar-item active" data-tab="overview">📊 Overview</div>
                <div class="sidebar-item" data-tab="code">🐍 Python Code Runner</div>
                <div class="sidebar-item" data-tab="files">📁 My Files</div>
                <div class="sidebar-item" data-tab="bots">🤖 My Bots</div>
                <div class="sidebar-item" data-tab="settings">⚙️ Settings</div>
            </div>
            <div class="content-area" id="dynamicContent">Loading...</div>
        </div>
    </div>
</div>
<div id="toastMsg" style="display:none;" class="toast-msg"></div>

<script>
    let currentTab = 'overview';
    let currentUser = null;
    let serverRunning = false;
    let currentPlan = '24h';
    let codeFiles = [];
    
    function showToast(msg, isError=false) {
        const toast = document.getElementById('toastMsg');
        toast.style.backgroundColor = isError ? '#dc3545' : '#28a745';
        toast.innerText = msg;
        toast.style.display = 'block';
        setTimeout(() => toast.style.display = 'none', 3000);
    }
    
    async function apiCall(url, method, data) {
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: data ? JSON.stringify(data) : undefined
        });
        return await res.json();
    }
    
    async function loadContent(tab) {
        const res = await fetch(`/api/content/${tab}`);
        const data = await res.json();
        document.getElementById('dynamicContent').innerHTML = data.html;
        attachEvents();
    }
    
    async function runPythonCode(code, filename) {
        const res = await apiCall('/api/run_code', 'POST', { code: code, filename: filename });
        const outputDiv = document.getElementById('outputArea');
        if(outputDiv) {
            outputDiv.innerHTML = `<strong>📤 আউটপুট:</strong><br><pre style="color:#aaffaa;">${res.output || res.error || 'কোনো আউটপুট নেই'}</pre>`;
        }
        showToast(res.message);
        return res;
    }
    
    async function saveCodeFile(name, code) {
        const res = await apiCall('/api/save_code', 'POST', { name: name, code: code });
        showToast(res.message);
        if(currentTab === 'files') loadContent('files');
        return res;
    }
    
    async function startBot(filename) {
        const res = await apiCall('/api/start_bot', 'POST', { filename: filename });
        showToast(res.message);
        if(currentTab === 'bots') loadContent('bots');
    }
    
    async function stopBot(botId) {
        const res = await apiCall('/api/stop_bot', 'POST', { bot_id: botId });
        showToast(res.message);
        if(currentTab === 'bots') loadContent('bots');
    }
    
    function attachEvents() {
        const runBtn = document.getElementById('runCodeBtn');
        if(runBtn) {
            runBtn.onclick = async () => {
                const code = document.getElementById('pythonCodeEditor')?.value;
                if(code) await runPythonCode(code, 'temp.py');
            };
        }
        const saveBtn = document.getElementById('saveCodeBtn');
        if(saveBtn) {
            saveBtn.onclick = async () => {
                const name = document.getElementById('filenameInput')?.value;
                const code = document.getElementById('pythonCodeEditor')?.value;
                if(name && code) await saveCodeFile(name, code);
                else showToast('ফাইলের নাম এবং কোড দিন!', true);
            };
        }
        const startBtns = document.querySelectorAll('.start-bot-btn');
        startBtns.forEach(btn => {
            btn.onclick = () => startBot(btn.dataset.filename);
        });
        const stopBtns = document.querySelectorAll('.stop-bot-btn');
        stopBtns.forEach(btn => {
            btn.onclick = () => stopBot(btn.dataset.botid);
        });
    }
    
    async function changePlan(plan) {
        const res = await apiCall('/api/change_plan', 'POST', { plan });
        showToast(res.message);
        document.querySelectorAll('.plan-badge').forEach(b => b.classList.remove('active-plan'));
        document.querySelector(`.plan-badge[data-plan="${plan}"]`).classList.add('active-plan');
    }
    
    async function checkAuth() {
        const res = await apiCall('/api/check_auth', 'GET');
        if(res.logged_in) {
            document.getElementById('authCard').style.display = 'none';
            document.getElementById('dashboard').style.display = 'block';
            document.getElementById('userEmailDisplay').innerHTML = `👤 ${res.name} (${res.email})`;
            document.querySelectorAll('.plan-badge').forEach(b => {
                if(b.dataset.plan === res.plan) b.classList.add('active-plan');
                b.onclick = () => changePlan(b.dataset.plan);
            });
            loadContent('overview');
        } else {
            document.getElementById('authCard').style.display = 'block';
            document.getElementById('dashboard').style.display = 'none';
        }
    }
    
    document.querySelectorAll('.sidebar-item').forEach(item => {
        item.onclick = () => {
            document.querySelectorAll('.sidebar-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            currentTab = item.dataset.tab;
            loadContent(currentTab);
        };
    });
    
    document.getElementById('loginAuthForm').onsubmit = async (e) => {
        e.preventDefault();
        const res = await apiCall('/api/login', 'POST', {
            email: document.getElementById('loginEmail').value,
            password: document.getElementById('loginPassword').value
        });
        if(res.success) { showToast('লগইন সফল!'); checkAuth(); }
        else showToast(res.message, true);
    };
    document.getElementById('registerAuthForm').onsubmit = async (e) => {
        e.preventDefault();
        const res = await apiCall('/api/register', 'POST', {
            name: document.getElementById('regName').value,
            email: document.getElementById('regEmail').value,
            password: document.getElementById('regPassword').value
        });
        showToast(res.message);
        if(res.success) document.querySelector('.tab-btn[data-tab="login"]').click();
    };
    document.getElementById('logoutMainBtn').onclick = async () => {
        await apiCall('/api/logout', 'POST');
        checkAuth();
    };
    
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.onclick = () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('loginForm').classList.toggle('active', btn.dataset.tab === 'login');
            document.getElementById('registerForm').classList.toggle('active', btn.dataset.tab === 'register');
        };
    });
    
    checkAuth();
</script>
</body>
</html>
'''

# ======================== Flask রাউট ========================
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/check_auth')
def check_auth():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            return {'logged_in': True, 'name': user.name, 'email': user.email, 'plan': user.plan}
    return {'logged_in': False}

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(email=data['email']).first():
        return {'success': False, 'message': 'ইমেইল ইতিমধ্যে আছে!'}
    user = User(
        name=data['name'],
        email=data['email'],
        password=data['password'],
        code_files='[]'
    )
    db.session.add(user)
    db.session.commit()
    return {'success': True, 'message': 'রেজিস্ট্রেশন সফল!'}

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(email=data['email'], password=data['password']).first()
    if user:
        session['user_id'] = user.id
        return {'success': True, 'message': 'লগইন সফল'}
    return {'success': False, 'message': 'ভুল তথ্য!'}

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return {'success': True}

@app.route('/api/change_plan', methods=['POST'])
def change_plan():
    if 'user_id' not in session:
        return {'message': 'লগইন করুন'}
    user = User.query.get(session['user_id'])
    user.plan = request.json['plan']
    user.plan_activated_at = datetime.utcnow()
    db.session.commit()
    return {'message': 'প্ল্যান পরিবর্তন করা হয়েছে!'}

@app.route('/api/run_code', methods=['POST'])
def run_code():
    if 'user_id' not in session:
        return {'message': 'লগইন করুন', 'output': ''}
    
    data = request.json
    code = data.get('code', '')
    filename = data.get('filename', 'temp.py')
    
    try:
        # টেম্পোরারি ফাইল তৈরি
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        # পাইথন কোড রান
        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # টেম্প ফাইল ডিলিট
        os.unlink(temp_file)
        
        output = result.stdout if result.stdout else result.stderr
        if not output:
            output = '✅ কোড সফলভাবে রান হয়েছে (কোনো আউটপুট নেই)'
        
        return {'message': 'কোড রান সফল!', 'output': output}
    
    except subprocess.TimeoutExpired:
        return {'message': 'কোড রান টাইমআউট!', 'output': '⏰ কোড 30 সেকেন্ডে শেষ হয়নি', 'error': True}
    except Exception as e:
        return {'message': f'এরর: {str(e)}', 'output': str(e), 'error': True}

@app.route('/api/save_code', methods=['POST'])
def save_code():
    if 'user_id' not in session:
        return {'message': 'লগইন করুন'}
    
    user = User.query.get(session['user_id'])
    files = json.loads(user.code_files) if user.code_files else []
    
    data = request.json
    name = data.get('name')
    code = data.get('code')
    
    # পুরনো ফাইল আপডেট বা নতুন যোগ
    existing = next((f for f in files if f['name'] == name), None)
    if existing:
        existing['code'] = code
        existing['updated_at'] = datetime.utcnow().isoformat()
    else:
        files.append({
            'name': name,
            'code': code,
            'created_at': datetime.utcnow().isoformat()
        })
    
    user.code_files = json.dumps(files)
    db.session.commit()
    return {'message': f'{name} সেভ করা হয়েছে!'}

@app.route('/api/start_bot', methods=['POST'])
def start_bot():
    if 'user_id' not in session:
        return {'message': 'লগইন করুন'}
    
    user = User.query.get(session['user_id'])
    filename = request.json.get('filename')
    files = json.loads(user.code_files) if user.code_files else []
    
    file_data = next((f for f in files if f['name'] == filename), None)
    if not file_data:
        return {'message': 'ফাইল পাওয়া যায়নি!'}
    
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(file_data['code'])
            temp_file = f.name
        
        # ব্যাকগ্রাউন্ডে প্রসেস স্টার্ট
        process = subprocess.Popen(
            [sys.executable, temp_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # বট প্রসেস সেভ
        bot = BotProcess(
            user_id=user.id,
            bot_name=filename,
            filename=temp_file,
            pid=process.pid,
            status='running'
        )
        db.session.add(bot)
        db.session.commit()
        
        return {'message': f'{filename} স্টার্ট করা হয়েছে! PID: {process.pid}'}
    
    except Exception as e:
        return {'message': f'স্টার্ট করতে ব্যর্থ: {str(e)}'}

@app.route('/api/stop_bot', methods=['POST'])
def stop_bot():
    if 'user_id' not in session:
        return {'message': 'লগইন করুন'}
    
    bot_id = request.json.get('bot_id')
    bot = BotProcess.query.get(bot_id)
    
    if not bot or bot.user_id != session['user_id']:
        return {'message': 'বট পাওয়া যায়নি!'}
    
    try:
        import signal
        os.kill(bot.pid, signal.SIGTERM)
        bot.status = 'stopped'
        db.session.commit()
        return {'message': f'{bot.bot_name} বন্ধ করা হয়েছে!'}
    except Exception as e:
        return {'message': f'বন্ধ করতে ব্যর্থ: {str(e)}'}

@app.route('/api/content/<tab>')
def get_content(tab):
    if 'user_id' not in session:
        return {'html': '<p>লগইন করুন</p>'}
    
    user = User.query.get(session['user_id'])
    files = json.loads(user.code_files) if user.code_files else []
    bots = BotProcess.query.filter_by(user_id=user.id).all()
    
    if tab == 'overview':
        html = f'''
        <div class="server-status-card">
            <span class="status-badge status-running">🟢 সার্ভার অনলাইন</span>
            <div style="margin-top:0.5rem;">🐍 পাইথন রানটাইম: {sys.version.split()[0]}</div>
        </div>
        <div class="info-card">
            <h3>📊 সার্ভার ওভারভিউ</h3>
            <p>📦 প্ল্যান: <strong>{user.plan}</strong> (ফ্রি)</p>
            <p>📁 মোট ফাইল: {len(files)}</p>
            <p>🤖 চলমান বট: {len([b for b in bots if b.status == 'running'])}</p>
            <p>🐍 পাইথন ভার্সন: {sys.version.split()[0]}</p>
        </div>
        <div class="info-card">
            <h4>💡 কিভাবে ব্যবহার করবেন:</h4>
            <p>1️⃣ "Python Code Runner" ট্যাবে গিয়ে কোড লিখুন</p>
            <p>2️⃣ "Run Code" বাটন চাপুন - আউটপুট দেখুন</p>
            <p>3️⃣ "Save Code" করে ফাইল সংরক্ষণ করুন</p>
            <p>4️⃣ "My Bots" এ গিয়ে বট স্টার্ট করুন</p>
        </div>
        '''
    
    elif tab == 'code':
        html = f'''
        <h3>🐍 Python Code Runner</h3>
        <div class="code-editor">
            <textarea id="pythonCodeEditor" rows="12" style="width:100%; background:#010c18; color:#c0e0ff; border:none; font-family: monospace; padding:0.5rem;"># আপনার পাইথন কোড লিখুন
print("Hello from IFTEKHAR Bot Server!")

# উদাহরণ: লুপ
for i in range(5):
    print(f"Hoisting bot iteration {{i}}")

# ফাংশন
def greet(name):
    return f"Hello, {{name}}!"
    
print(greet("IFTEKHAR"))
</textarea>
            <div style="margin-top:1rem;">
                <input type="text" id="filenameInput" class="input-field" placeholder="ফাইলের নাম (যেমন: my_bot.py)" style="width:60%; display:inline-block;">
                <button id="saveCodeBtn" class="action-btn success">💾 সেভ</button>
                <button id="runCodeBtn" class="action-btn primary">▶️ রান</button>
            </div>
            <div id="outputArea" class="output-area">
                <strong>📤 আউটপুট এখানে দেখাবে:</strong><br>
                <span style="color:#888;">কোড রান করুন...</span>
            </div>
        </div>
        '''
    
    elif tab == 'files':
        files_html = ''
        for f in files:
            files_html += f'''
            <div class="file-item">
                <span>📄 {f['name']} - {f.get('created_at', '')[:19]}</span>
                <div>
                    <button class="action-btn" onclick="document.getElementById('pythonCodeEditor').value = atob('{f['code'][:500]}')">✏️ এডিট</button>
                </div>
            </div>
            '''
        html = f'''
        <h3>📁 আমার কোড ফাইল</h3>
        <div class="info-card">
            {files_html if files_html else '<p>কোনো ফাইল নেই। কোড রানার ট্যাবে গিয়ে ফাইল সেভ করুন!</p>'}
        </div>
        '''
    
    elif tab == 'bots':
        bots_html = ''
        for bot in bots:
            bots_html += f'''
            <div class="file-item">
                <span>🤖 {bot.bot_name} - {bot.status} - PID: {bot.pid}</span>
                <div>
                    {f'<button class="stop-bot-btn action-btn danger" data-botid="{bot.id}">⏹️ স্টপ</button>' if bot.status == 'running' else '<span class="status-badge status-stopped">স্টপড</span>'}
                </div>
            </div>
            '''
        html = f'''
        <h3>🤮 আমার বট প্রসেস</h3>
        <div class="info-card">
            {bots_html if bots_html else '<p>কোনো বট চলছে না। ফাইল সেভ করে বট স্টার্ট করুন!</p>'}
            <p style="margin-top:1rem;"><small>⚠️ বট স্টার্ট করতে: "Files" ট্যাবে ফাইল সেভ করুন, তারপর এখানে স্টার্ট হবে।</small></p>
        </div>
        '''
    
    else:
        html = f'''
        <h3>⚙️ সেটিংস</h3>
        <div class="info-card">
            <label>ইউজারনেম</label>
            <input type="text" class="input-field" value="{user.name}" readonly>
            <label>ইমেইল</label>
            <input type="email" class="input-field" value="{user.email}" readonly>
            <label>অ্যাকাউন্ট তৈরি</label>
            <input type="text" class="input-field" value="{user.created_at}" readonly>
        </div>
        <div class="danger-zone">
            <h4>⚠️ অ্যাকাউন্ট ডিলিট</h4>
            <button id="deleteAccountBtn" class="delete-btn">🗑️ অ্যাকাউন্ট ডিলিট</button>
        </div>
        '''
    
    return {'html': html}

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║     🐍 PYTHON BOT HOSTING SERVER - IFTEKHAR                  ║
    ║     http://localhost:5000                                    ║
    ║     লগইন: demo@hoist.com / 123456                           ║
    ║     📝 আপনি এখন আসল Python কোড রান করতে পারবেন!              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    app.run(debug=True, host='0.0.0.0', port=5000)