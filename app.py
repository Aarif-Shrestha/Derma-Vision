from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file, make_response, render_template_string
from werkzeug.utils import secure_filename
import os
import numpy as np
from PIL import Image
import tensorflow as tf
import json
import bcrypt
from functools import wraps
import pdfkit
from datetime import datetime
import io

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a secure secret key
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Load model (commented out until model is available)
# model = tf.keras.models.load_model('skin.keras')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

@app.context_processor
def inject_year():
    return {'current_year': datetime.now().year}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_users():
    try:
        with open('users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"users": []}

def save_users(users):
    with open('users.json', 'w') as f:
        json.dump(users, f, indent=4)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():  # Changed from home to index
    return render_template('index.html')    

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        users_data = load_users()
        
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Check if user already exists
        if any(user['email'] == email for user in users_data['users']):
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        # Validate password match
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))
        
        # Hash password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        
        # Create new user
        new_user = {
            'id': len(users_data['users']) + 1,
            'email': email,
            'password': hashed_password.decode('utf-8')
        }
        
        users_data['users'].append(new_user)
        save_users(users_data)
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users_data = load_users()
        email = request.form['email']
        password = request.form['password']
        
        user = next((user for user in users_data['users'] if user['email'] == email), None)
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            session['user_id'] = user['id']
            session['email'] = user['email']
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))  # Changed from home to index
        else:
            flash('Invalid email or password', 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))  # Changed from home to index

@app.route('/detect', methods=['GET', 'POST'])
@login_required
def detect():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'})
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Image preprocessing (commented out until model is available)
            """
            img = Image.open(filepath)
            img = img.resize((224, 224))  # Adjust size according to your model
            img_array = np.array(img)
            img_array = np.expand_dims(img_array, axis=0)
            
            # Make prediction
            prediction = model.predict(img_array)
            result = {'prediction': prediction.tolist()}
            """
            
            # Temporary response until model is integrated
            result = {'message': 'Image uploaded successfully'}
            return jsonify(result)
            
    return render_template('detect.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        # Add password reset logic here
        flash('Password reset instructions have been sent to your email.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/download-report/<int:report_id>')
@login_required
def download_report_pdf(report_id):
    # Get report data based on report_id
    # This is a placeholder - implement actual report generation logic
    report_data = {
        'id': report_id,
        'date': '2024-03-19',
        'diagnosis': 'Sample Diagnosis',
        'confidence': '95%'
    }
    
    # Render the report template
    html = render_template('report_template.html', report=report_data)
    
    # Convert HTML to PDF
    pdf = pdfkit.from_string(html, False)
    
    # Prepare the response
    response = app.make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=report_{report_id}.pdf'
    
    return response

@app.route('/download_report', methods=['POST'])
def download_report():
    # Get data from request (simulate or use actual detection data)
    data = request.json or {}
    # Example data, replace with actual detection result
    report_data = {
        'report_id': data.get('report_id', 'RPT-' + datetime.now().strftime('%Y%m%d%H%M%S')),
        'report_date': datetime.now().strftime('%Y-%m-%d'),
        'report_time': datetime.now().strftime('%H:%M:%S'),
        'patient_name': data.get('patient_name', 'Anonymous'),
        'condition_name': data.get('condition_name', 'Unknown'),
        'confidence': data.get('confidence', 'N/A'),
        'image_url': data.get('image_url', None),
    }
    # Render HTML report
    html = render_template('report_template.html', **report_data)
    # Generate PDF from HTML
    pdf = pdfkit.from_string(html, False)
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=DermaVision_Report_{}.pdf'.format(report_data['report_id'])
    return response

if __name__ == '__main__':
    app.run(debug=True)
