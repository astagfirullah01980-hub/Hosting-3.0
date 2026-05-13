from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import zipfile
import os
import shutil
import uuid
import json
import subprocess
import sys
import signal
import psutil
import threading
import time
from functools import wraps
import requests
import jwt
import pytz
import asyncio
from pathlib import Path

app = Flask(__name__)
app.config['SECRET_KEY'] = 'iftekhar-super-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DEPLOYMENT_FOLDER'] = 'deployments'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'zip'}

db = SQLAlchemy(app)

# Create necessary folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DEPLOYMENT_FOLDER'], exist_ok=True)

# Store running processes
running_processes = {}
process_lock = threading.Lock()

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    storage_used = db.Column(db.Float, default=0.0)
    bots_deployed = db.Column(db.Integer, default=0)
    
    files = db.relationship('UploadedFile', backref='owner', lazy=True)
    bots = db.relationship('UserBot', backref='owner', lazy=True)

class UploadedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    file_size = db.Column(db.Float, default=0.0)
    file_path = db.Column(db.String(500), nullable=False)
    extracted_path = db.Column(db.String(500))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    extracted_files_count = db.Column(db.Integer, default=0)
    is_extracted = db.Column(db.Boolean, default=False)
    main_file_path = db.Column(db.String(500))
    platform = db.Column(db.String(20), default='python')

class UserBot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bot_name = db.Column(db.String(100), nullable=False)
    bot_type = db.Column(db.String(50), nullable=False)
    bot_status = db.Column(db.String(20), default='stopped')
    bot_port = db.Column(db.Integer)
    process_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    file_id = db.Column(db.Integer, db.ForeignKey('uploaded_file.id'), nullable=True)
    config = db.Column(db.Text)
    log_file = db.Column(db.String(500))

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    status = db.Column(db.String(20), default='success')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Create tables
with app.app_context():
    db.create_all()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first!', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_zip(zip_path, extract_to):
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            zip_ref.extractall(extract_to)
        return True, file_list, None
    except Exception as e:
        return False, [], str(e)

def find_main_file(directory, platform='python'):
    if platform == 'python':
        for root, dirs, files in os.walk(directory):
            if 'main.py' in files:
                return os.path.join(root, 'main.py')
            elif 'bot.py' in files:
                return os.path.join(root, 'bot.py')
            elif 'app.py' in files:
                return os.path.join(root, 'app.py')
        
        py_files = [f for f in os.listdir(directory) if f.endswith('.py')]
        if py_files:
            return os.path.join(directory, py_files[0])
        return None
    else:
        for root, dirs, files in os.walk(directory):
            if 'main.js' in files:
                return os.path.join(root, 'main.js')
            elif 'index.js' in files:
                return os.path.join(root, 'index.js')
            elif 'server.js' in files:
                return os.path.join(root, 'server.js')
        return None

def log_activity(user_id, action, details, status='success'):
    log = ActivityLog(user_id=user_id, action=action, details=details, status=status)
    db.session.add(log)
    db.session.commit()

def get_server_stats():
    return {
        'cpu_percent': psutil.cpu_percent(interval=0.5),
        'memory_percent': psutil.virtual_memory().percent,
        'memory_used': psutil.virtual_memory().used // (1024**2),
        'memory_total': psutil.virtual_memory().total // (1024**2),
        'disk_used': psutil.disk_usage('/').used // (1024**3),
        'disk_total': psutil.disk_usage('/').total // (1024**3),
        'running_processes': len(running_processes)
    }

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect(url_for('register'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters!', 'error')
            return redirect(url_for('register'))
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists!', 'error')
            return redirect(url_for('register'))
        
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            flash('Email already registered!', 'error')
            return redirect(url_for('register'))
        
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, password=hashed_password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['email'] = user.email
            log_activity(user.id, 'login', f'User {username} logged in')
            flash(f'Welcome back, {username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password!', 'error')
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    files = UploadedFile.query.filter_by(user_id=user.id).order_by(UploadedFile.upload_date.desc()).all()
    bots = UserBot.query.filter_by(user_id=user.id).all()
    
    total_files = len(files)
    total_size = sum([f.file_size for f in files])
    total_bots = len(bots)
    running_bots = len([b for b in bots if b.bot_status == 'running'])
    
    stats = {
        'total_files': total_files,
        'total_size': round(total_size, 2),
        'total_bots': total_bots,
        'running_bots': running_bots,
        'storage_limit': 1000,
        'storage_used': round(total_size, 2),
    }
    
    return render_template('dashboard.html', user=user, files=files[:5], bots=bots[:5], stats=stats, all_files=files)

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash('No file selected!', 'error')
        return redirect(url_for('dashboard'))
    
    file = request.files['file']
    platform = request.form.get('platform', 'python')
    
    if file.filename == '':
        flash('No file selected!', 'error')
        return redirect(url_for('dashboard'))
    
    if file and allowed_file(file.filename):
        user_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(session['user_id']))
        os.makedirs(user_folder, exist_ok=True)
        
        original_filename = file.filename
        filename = secure_filename(f"{uuid.uuid4().hex}_{original_filename}")
        file_path = os.path.join(user_folder, filename)
        
        file.save(file_path)
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        
        user = User.query.get(session['user_id'])
        user.storage_used += file_size
        db.session.commit()
        
        extracted_folder = os.path.join(user_folder, f"extracted_{uuid.uuid4().hex[:8]}")
        os.makedirs(extracted_folder, exist_ok=True)
        
        success, file_list, error = extract_zip(file_path, extracted_folder)
        
        main_file = None
        if success:
            main_file = find_main_file(extracted_folder, platform)
        
        uploaded_file = UploadedFile(
            filename=filename,
            original_filename=original_filename,
            file_size=file_size,
            file_path=file_path,
            extracted_path=extracted_folder,
            extracted_files_count=len(file_list) if success else 0,
            is_extracted=success,
            main_file_path=main_file,
            platform=platform,
            user_id=session['user_id']
        )
        
        db.session.add(uploaded_file)
        db.session.commit()
        
        log_activity(session['user_id'], 'upload', f'Uploaded {original_filename} (Platform: {platform})')
        
        if main_file:
            flash(f'✅ File uploaded! Found main file: {os.path.basename(main_file)}', 'success')
        else:
            flash(f'⚠️ File uploaded but no main file found!', 'warning')
        
    else:
        flash('Only ZIP files are allowed!', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/bot/<int:bot_id>/start', methods=['POST'])
@login_required
def start_bot(bot_id):
    bot = UserBot.query.get_or_404(bot_id)
    
    if bot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    if bot.bot_status == 'running':
        return jsonify({'success': False, 'message': 'Bot is already running!'})
    
    try:
        file_record = UploadedFile.query.get(bot.file_id)
        if not file_record or not file_record.main_file_path:
            return jsonify({'success': False, 'message': 'Bot files not found!'})
        
        if not os.path.exists(file_record.main_file_path):
            return jsonify({'success': False, 'message': 'Main file not found on disk!'})
        
        log_path = os.path.join(app.config['DEPLOYMENT_FOLDER'], f"bot_{bot.id}.log")
        bot.log_file = log_path
        
        if bot.bot_type == 'python':
            process = subprocess.Popen(
                [sys.executable, file_record.main_file_path],
                stdout=open(log_path, 'w'),
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(file_record.main_file_path),
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
        else:
            process = subprocess.Popen(
                ['node', file_record.main_file_path],
                stdout=open(log_path, 'w'),
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(file_record.main_file_path),
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
        
        with process_lock:
            running_processes[bot.id] = {
                'process': process,
                'pid': process.pid,
                'start_time': datetime.utcnow()
            }
        
        bot.process_id = process.pid
        bot.bot_status = 'running'
        bot.last_active = datetime.utcnow()
        db.session.commit()
        
        log_activity(session['user_id'], 'start_bot', f'Started bot: {bot.bot_name}')
        
        return jsonify({'success': True, 'message': 'Bot started successfully!', 'pid': process.pid})
    
    except Exception as e:
        bot.bot_status = 'error'
        db.session.commit()
        return jsonify({'success': False, 'message': f'Failed to start bot: {str(e)}'})

@app.route('/bot/<int:bot_id>/stop', methods=['POST'])
@login_required
def stop_bot(bot_id):
    bot = UserBot.query.get_or_404(bot_id)
    
    if bot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        with process_lock:
            if bot.id in running_processes:
                process_info = running_processes[bot.id]
                process = process_info['process']
                
                if os.name != 'nt':
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    process.terminate()
                
                process.wait(timeout=5)
                del running_processes[bot.id]
        
        bot.bot_status = 'stopped'
        bot.process_id = None
        bot.last_active = datetime.utcnow()
        db.session.commit()
        
        log_activity(session['user_id'], 'stop_bot', f'Stopped bot: {bot.bot_name}')
        
        return jsonify({'success': True, 'message': 'Bot stopped successfully!'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to stop bot: {str(e)}'})

@app.route('/bot/<int:bot_id>/logs', methods=['GET'])
@login_required
def get_bot_logs(bot_id):
    bot = UserBot.query.get_or_404(bot_id)
    
    if bot.user_id != session['user_id']:
        return jsonify({'error': 'Access denied'}), 403
    
    if bot.log_file and os.path.exists(bot.log_file):
        with open(bot.log_file, 'r') as f:
            lines = f.readlines()
            return jsonify({'logs': lines[-100:]})
    
    return jsonify({'logs': ['No logs available']})

@app.route('/deploy', methods=['POST'])
@login_required
def deploy_bot():
    data = request.get_json()
    file_id = data.get('file_id')
    bot_name = data.get('bot_name')
    platform = data.get('platform', 'python')
    
    file_record = UploadedFile.query.get_or_404(file_id)
    
    if file_record.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    if not file_record.main_file_path:
        return jsonify({'success': False, 'message': 'No main file found in this archive!'})
    
    new_bot = UserBot(
        bot_name=bot_name,
        bot_type=platform,
        bot_status='stopped',
        bot_port=5000 + len(UserBot.query.all()),
        user_id=session['user_id'],
        file_id=file_id,
        config=json.dumps({
            'deployed_at': datetime.utcnow().isoformat(),
            'main_file': file_record.main_file_path,
            'extracted_path': file_record.extracted_path
        })
    )
    
    db.session.add(new_bot)
    user = User.query.get(session['user_id'])
    user.bots_deployed += 1
    db.session.commit()
    
    log_activity(session['user_id'], 'deploy_bot', f'Deployed bot: {bot_name} (Platform: {platform})')
    
    return jsonify({'success': True, 'message': 'Bot deployed successfully!', 'bot_id': new_bot.id})

@app.route('/bot/<int:bot_id>/delete', methods=['DELETE'])
@login_required
def delete_bot(bot_id):
    bot = UserBot.query.get_or_404(bot_id)
    
    if bot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    if bot.bot_status == 'running':
        stop_bot(bot_id)
    
    db.session.delete(bot)
    user = User.query.get(session['user_id'])
    user.bots_deployed -= 1
    db.session.commit()
    
    log_activity(session['user_id'], 'delete_bot', f'Deleted bot: {bot.bot_name}')
    
    return jsonify({'success': True, 'message': 'Bot deleted successfully!'})

@app.route('/overview')
@login_required
def overview():
    return render_template('overview.html')

@app.route('/api/overview/stats')
@login_required
def get_overview_stats():
    user = User.query.get(session['user_id'])
    files = UploadedFile.query.filter_by(user_id=user.id).all()
    bots = UserBot.query.filter_by(user_id=user.id).all()
    logs = ActivityLog.query.filter_by(user_id=user.id).order_by(ActivityLog.created_at.desc()).limit(20).all()
    
    server_stats = get_server_stats()
    
    return jsonify({
        'user': {
            'username': user.username,
            'email': user.email,
            'bots_deployed': user.bots_deployed,
            'storage_used': round(user.storage_used, 2),
            'member_since': user.created_at.strftime('%Y-%m-%d')
        },
        'stats': {
            'total_files': len(files),
            'total_bots': len(bots),
            'running_bots': len([b for b in bots if b.bot_status == 'running']),
            'storage_percent': round((user.storage_used / 1000) * 100, 1) if user.storage_used > 0 else 0
        },
        'server': server_stats,
        'recent_activity': [{
            'action': log.action,
            'details': log.details,
            'time': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'status': log.status
        } for log in logs]
    })

@app.route('/api/overview/processes')
@login_required
def get_processes():
    processes = []
    with process_lock:
        for bot_id, info in running_processes.items():
            bot = UserBot.query.get(bot_id)
            if bot and bot.user_id == session['user_id']:
                try:
                    proc = psutil.Process(info['pid'])
                    processes.append({
                        'bot_id': bot_id,
                        'bot_name': bot.bot_name,
                        'pid': info['pid'],
                        'start_time': info['start_time'].strftime('%Y-%m-%d %H:%M:%S'),
                        'cpu_percent': proc.cpu_percent(interval=0.1),
                        'memory_mb': proc.memory_info().rss // (1024**2)
                    })
                except:
                    processes.append({
                        'bot_id': bot_id,
                        'bot_name': bot.bot_name,
                        'pid': info['pid'],
                        'start_time': info['start_time'].strftime('%Y-%m-%d %H:%M:%S'),
                        'cpu_percent': 0,
                        'memory_mb': 0
                    })
    return jsonify(processes)

@app.route('/api/files')
@login_required
def get_files():
    files = UploadedFile.query.filter_by(user_id=session['user_id']).order_by(UploadedFile.upload_date.desc()).all()
    return jsonify([{
        'id': f.id,
        'name': f.original_filename,
        'size_mb': round(f.file_size, 2),
        'date': f.upload_date.strftime('%Y-%m-%d %H:%M:%S'),
        'is_extracted': f.is_extracted,
        'has_main': f.main_file_path is not None,
        'platform': f.platform,
        'extracted_count': f.extracted_files_count
    } for f in files])

@app.route('/api/bots')
@login_required
def get_bots():
    bots = UserBot.query.filter_by(user_id=session['user_id']).all()
    return jsonify([{
        'id': b.id,
        'name': b.bot_name,
        'type': b.bot_type,
        'status': b.bot_status,
        'created_at': b.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'last_active': b.last_active.strftime('%Y-%m-%d %H:%M:%S')
    } for b in bots])

@app.route('/api/files/<int:file_id>/delete', methods=['DELETE'])
@login_required
def delete_file(file_id):
    file_record = UploadedFile.query.get_or_404(file_id)
    
    if file_record.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    if os.path.exists(file_record.file_path):
        os.remove(file_record.file_path)
    
    if file_record.extracted_path and os.path.exists(file_record.extracted_path):
        shutil.rmtree(file_record.extracted_path)
    
    user = User.query.get(session['user_id'])
    user.storage_used -= file_record.file_size
    db.session.delete(file_record)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'File deleted successfully!'})

@app.route('/logout')
def logout():
    log_activity(session.get('user_id'), 'logout', 'User logged out') if session.get('user_id') else None
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)