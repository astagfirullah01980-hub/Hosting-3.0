from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import zipfile
import os
import shutil
import uuid
import json
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'iftekhar-super-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
app.config['ALLOWED_EXTENSIONS'] = {'zip', 'rar', '7z'}

db = SQLAlchemy(app)

# Create upload folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    storage_used = db.Column(db.Float, default=0.0)  # in MB
    bots_deployed = db.Column(db.Integer, default=0)
    
    files = db.relationship('UploadedFile', backref='owner', lazy=True)
    bots = db.relationship('UserBot', backref='owner', lazy=True)

class UploadedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    original_filename = db.Column(db.String(200), nullable=False)
    file_size = db.Column(db.Float, default=0.0)  # in MB
    file_path = db.Column(db.String(500), nullable=False)
    extracted_path = db.Column(db.String(500))
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    extracted_files_count = db.Column(db.Integer, default=0)
    is_extracted = db.Column(db.Boolean, default=False)

class UserBot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bot_name = db.Column(db.String(100), nullable=False)
    bot_type = db.Column(db.String(50), nullable=False)  # python, nodejs, java, etc.
    bot_status = db.Column(db.String(20), default='stopped')  # running, stopped, error
    bot_port = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    config = db.Column(db.Text)  # JSON config

class BotTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))
    version = db.Column(db.String(20))
    template_code = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)

# Create tables
with app.app_context():
    db.create_all()
    
    # Add default bot templates if not exists
    if BotTemplate.query.count() == 0:
        templates = [
            BotTemplate(name="Python Discord Bot", type="python", 
                       description="Complete Discord bot with moderation features",
                       icon="🐍", version="3.11",
                       template_code="import discord\n\nclient = discord.Client()\n\n@client.event\nasync def on_ready():\n    print('Bot is ready!')"),
            
            BotTemplate(name="Node.js Web Server", type="nodejs",
                       description="Express.js web server with REST API",
                       icon="💚", version="20.x",
                       template_code="const express = require('express');\nconst app = express();\n\napp.get('/', (req, res) => {\n    res.send('Hello World!');\n});\n\napp.listen(3000);"),
            
            BotTemplate(name="Java Spring Bot", type="java",
                       description="Spring Boot application with JPA",
                       icon="☕", version="17",
                       template_code="@SpringBootApplication\npublic class Application {\n    public static void main(String[] args) {\n        SpringApplication.run(Application.class, args);\n    }\n}"),
            
            BotTemplate(name="PHP Web Bot", type="php",
                       description="PHP bot with Laravel support",
                       icon="🐘", version="8.2",
                       template_code="<?php\necho 'Bot is running!';\n?>"),
        ]
        for template in templates:
            db.session.add(template)
        db.session.commit()

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
    """Extract ZIP file with progress tracking"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            zip_ref.extractall(extract_to)
        return True, file_list, None
    except Exception as e:
        return False, [], str(e)

def get_file_size_mb(file_path):
    return os.path.getsize(file_path) / (1024 * 1024)

# Routes
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
    
    # Calculate statistics
    total_files = len(files)
    total_size = sum([f.file_size for f in files])
    total_bots = len(bots)
    running_bots = len([b for b in bots if b.bot_status == 'running'])
    
    # Get recent activity
    recent_files = files[:5]
    recent_bots = bots[:5]
    
    stats = {
        'total_files': total_files,
        'total_size': round(total_size, 2),
        'total_bots': total_bots,
        'running_bots': running_bots,
        'storage_limit': 1000,  # 1GB limit
        'storage_used': round(total_size, 2),
        'storage_percent': round((total_size / 1000) * 100, 2) if total_size > 0 else 0
    }
    
    return render_template('dashboard.html', 
                         user=user, 
                         files=recent_files,
                         bots=recent_bots,
                         stats=stats,
                         all_files=files)

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        flash('No file selected!', 'error')
        return redirect(url_for('dashboard'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected!', 'error')
        return redirect(url_for('dashboard'))
    
    if file and allowed_file(file.filename):
        # Create user folder
        user_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(session['user_id']))
        os.makedirs(user_folder, exist_ok=True)
        
        # Secure filename
        original_filename = file.filename
        filename = secure_filename(f"{uuid.uuid4().hex}_{original_filename}")
        file_path = os.path.join(user_folder, filename)
        
        # Save file
        file.save(file_path)
        file_size = get_file_size_mb(file_path)
        
        # Update user storage
        user = User.query.get(session['user_id'])
        user.storage_used += file_size
        db.session.commit()
        
        # Extract if ZIP
        extracted_path = None
        extracted_count = 0
        is_extracted = False
        
        if filename.endswith('.zip'):
            extracted_folder = os.path.join(user_folder, f"extracted_{uuid.uuid4().hex[:8]}")
            os.makedirs(extracted_folder, exist_ok=True)
            
            success, file_list, error = extract_zip(file_path, extracted_folder)
            if success:
                extracted_path = extracted_folder
                extracted_count = len(file_list)
                is_extracted = True
                flash(f'✅ ZIP file extracted successfully! Found {extracted_count} files.', 'success')
            else:
                flash(f'⚠️ File uploaded but extraction failed: {error}', 'warning')
        
        # Save to database
        uploaded_file = UploadedFile(
            filename=filename,
            original_filename=original_filename,
            file_size=file_size,
            file_path=file_path,
            extracted_path=extracted_path,
            extracted_files_count=extracted_count,
            is_extracted=is_extracted,
            user_id=session['user_id']
        )
        
        db.session.add(uploaded_file)
        db.session.commit()
        
        flash(f'✅ File "{original_filename}" uploaded successfully!', 'success')
        
    else:
        flash('Only ZIP, RAR, and 7Z files are allowed!', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/file/<int:file_id>/extract')
@login_required
def view_extracted_files(file_id):
    file_record = UploadedFile.query.get_or_404(file_id)
    
    if file_record.user_id != session['user_id']:
        flash('Access denied!', 'error')
        return redirect(url_for('dashboard'))
    
    if not file_record.is_extracted or not file_record.extracted_path:
        flash('This file has no extracted contents!', 'warning')
        return redirect(url_for('dashboard'))
    
    # Get list of extracted files
    extracted_files = []
    if os.path.exists(file_record.extracted_path):
        for root, dirs, files in os.walk(file_record.extracted_path):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, file_record.extracted_path)
                file_size = os.path.getsize(full_path) / 1024  # KB
                extracted_files.append({
                    'name': file,
                    'path': rel_path,
                    'size_kb': round(file_size, 2),
                    'full_path': full_path
                })
    
    return render_template('extracted_files.html', 
                         file=file_record, 
                         files=extracted_files)

@app.route('/api/bots/templates')
@login_required
def get_bot_templates():
    templates = BotTemplate.query.filter_by(is_active=True).all()
    return jsonify([{
        'id': t.id,
        'name': t.name,
        'type': t.type,
        'description': t.description,
        'icon': t.icon,
        'version': t.version,
        'template_code': t.template_code
    } for t in templates])

@app.route('/api/bots/deploy', methods=['POST'])
@login_required
def deploy_bot():
    data = request.get_json()
    bot_template_id = data.get('template_id')
    bot_name = data.get('bot_name')
    
    template = BotTemplate.query.get_or_404(bot_template_id)
    
    # Create bot deployment folder
    bot_folder = os.path.join('deployments', str(session['user_id']), bot_name.replace(' ', '_'))
    os.makedirs(bot_folder, exist_ok=True)
    
    # Save bot configuration
    new_bot = UserBot(
        bot_name=bot_name,
        bot_type=template.type,
        bot_status='stopped',
        bot_port=5000 + len(UserBot.query.all()),
        user_id=session['user_id'],
        config=json.dumps({
            'template_id': bot_template_id,
            'deployed_at': datetime.utcnow().isoformat(),
            'folder': bot_folder
        })
    )
    
    db.session.add(new_bot)
    
    # Update user stats
    user = User.query.get(session['user_id'])
    user.bots_deployed += 1
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Bot "{bot_name}" deployed successfully!',
        'bot_id': new_bot.id
    })

@app.route('/api/bots/<int:bot_id>/start', methods=['POST'])
@login_required
def start_bot(bot_id):
    bot = UserBot.query.get_or_404(bot_id)
    
    if bot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    bot.bot_status = 'running'
    bot.last_active = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Bot started successfully!'})

@app.route('/api/bots/<int:bot_id>/stop', methods=['POST'])
@login_required
def stop_bot(bot_id):
    bot = UserBot.query.get_or_404(bot_id)
    
    if bot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    bot.bot_status = 'stopped'
    bot.last_active = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Bot stopped successfully!'})

@app.route('/api/bots/<int:bot_id>/delete', methods=['DELETE'])
@login_required
def delete_bot(bot_id):
    bot = UserBot.query.get_or_404(bot_id)
    
    if bot.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    # Delete bot files
    config = json.loads(bot.config)
    if os.path.exists(config.get('folder', '')):
        shutil.rmtree(config.get('folder'))
    
    db.session.delete(bot)
    
    # Update user stats
    user = User.query.get(session['user_id'])
    user.bots_deployed -= 1
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Bot deleted successfully!'})

@app.route('/api/stats')
@login_required
def get_stats():
    user = User.query.get(session['user_id'])
    files = UploadedFile.query.filter_by(user_id=user.id).all()
    bots = UserBot.query.filter_by(user_id=user.id).all()
    
    stats = {
        'total_files': len(files),
        'total_files_size': round(sum([f.file_size for f in files]), 2),
        'total_bots': len(bots),
        'running_bots': len([b for b in bots if b.bot_status == 'running']),
        'storage_used': round(user.storage_used, 2),
        'storage_limit': 1000,
        'bots_deployed': user.bots_deployed
    }
    
    return jsonify(stats)

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
        'extracted_count': f.extracted_files_count
    } for f in files])

@app.route('/api/files/<int:file_id>/delete', methods=['DELETE'])
@login_required
def delete_file(file_id):
    file_record = UploadedFile.query.get_or_404(file_id)
    
    if file_record.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    # Delete physical files
    if os.path.exists(file_record.file_path):
        os.remove(file_record.file_path)
    
    if file_record.extracted_path and os.path.exists(file_record.extracted_path):
        shutil.rmtree(file_record.extracted_path)
    
    # Update user storage
    user = User.query.get(session['user_id'])
    user.storage_used -= file_record.file_size
    db.session.delete(file_record)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'File deleted successfully!'})

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/overview')
@login_required
def overview():
    return render_template('overview.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)