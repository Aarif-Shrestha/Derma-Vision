from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file
from werkzeug.utils import secure_filename
import os
import numpy as np
import json
import bcrypt
from functools import wraps
from datetime import datetime
import io
import time
from tensorflow import keras
from PIL import Image, ImageOps
import google.generativeai as genai
from tensorflow.keras.preprocessing import image
import tensorflow as tf
from tensorflow.keras.applications.efficientnet_v2 import preprocess_input

app = Flask(__name__)
app.secret_key = 'eefbca0d0f8710f182def35e827248045dafc9592fe6cd45af93ae784a6e04d3'  # Change this to a secure secret key
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Load model at server startup so it is always available for predictions
MODEL_PATH = os.path.join(app.root_path, 'models', 'thisisit.keras')
# Load model in a background thread so server starts immediately
import threading
model = None

def load_model_bg():
    global model
    print("[INFO] Loading model, please wait...", flush=True)
    for i in range(3):
        print("[INFO] Loading" + "." * (i+1), flush=True)
        time.sleep(0.5)
    model = keras.models.load_model(MODEL_PATH)
    print("[INFO] Model loaded successfully!", flush=True)

threading.Thread(target=load_model_bg, daemon=True).start()

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

def load_user_history():
    try:
        with open('user_history.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"history": {}}

def save_user_history(history):
    with open('user_history.json', 'w') as f:
        json.dump(history, f, indent=4)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login', next=request.url))
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
    next_url = request.args.get('next')
    if request.method == 'POST':
        users_data = load_users()
        email = request.form['email']
        password = request.form['password']
        
        user = next((user for user in users_data['users'] if user['email'] == email), None)
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password'].encode('utf-8')):
            session['user_id'] = user['id']
            session['email'] = user['email']
            # Load user history and store in session
            user_history = load_user_history()
            user_id_str = str(user['id'])
            session['history'] = user_history['history'].get(user_id_str, [])
            flash('Logged in successfully!', 'success')
            return redirect(next_url or url_for('index'))  # Changed from home to index
        else:
            flash('Invalid email or password', 'error')
            return redirect(url_for('login', next=next_url))

    return render_template('login.html', next=next_url)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))  # Changed from home to index

@app.route('/detect', methods=['GET', 'POST'])
@login_required
def detect():
    if request.method == 'GET':
        return render_template('detect.html')
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        # --- Gemini skin check ---
        if not is_skin_related_image(filepath):
            return jsonify({'error': 'The uploaded image does not appear to be a skin lesion or skin disease.'}), 400
        # --- End Gemini check ---
        if model is None:
            return jsonify({'error': 'Model is still loading, please try again in a few seconds.'}), 503
        img_array = preprocess_image(filepath)
        prediction = model.predict(img_array)
        # Use fixed class names for prediction
        class_names = [
            "Basal Cell Carcinoma (bcc)",
            "Benign Keratosis-like Lesions (bkl)",
            "Dermatofibroma (df)",
            "Melanoma (mel)",
            "Melanocytic Nevi (nv)",
            "Vascular Lesions (vasc)"
        ]
        if hasattr(prediction, 'tolist'):
            prediction = prediction.tolist()
        if isinstance(prediction, list) and isinstance(prediction[0], list):
            prediction = prediction[0]
        class_probabilities = {name: float(prob) for name, prob in zip(class_names, prediction)}
        predicted_label = class_names[int(np.argmax(list(class_probabilities.values())))]
        result = {
            'predicted_label': predicted_label,
            'class_probabilities': class_probabilities,
            'image_url': url_for('static', filename=f'uploads/{filename}', _external=True),
            'recommendations': [rec.lstrip('- ').strip() for rec in get_recommendations(predicted_label).split('\n') if rec.strip()]
        }
        return jsonify(result)
    return jsonify({'error': 'Invalid file type'}), 400

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

def get_recommendations(condition_name):
    recommendations = {
        "Basal Cell Carcinoma (bcc)": [
            "Consult a dermatologist for treatment options as soon as possible.",
            "Early intervention is important to prevent further growth.",
            "Avoid sun exposure and use broad-spectrum sunscreen daily.",
            "Do not attempt to self-treat or remove the lesion.",
            "Schedule regular follow-ups with your dermatologist to monitor for recurrence."
        ],
        "Benign Keratosis-like Lesions (bkl)": [
            "These are usually harmless, but monitor for changes in size, color, or shape.",
            "If you notice rapid growth or color change, consult a dermatologist.",
            "Avoid scratching or picking at the lesion to prevent irritation or infection.",
            "Maintain good skin hygiene to avoid secondary infection.",
            "Consider removal only if the lesion becomes bothersome or for cosmetic reasons."
        ],
        "Dermatofibroma (df)": [
            "Generally benign and do not require treatment.",
            "If the lesion becomes painful, itchy, or changes in appearance, seek medical advice.",
            "Avoid trauma to the area to prevent irritation.",
            "Monitor for any rapid changes in size or color.",
            "Removal is usually not necessary unless it causes discomfort."
        ],
        "Melanoma (mel)": [
            "Seek immediate medical attention. Melanoma can be life-threatening if not treated early.",
            "Do not attempt to self-treat or remove the lesion.",
            "Schedule regular skin checks with a dermatologist, especially if you have a history of sunburns or family history of melanoma.",
            "Protect your skin from further sun exposure.",
            "Educate close family members about the signs of melanoma for early detection."
        ],
        "Melanocytic Nevi (nv)": [
            "Common moles are usually harmless.",
            "Monitor for changes in size, shape, or color using the ABCDE rule (Asymmetry, Border, Color, Diameter, Evolving).",
            "See a dermatologist if you notice any changes or if the mole becomes symptomatic (itchy, bleeding, or painful).",
            "Avoid excessive sun exposure and use sunscreen regularly.",
            "Do not attempt to remove moles at home."
        ],
        "Vascular Lesions (vasc)": [
            "Most are benign, but if you notice bleeding or rapid growth, consult a healthcare provider.",
            "Avoid trauma to the lesion to prevent bleeding.",
            "If the lesion is bothersome or cosmetically concerning, discuss removal options with a dermatologist.",
            "Monitor for any changes in color or size.",
            "Maintain good skin hygiene to prevent infection."
        ],
    }
    recs = recommendations.get(condition_name, ["Consult a healthcare professional for further advice."])
    return '\n'.join(f"- {r}" for r in recs)

@app.route('/download_report', methods=['POST'])
def download_report():
    try:
        data = request.json or {}
        report_data = {
            'report_id': data.get('report_id', 'RPT-' + datetime.now().strftime('%Y%m%d%H%M%S')),
            'report_date': data.get('report_date', datetime.now().strftime('%Y-%m-%d')),
            'report_time': data.get('report_time', datetime.now().strftime('%H:%M:%S')),
            'patient_name': data.get('patient_name', 'Anonymous'),
            'condition_name': data.get('condition_name', 'Unknown'),
            'confidence': data.get('confidence', 'N/A'),
            'image_url': data.get('image_url', None),
        }

        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Image as RLImage, Table, TableStyle
        import io

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        # Add logo (fix aspect ratio)
        logo_path = os.path.join(app.root_path, 'static', 'images', 'logo.png')
        if os.path.exists(logo_path):
            logo = RLImage(logo_path, width=120, height=120, kind='proportional')
            elements.append(logo)
            elements.append(Spacer(1, 12))

        # Title
        title = Paragraph('<font size=20 color="#2E86C1"><b>Derma Vision Disease Report</b></font>', styles['Title'])
        elements.append(title)
        elements.append(Spacer(1, 24))

        # Patient and report info (cleaner, less bold)
        info_table = Table([
            ['Report ID:', report_data['report_id']],
            ['Date:', report_data['report_date']],
            ['Time:', report_data['report_time']],
            ['Patient Name:', report_data['patient_name']],
        ], colWidths=[120, 300])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F4F6F7')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2E4053')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F8F9F9')]),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 18))

        # Disease info (cleaner, less bold)
        disease_table = Table([
            ['Condition Name', 'Confidence'],
            [report_data['condition_name'], report_data['confidence']],
        ], colWidths=[220, 200])
        disease_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D6EAF8')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#154360')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(disease_table)
        elements.append(Spacer(1, 24))
        # Add recommendations section
        recommendations = get_recommendations(report_data['condition_name'])
        elements.append(Paragraph('<b>Recommendations:</b>', styles['Heading3']))
        elements.append(Paragraph(recommendations, styles['Normal']))
        elements.append(Spacer(1, 18))

        # Add uploaded image if available
        if report_data['image_url']:
            img_filename = os.path.basename(report_data['image_url'])
            img_path = os.path.join(app.root_path, 'static', 'uploads', img_filename)
            if os.path.exists(img_path):
                uploaded_img = RLImage(img_path, width=200, height=200)
                elements.append(Paragraph('<b>Uploaded Image:</b>', styles['Heading3']))
                elements.append(uploaded_img)
                elements.append(Spacer(1, 18))

        # Add a footer
        elements.append(Spacer(1, 36))
        footer = Paragraph('<font size=10 color="#85929E">Generated by Derma Vision &copy; {}</font>'.format(datetime.now().year), styles['Normal'])
        elements.append(footer)

        # Add Derma Vision watermark
        def add_watermark(canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica-Bold', 40)
            canvas.setFillColorRGB(0.85, 0.9, 0.95, alpha=0.15)
            canvas.drawCentredString(300, 400, "Derma Vision")
            canvas.restoreState()

        doc.build(elements, onFirstPage=add_watermark, onLaterPages=add_watermark)
        pdf = buffer.getvalue()
        buffer.close()

        response = app.make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f"attachment; filename=DermaVision_Report_{report_data['report_id']}.pdf"
        return response
    except Exception as e:
        print('PDF generation error:', e)
        return jsonify({'error': 'Failed to generate PDF report. Please contact support.'}), 500

@app.route('/download_latest_report', methods=['POST'])
@login_required
def download_latest_report():
    try:
        data = request.json or {}
        # Example: get latest prediction data from session or database
        report_data = {
            'report_id': data.get('report_id', 'RPT-' + datetime.now().strftime('%Y%m%d%H%M%S')),
            'report_date': data.get('report_date', datetime.now().strftime('%Y-%m-%d')),
            'report_time': data.get('report_time', datetime.now().strftime('%H:%M:%S')),
            'patient_name': data.get('patient_name', 'Anonymous'),
            'condition_name': data.get('condition_name', 'Unknown'),
            'confidence': data.get('confidence', 'N/A'),
            'image_url': data.get('image_url', None),
        }

        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Image as RLImage, Table, TableStyle
        import io

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        # Add logo (fix aspect ratio)
        logo_path = os.path.join(app.root_path, 'static', 'images', 'logo.png')
        if os.path.exists(logo_path):
            logo = RLImage(logo_path, width=120, height=120, kind='proportional')
            elements.append(logo)
            elements.append(Spacer(1, 12))

        # Title
        title = Paragraph('<font size=20 color="#2E86C1"><b>Derma Vision Disease Report</b></font>', styles['Title'])
        elements.append(title)
        elements.append(Spacer(1, 24))

        # Patient and report info (cleaner, less bold)
        info_table = Table([
            ['Report ID:', report_data['report_id']],
            ['Date:', report_data['report_date']],
            ['Time:', report_data['report_time']],
            ['Patient Name:', report_data['patient_name']],
        ], colWidths=[120, 300])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F4F6F7')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#2E4053')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F8F9F9')]),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 18))

        # Disease info (cleaner, less bold)
        disease_table = Table([
            ['Condition Name', 'Confidence'],
            [report_data['condition_name'], report_data['confidence']],
        ], colWidths=[220, 200])
        disease_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D6EAF8')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#154360')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(disease_table)
        elements.append(Spacer(1, 24))
        # Add recommendations section
        recommendations = get_recommendations(report_data['condition_name'])
        elements.append(Paragraph('<b>Recommendations:</b>', styles['Heading3']))
        elements.append(Paragraph(recommendations, styles['Normal']))
        elements.append(Spacer(1, 18))

        # Add uploaded image if available
        if report_data['image_url']:
            img_filename = os.path.basename(report_data['image_url'])
            img_path = os.path.join(app.root_path, 'static', 'uploads', img_filename)
            if os.path.exists(img_path):
                uploaded_img = RLImage(img_path, width=200, height=200)
                elements.append(Paragraph('<b>Uploaded Image:</b>', styles['Heading3']))
                elements.append(uploaded_img)
                elements.append(Spacer(1, 18))

        # Add a footer
        elements.append(Spacer(1, 36))
        footer = Paragraph('<font size=10 color="#85929E">Generated by Derma Vision &copy; {}</font>'.format(datetime.now().year), styles['Normal'])
        elements.append(footer)

        # Add Derma Vision watermark
        def add_watermark(canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica-Bold', 40)
            canvas.setFillColorRGB(0.85, 0.9, 0.95, alpha=0.15)
            canvas.drawCentredString(300, 400, "Derma Vision")
            canvas.restoreState()

        doc.build(elements, onFirstPage=add_watermark, onLaterPages=add_watermark)
        pdf = buffer.getvalue()
        buffer.close()

        response = app.make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f"attachment; filename=DermaVision_Report_{report_data['report_id']}.pdf"
        return response
    except Exception as e:
        print('PDF generation error:', e)
        return jsonify({'error': 'Failed to generate PDF report. Please contact support.'}), 500

genai.configure(api_key="AIzaSyA1o8P4FE8B77mBPNwJHCqEyLdzyOdaVmY")  # ← REPLACE with your actual key

def is_skin_related_image(image_path):
    try:
        img = Image.open(image_path)
    except Exception as e:
        print(f"[ERROR] Failed to open image for Gemini check: {e}")
        return False
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content([
            """You are a strict skin disease screening assistant.\nOnly reply with YES or NO: Does this image contain a human skin lesion or skin disease?\nAvoid being overly generous — say NO if unsure.\n""", img
        ])
        result = response.text.strip().lower()
        print("Gemini raw response:", result)
        return result.startswith("yes")
    except Exception as e:
        print(f"[ERROR] Gemini API call failed: {e}")
        return False

def preprocess_image(img_path):
    img = image.load_img(img_path, target_size=(224, 224))
    img_array = image.img_to_array(img)
    img_array = tf.cast(img_array, tf.float32)
    img_array = tf.expand_dims(img_array, axis=0)
    img_array = preprocess_input(img_array)
    return img_array

if __name__ == '__main__':
    app.run(debug=True)
