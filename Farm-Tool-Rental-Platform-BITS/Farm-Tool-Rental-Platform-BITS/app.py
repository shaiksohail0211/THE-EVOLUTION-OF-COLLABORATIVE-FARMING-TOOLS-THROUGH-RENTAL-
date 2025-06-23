from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
from dotenv import load_dotenv
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from sqlalchemy import text
import speech_recognition as sr
import pyaudio
import wave
import threading
import time
import logging
from flask_cors import CORS

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Constants
WAVE_OUTPUT_DIR = "recordings"
ALLOWED_EXTENSIONS = {'wav'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'toolrental.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Add this before creating the database to ensure the directory is writable
db_dir = os.path.dirname(app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''))
if not os.path.exists(db_dir):
    os.makedirs(db_dir)

# Mail settings
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

# Initialize extensions
db = SQLAlchemy(app)
mail = Mail(app)

def send_email(to, subject, body):
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        print(f"Email not sent (mail not configured) - To: {to}, Subject: {subject}")
        return True
    try:
        msg = Message(
            subject=subject,
            recipients=[to],
            body=body
        )
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False

# Add configurations for image uploads
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'tool_images')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_TIMEOUT'] = 30  # 30 seconds timeout

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

@app.route('/static/tool_images/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

def save_image(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        return filename  # Return just the filename
    return None

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    mobile = db.Column(db.String(15))
    owned_tools = db.relationship('Tool', backref=db.backref('owner_user', lazy=True), foreign_keys='Tool.owner_id')
    purchases_made = db.relationship('Purchase', foreign_keys='Purchase.buyer_id', backref=db.backref('buyer_user', lazy=True))
    purchases_sold = db.relationship('Purchase', foreign_keys='Purchase.seller_id', backref=db.backref('seller_user', lazy=True))
    rentals_given = db.relationship('Rental', foreign_keys='Rental.owner_id', backref='owner', lazy=True)
    rentals_taken = db.relationship('Rental', foreign_keys='Rental.renter_id', backref='renter', lazy=True)
    # Relationship is defined in RentalRequest model

# Tool Model
class Tool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(100), nullable=False)  # e.g., 'Tractor', 'Harvester', 'Plow', etc.
    brand = db.Column(db.String(100), nullable=False)
    condition = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_available = db.Column(db.Boolean, default=True)
    listing_type = db.Column(db.String(10), nullable=False)  # 'rent' or 'sale'
    price_per_day = db.Column(db.Float, nullable=True)
    sale_price = db.Column(db.Float, nullable=True)
    image_url_1 = db.Column(db.String(200))
    image_url_2 = db.Column(db.String(200))
    image_url_3 = db.Column(db.String(200))
    power_source = db.Column(db.String(50))  # e.g., 'Diesel', 'Electric', 'Manual'
    maintenance_status = db.Column(db.String(50))  # e.g., 'Excellent', 'Good', 'Fair'
    last_maintenance_date = db.Column(db.DateTime)
    rentals = db.relationship('Rental', backref='tool', lazy=True)
    rental_requests = db.relationship('RentalRequest', backref='tool', lazy=True)
    tool_purchases = db.relationship('Purchase', backref=db.backref('tool_details', lazy=True))

# Rental Model
class Rental(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tool_id = db.Column(db.Integer, db.ForeignKey('tool.id'), nullable=False)
    renter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, active, completed, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Rental Request Model
class RentalRequest(db.Model):
    __tablename__ = 'rental_request'
    id = db.Column(db.Integer, primary_key=True)
    tool_id = db.Column(db.Integer, db.ForeignKey('tool.id'), nullable=False)
    renter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    renter = db.relationship('User', foreign_keys=[renter_id], backref=db.backref('rental_requests_made', lazy=True))

# Purchase Model
class Purchase(db.Model):
    __tablename__ = 'purchase'
    id = db.Column(db.Integer, primary_key=True)
    tool_id = db.Column(db.Integer, db.ForeignKey('tool.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

# Login decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please login first')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Context processor to add pending requests count to all templates
@app.context_processor
def utility_processor():
    def get_pending_requests_count():
        if not session.get('user_id'):
            return 0
        # Count pending requests for tools owned by the current user
        return RentalRequest.query.join(Tool).filter(
            Tool.owner_id == session['user_id'],
            RentalRequest.status == 'pending'
        ).count()
    return {'get_pending_requests_count': get_pending_requests_count}

def send_notification_email(subject, recipient, template, **kwargs):
    try:
        msg = Message(
            subject,
            recipients=[recipient]
        )
        msg.html = render_template(template, **kwargs)
        mail.send(msg)
        print(f"Email sent successfully to {recipient}")
    except Exception as e:
        print(f"Failed to send email: {str(e)}")

@app.route('/')
def index():
    # Get search parameters
    search_query = request.args.get('search', '')
    category = request.args.get('category', '')

    # Start with base query
    query = Tool.query.filter_by(is_available=True)

    # Apply category filter if specified
    if category:
        query = query.filter(Tool.category == category)

    # Apply search filter if specified
    if search_query:
        search_filter = f"%{search_query}%"
        query = query.filter(
            db.or_(
                Tool.name.ilike(search_filter),
                Tool.brand.ilike(search_filter),
                Tool.description.ilike(search_filter)
            )
        )

    # Order by creation date and get results
    tools = query.order_by(Tool.created_at.desc()).all()

    return render_template('index.html', tools=tools)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        mobile = request.form['mobile']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('register'))

        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists!', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))

        # Create new user
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, mobile=mobile, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Welcome back!')
            return redirect(url_for('index'))

        flash('Invalid username or password')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out')
    return redirect(url_for('index'))

# Tool Management Routes
@app.route('/tools/add', methods=['GET', 'POST'])
@login_required
def add_tool():
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            category = request.form.get('category')
            brand = request.form.get('brand')
            condition = request.form.get('condition')
            listing_type = request.form.get('listing_type')
            if listing_type == 'rent':
                price_per_day = float(request.form.get('price_per_day'))
                sale_price = None
            elif listing_type == 'sale':
                price_per_day = None
                sale_price = float(request.form.get('sale_price'))
            else:
                flash('Invalid listing type', 'danger')
                return redirect(url_for('add_tool'))

            description = request.form.get('description')
            power_source = request.form.get('power_source')
            maintenance_status = request.form.get('maintenance_status')
            last_maintenance_date = datetime.strptime(request.form.get('last_maintenance_date'), '%Y-%m-%d') if request.form.get('last_maintenance_date') else None

            # Handle image uploads
            image_urls = []
            for i in range(1, 4):
                image = request.files.get(f'image{i}')
                if image and allowed_file(image.filename):
                    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image.filename}")
                    image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    image_urls.append(os.path.join('tool_images', filename))
                else:
                    image_urls.append(None)

            new_tool = Tool(
                name=name,
                category=category,
                brand=brand,
                condition=condition,
                listing_type=listing_type,
                price_per_day=price_per_day,
                sale_price=sale_price,
                description=description,
                owner_id=session['user_id'],
                image_url_1=image_urls[0],
                image_url_2=image_urls[1],
                image_url_3=image_urls[2],
                power_source=power_source,
                maintenance_status=maintenance_status,
                last_maintenance_date=last_maintenance_date
            )

            db.session.add(new_tool)
            db.session.commit()
            flash('Tool added successfully!', 'success')
            return redirect(url_for('my_tools'))

        except Exception as e:
            print(f"Error adding tool: {str(e)}")
            db.session.rollback()
            flash('Error adding tool. Please try again.', 'danger')
            return redirect(url_for('add_tool'))

    return render_template('add_tool.html')

@app.route('/tools/my-tools')
@login_required
def my_tools():
    user = User.query.get(session['user_id'])
    if not user:
        flash('User not found. Please login again.', 'danger')
        session.clear()  # Clear invalid session
        return redirect(url_for('login'))

    return render_template('my_tools.html', tools=user.owned_tools)

@app.route('/tools/<int:tool_id>')
def view_tool(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    # Get current and future rentals for this tool
    current_time = datetime.utcnow()
    active_rentals = Rental.query.filter(
        Rental.tool_id == tool_id,
        Rental.status == 'active',
        Rental.end_date > current_time
    ).order_by(Rental.start_date).all()

    # Get pending rental requests
    pending_requests = RentalRequest.query.filter(
        RentalRequest.tool_id == tool_id,
        RentalRequest.status == 'pending'
    ).order_by(RentalRequest.created_at).all()

    return render_template('view_tool.html',
                           tool=tool,
                           active_rentals=active_rentals,
                           pending_requests=pending_requests,
                           current_time=current_time)

@app.route('/tools/<int:tool_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_tool(tool_id):
    tool = Tool.query.get_or_404(tool_id)

    # Check if the current user is the owner
    if tool.owner_id != session['user_id']:
        flash('You can only edit your own tools.', 'danger')
        return redirect(url_for('my_tools'))

    if request.method == 'POST':
        try:
            tool.name = request.form.get('name')
            tool.category = request.form.get('category')
            tool.brand = request.form.get('brand')
            tool.condition = request.form.get('condition')
            tool.description = request.form.get('description')
            tool.listing_type = request.form.get('listing_type')
            tool.is_available = 'is_available' in request.form

            # Handle prices based on listing type
            if tool.listing_type == 'rent':
                price_per_day = request.form.get('price_per_day')
                tool.price_per_day = float(price_per_day) if price_per_day else None
                tool.sale_price = None
            else:
                sale_price = request.form.get('sale_price')
                tool.sale_price = float(sale_price) if sale_price else None
                tool.price_per_day = None

            # Handle image uploads
            for i in range(1, 4):
                image = request.files.get(f'image_{i}')
                if image and allowed_file(image.filename):
                    filename = save_image(image)
                    if filename:
                        setattr(tool, f'image_url_{i}', filename)

            db.session.commit()
            flash('Tool updated successfully!', 'success')
            return redirect(url_for('my_tools'))

        except Exception as e:
            db.session.rollback()
            print(f"Error updating tool: {str(e)}")
            flash('Error updating tool. Please try again.', 'danger')
            return redirect(url_for('edit_tool', tool_id=tool_id))

    return render_template('edit_tool.html', tool=tool)

@app.route('/tools/<int:tool_id>/delete', methods=['GET', 'POST'])
@login_required
def delete_tool(tool_id):
    tool = Tool.query.get_or_404(tool_id)

    # Check if the current user is the owner
    if tool.owner_id != session['user_id']:
        flash('You can only delete your own tools', 'danger')
        return redirect(url_for('my_tools'))

    try:
        # Delete related records first
        RentalRequest.query.filter_by(tool_id=tool.id).delete()
        Rental.query.filter_by(tool_id=tool.id).delete()
        Purchase.query.filter_by(tool_id=tool.id).delete()

        # Delete tool images from filesystem
        for i in range(1, 4):
            image_url = getattr(tool, f'image_url_{i}')
            if image_url:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(image_url))
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Error deleting file {file_path}: {e}")

        # Delete the tool
        db.session.delete(tool)
        db.session.commit()
        flash('Tool deleted successfully!', 'success')

    except Exception as e:
        db.session.rollback()
        print(f"Error deleting tool: {str(e)}")
        flash('Error deleting tool. Please try again.', 'danger')

    return redirect(url_for('my_tools'))

@app.route('/tools/<int:tool_id>/rent', methods=['GET', 'POST'])
@login_required
def rent_tool(tool_id):
    return redirect(url_for('request_rental', tool_id=tool_id))

@app.route('/tools/<int:tool_id>/request-rental', methods=['GET', 'POST'])
@login_required
def request_rental(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    print(f"Processing rental request for tool {tool_id} by user {session['user_id']}")

    if request.method == 'POST':
        if tool.owner_id == session['user_id']:
            flash('You cannot request to rent your own tool')
            return redirect(url_for('view_tool', tool_id=tool_id))

        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
        message = request.form.get('message', '')

        print(f"Rental request details - Start: {start_date}, End: {end_date}, Message: {message}")

        if start_date >= end_date:
            flash('End date must be after start date')
            return redirect(url_for('request_rental', tool_id=tool_id))

        if not tool.is_available:
            flash('This tool is not available for the selected dates')
            return redirect(url_for('view_tool', tool_id=tool_id))

        print(f"Creating rental request for tool {tool_id} from user {session['user_id']}")
        rental_request = RentalRequest(
            tool_id=tool_id,
            renter_id=session['user_id'],
            start_date=start_date,
            end_date=end_date,
            message=message,
            status='pending'
        )

        db.session.add(rental_request)
        db.session.commit()
        print(f"Rental request {rental_request.id} created successfully")

        if tool.owner_user.email:
            send_notification_email(
                'New Rental Request',
                tool.owner_user.email,
                'email/new_request.html',
                user=User.query.get(session['user_id']),
                tool=tool,
                request=rental_request
            )

        flash('Your rental request has been sent! The owner will review it and respond soon.')
        return redirect(url_for('my_rental_requests'))

    return render_template('request_rental.html', tool=tool, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/tools/purchase/<int:tool_id>', methods=['POST'])
@login_required
def request_purchase(tool_id):
    tool = Tool.query.get_or_404(tool_id)

    if not tool.is_available:
        flash('Sorry, this tool is no longer available.', 'danger')
        return redirect(url_for('view_tool', tool_id=tool_id))

    if tool.owner_id == session['user_id']:
        flash('You cannot purchase your own tool.', 'danger')
        return redirect(url_for('view_tool', tool_id=tool_id))

    if tool.listing_type != 'sale':
        flash('This tool is not listed for sale.', 'danger')
        return redirect(url_for('view_tool', tool_id=tool_id))

    # Check if user already has a pending request for this tool
    existing_request = Purchase.query.filter_by(
        tool_id=tool_id,
        buyer_id=session['user_id'],
        status='pending'
    ).first()

    if existing_request:
        flash('You already have a pending request for this tool.', 'info')
        return redirect(url_for('view_tool', tool_id=tool_id))

    try:
        buyer = User.query.get(session['user_id'])
        seller = tool.owner_user
        message = request.form.get('message', '')

        # Create a new purchase request
        purchase = Purchase(
            tool_id=tool_id,
            buyer_id=session['user_id'],
            seller_id=tool.owner_id,
            price=tool.sale_price,
            message=message
        )

        db.session.add(purchase)
        db.session.commit()

        # Send email notifications
        send_email(
            to=buyer.email,
            subject=f"Purchase Request Sent - {tool.name}",
            body=f"""Hi {buyer.username},

Your purchase request has been sent for {tool.name}.

Tool Details:
- Name: {tool.name}
- Category: {tool.category}
- Brand: {tool.brand}
- Price: ${tool.sale_price}

Seller Details:
- Name: {seller.username}
- Contact: {seller.mobile if seller.mobile else 'Not provided'}

Your message to the seller:
{message}

The seller will review your request and contact you if they accept.

Best regards,
The Tool Rental Team"""
        )

        send_email(
            to=seller.email,
            subject=f"New Purchase Request - {tool.name}",
            body=f"""Hi {seller.username},

{buyer.username} is interested in buying your tool {tool.name}.

Buyer Details:
- Name: {buyer.username}
- Contact: {buyer.mobile if buyer.mobile else 'Not provided'}

Their message:
{message}

Please review this request in your dashboard and accept or reject it.

Best regards,
The Tool Rental Team"""
        )

        flash('Your purchase request has been sent! You will be notified when the seller responds.', 'success')
        return redirect(url_for('my_purchase_requests'))

    except Exception as e:
        db.session.rollback()
        print(f"Error processing purchase request: {str(e)}")
        flash('Error processing your request. Please try again.', 'danger')
        return redirect(url_for('view_tool', tool_id=tool_id))

@app.route('/my-purchase-requests')
@login_required
def my_purchase_requests():
    # Get requests for tools I'm selling
    selling_requests = Purchase.query.join(Tool).filter(
        Tool.owner_id == session['user_id'],
        Purchase.status == 'pending'
    ).all()

    # Get my requests to buy tools
    buying_requests = Purchase.query.filter_by(
        buyer_id=session['user_id']
    ).all()

    return render_template(
        'my_purchase_requests.html',
        selling_requests=selling_requests,
        buying_requests=buying_requests
    )

@app.route('/handle-purchase-request/<int:request_id>', methods=['POST'])
@login_required
def handle_purchase_request(request_id):
    purchase = Purchase.query.get_or_404(request_id)
    tool = Tool.query.get_or_404(purchase.tool_id)

    # Verify the current user is the seller
    if tool.owner_id != session['user_id']:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('my_purchase_requests'))

    action = request.form.get('action')
    if action not in ['accept', 'reject']:
        flash('Invalid action.', 'danger')
        return redirect(url_for('my_purchase_requests'))

    try:
        if action == 'accept':
            # Mark the purchase as accepted
            purchase.status = 'accepted'
            purchase.seller_id = session['user_id']  # Set the seller_id
            # Mark the tool as unavailable
            tool.is_available = False
            # Reject all other pending requests for this tool
            other_requests = Purchase.query.filter(
                Purchase.tool_id == tool.id,
                Purchase.id != purchase.id,
                Purchase.status == 'pending'
            ).all()
            for req in other_requests:
                req.status = 'rejected'
                # Send rejection email
                send_email(
                    to=req.buyer_user.email,
                    subject=f"Purchase Request Rejected - {tool.name}",
                    body=f"""Hi {req.buyer_user.username},

Unfortunately, your purchase request for {tool.name} was not accepted as the tool has been sold to another buyer.

You can continue browsing other available tools on our platform.

Best regards,
The Tool Rental Team"""
                )

            # Send acceptance email
            send_email(
                to=purchase.buyer_user.email,
                subject=f"Purchase Request Accepted - {tool.name}",
                body=f"""Hi {purchase.buyer_user.username},

Great news! {tool.owner_user.username} has accepted your purchase request for {tool.name}.

Seller Contact:
{tool.owner_user.mobile if tool.owner_user.mobile else 'Not provided'}

Please contact the seller to arrange the payment and pickup.

Best regards,
The Tool Rental Team"""
            )

            # Send notification to seller
            send_email(
                to=tool.owner_user.email,
                subject=f"You've Accepted a Purchase Request - {tool.name}",
                body=f"""Hi {tool.owner_user.username},

You have accepted the purchase request from {purchase.buyer_user.username} for your tool {tool.name}.

Buyer Contact:
{purchase.buyer_user.mobile if purchase.buyer_user.mobile else 'Not provided'}

Please wait for the buyer to contact you to arrange the payment and pickup.

Best regards,
The Tool Rental Team"""
            )

        else:  # reject
            purchase.status = 'rejected'
            purchase.seller_id = session['user_id']  # Set the seller_id
            send_email(
                to=purchase.buyer_user.email,
                subject=f"Purchase Request Rejected - {tool.name}",
                body=f"""Hi {purchase.buyer_user.username},

Unfortunately, your purchase request for {tool.name} was not accepted.

You can continue browsing other available tools on our platform.

Best regards,
The Tool Rental Team"""
            )

        db.session.commit()
        flash(f'Purchase request {action}ed successfully.', 'success')

    except Exception as e:
        db.session.rollback()
        print(f"Error handling purchase request: {str(e)}")
        flash('Error processing your request. Please try again.', 'danger')

    return redirect(url_for('my_purchase_requests'))

@app.route('/rentals/my-rentals')
@login_required
def my_rentals():
    print(f"Fetching rentals for user_id: {session['user_id']}")

    # Get rentals where user is the renter
    my_rentals = Rental.query.filter_by(
        renter_id=session['user_id']
    ).order_by(Rental.created_at.desc()).all()
    print(f"Found {len(my_rentals)} rentals where user is renter")

    # Get rentals of tools owned by the user
    owned_tools = Tool.query.filter_by(owner_id=session['user_id']).with_entities(Tool.id).all()
    owned_tool_ids = [tool[0] for tool in owned_tools]
    print(f"User owns {len(owned_tool_ids)} tools")

    rentals_of_my_tools = Rental.query.filter(
        Rental.tool_id.in_(owned_tool_ids)
    ).order_by(Rental.created_at.desc()).all()
    print(f"Found {len(rentals_of_my_tools)} rentals of user's tools")

    return render_template('my_rentals.html',
                         my_rentals=my_rentals,
                         rentals_of_my_tools=rentals_of_my_tools)

@app.route('/rentals/<int:rental_id>/status', methods=['POST'])
@login_required
def update_rental_status(rental_id):
    try:
        rental = Rental.query.get_or_404(rental_id)

        # Allow both renter and owner to update status
        if rental.renter_id != session['user_id'] and rental.owner_id != session['user_id']:
            return jsonify({'error': 'Unauthorized'}), 403

        data = request.get_json()
        if not data or 'status' not in data:
            return jsonify({'error': 'Status not provided'}), 400

        new_status = data.get('status')

        if new_status not in ['pending', 'active', 'completed', 'cancelled']:
            return jsonify({'error': 'Invalid status'}), 400

        rental.status = new_status

        # If rental is completed or cancelled, make the tool available again
        if new_status in ['completed', 'cancelled']:
            rental.tool.is_available = True

        db.session.commit()

        return jsonify({
            'message': 'Status updated successfully',
            'new_status': new_status
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"Error updating rental status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/rentals/<int:rental_id>/complete', methods=['POST'])
@login_required
def complete_rental(rental_id):
    rental = Rental.query.get_or_404(rental_id)

    # Verify that the current user is the tool owner
    if rental.tool.owner_id != session['user_id']:
        return jsonify({'error': 'Unauthorized'}), 403

    # Only active rentals can be marked as complete
    if rental.status != 'active':
        return jsonify({'error': 'Only active rentals can be marked as complete'}), 400

    try:
        rental.status = 'completed'
        rental.tool.is_available = True  # Make the tool available again
        db.session.commit()
        return jsonify({'message': 'Rental marked as complete successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/my-rental-requests')
@login_required
def my_rental_requests():
    user_id = session['user_id']

    sent_requests = RentalRequest.query.filter_by(renter_id=user_id).order_by(RentalRequest.created_at.desc()).all()

    owned_tools_info = db.session.execute(text("""
        SELECT t.id, t.name,
               (SELECT COUNT(*) FROM rental_request WHERE tool_id = t.id) as request_count
        FROM tool t
        WHERE t.owner_id = :user_id
    """), {'user_id': user_id}).fetchall()

    owned_tool_ids = [tool.id for tool in Tool.query.filter_by(owner_id=user_id).all()]

    received_requests = RentalRequest.query.filter(
        RentalRequest.tool_id.in_(owned_tool_ids) if owned_tool_ids else False
    ).order_by(RentalRequest.created_at.desc()).all()

    return render_template('my_rental_requests.html',
                         sent_requests=sent_requests,
                         received_requests=received_requests)

@app.route('/rental-requests/<int:request_id>/handle', methods=['POST'])
@login_required
def handle_rental_request(request_id):
    print(f"Handling rental request {request_id}")
    rental_request = RentalRequest.query.get_or_404(request_id)
    tool = rental_request.tool

    if tool.owner_id != session['user_id']:
        print(f"Unauthorized access attempt - User {session['user_id']} is not the owner of tool {tool.id}")
        return jsonify({'error': 'Unauthorized'}), 403

    # Handle both JSON and form data
    if request.is_json:
        data = request.get_json()
        action = data.get('action', '').lower()  # Convert to lowercase for consistent comparison
    else:
        action = request.form.get('action', '').lower()  # Convert to lowercase for consistent comparison

    print(f"Action requested: {action}")

    if action not in ['approve', 'reject']:
        print(f"Invalid action: {action}")
        return jsonify({'error': 'Invalid action'}), 400

    if rental_request.status != 'pending':
        print(f"Request {request_id} is not pending (current status: {rental_request.status})")
        return jsonify({'error': 'Request has already been processed'}), 400

    # Check if tool is still available
    if action == 'approve' and not tool.is_available:
        print(f"Tool {tool.id} is no longer available")
        return jsonify({'error': 'Tool is no longer available'}), 400

    requester = User.query.get(rental_request.renter_id)
    print(f"Processing request from user {requester.username}")

    try:
        if action == 'approve':
            # Calculate rental duration and total price
            rental_days = (rental_request.end_date - rental_request.start_date).days
            total_price = rental_days * tool.price_per_day

            print(f"Creating rental - Days: {rental_days}, Total Price: ${total_price}")

            # Create a new rental with status 'active'
            rental = Rental(
                tool_id=tool.id,
                renter_id=rental_request.renter_id,
                owner_id=tool.owner_id,
                start_date=rental_request.start_date,
                end_date=rental_request.end_date,
                total_price=total_price,
                status='active'  # Explicitly set status to active
            )

            # Update tool and request status
            tool.is_available = False
            rental_request.status = 'approved'

            # Add and commit the rental
            db.session.add(rental)
            db.session.commit()

            print(f"Created rental {rental.id} with status: {rental.status}")

            if requester.email:
                send_notification_email(
                    'Your Rental Request was Approved!',
                    requester.email,
                    'email/request_approved.html',
                    user=requester,
                    tool=tool,
                    request=rental_request,
                    rental=rental
                )

        else:  # reject
            rental_request.status = 'rejected'
            if requester.email:
                send_notification_email(
                    'Update on Your Rental Request',
                    requester.email,
                    'email/request_rejected.html',
                    user=requester,
                    tool=tool,
                    request=rental_request
                )
            db.session.commit()
            print(f"Rejected rental request {request_id}")

        return jsonify({'message': f'Request {action}d successfully'})

    except Exception as e:
        db.session.rollback()
        print(f"Error handling rental request: {str(e)}")
        return jsonify({'error': 'An error occurred while processing your request'}), 500

def send_purchase_confirmation_email(purchase):
    buyer_email = purchase.buyer_user.email
    seller_email = purchase.seller_user.email
    tool_name = purchase.tool_details.name

    # Send email to buyer
    buyer_subject = f"Purchase Confirmation - {tool_name}"
    buyer_body = f"""
    Dear {purchase.buyer_user.username},

    Your purchase of {tool_name} has been confirmed!

    Purchase Details:
    - Tool: {tool_name}
    - Price: ${purchase.price:.2f}
    - Purchase Date: {purchase.purchase_date.strftime('%Y-%m-%d %H:%M:%S')}
    - Seller: {purchase.seller_user.username}

    Thank you for using our platform!
    """

    # Send email to seller
    seller_subject = f"Tool Sold - {tool_name}"
    seller_body = f"""
    Dear {purchase.seller_user.username},

    Your tool {tool_name} has been sold!

    Sale Details:
    - Tool: {tool_name}
    - Price: ${purchase.price:.2f}
    - Sale Date: {purchase.purchase_date.strftime('%Y-%m-%d %H:%M:%S')}
    - Buyer: {purchase.buyer_user.username}

    Thank you for using our platform!
    """

    try:
        msg_buyer = Message(buyer_subject,
                          sender=app.config['MAIL_DEFAULT_SENDER'],
                          recipients=[buyer_email],
                          body=buyer_body)
        mail.send(msg_buyer)

        msg_seller = Message(seller_subject,
                           sender=app.config['MAIL_DEFAULT_SENDER'],
                           recipients=[seller_email],
                           body=seller_body)
        mail.send(msg_seller)
    except Exception as e:
        print(f"Error sending purchase confirmation emails: {str(e)}")

@app.route('/api/tools/clear-all', methods=['DELETE'])
def clear_all_tools():
    try:
        # Delete all related records
        RentalRequest.query.delete()
        Rental.query.delete()
        Purchase.query.delete()

        # Delete all tool records
        num_deleted = Tool.query.delete()

        # Commit the transaction
        db.session.commit()

        # Delete all tool images from the filesystem
        tool_images_dir = app.config['UPLOAD_FOLDER']
        for filename in os.listdir(tool_images_dir):
            file_path = os.path.join(tool_images_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}")

        return jsonify({
            'message': 'Successfully cleared all tools and related records',
            'tools_deleted': num_deleted
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to clear tools',
            'details': str(e)
        }), 500

@app.route('/api/tools/delete-last/<int:count>', methods=['GET'])
def delete_last_n_tools(count):
    try:
        # Get the last N tools ordered by creation date
        tools_to_delete = Tool.query.order_by(Tool.created_at.desc()).limit(count).all()

        if not tools_to_delete:
            return jsonify({
                'message': 'No tools found to delete',
                'tools_deleted': 0
            }), 200

        deleted_count = 0
        deleted_tool_ids = []

        for tool in tools_to_delete:
            try:
                # Delete related records first
                RentalRequest.query.filter_by(tool_id=tool.id).delete()
                Rental.query.filter_by(tool_id=tool.id).delete()
                Purchase.query.filter_by(tool_id=tool.id).delete()

                # Delete tool images from filesystem
                for i in range(1, 4):
                    image_url = getattr(tool, f'image_url_{i}')
                    if image_url:
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(image_url))
                        try:
                            if os.path.isfile(file_path):
                                os.unlink(file_path)
                        except Exception as e:
                            print(f"Error deleting file {file_path}: {e}")

                # Delete the tool
                db.session.delete(tool)
                deleted_count += 1
                deleted_tool_ids.append(tool.id)

            except Exception as e:
                print(f"Error deleting tool {tool.id}: {e}")
                continue

        db.session.commit()

        return jsonify({
            'message': 'Successfully deleted last N tools',
            'tools_deleted': deleted_count,
            'deleted_tool_ids': deleted_tool_ids
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to delete tools',
            'details': str(e)
        }), 500

@app.route('/tools')
@login_required
def tools_categories():
    return render_template('tools.html')

@app.route('/voice-book')
@login_required
def voice_book():
    # Get category parameter if provided
    category = request.args.get('category', '')

    # Start with base query for available rental tools
    query = Tool.query.filter_by(
        is_available=True,
        listing_type='rent'  # Only show rental tools
    )

    # Apply category filter if specified
    if category:
        query = query.filter(Tool.category == category)

    # Order by creation date and get results
    tools = query.order_by(Tool.created_at.desc()).all()

    return render_template('voice_book.html', tools=tools, selected_category=category)

@app.route('/api/add-default-tools', methods=['GET'])
def add_default_tools():
    try:
        # Default tools data
        default_tools = [
            {
                "name": "John Deere Tractor",
                "category": "Tractor",
                "brand": "John Deere",
                "condition": "Good",
                "description": "Modern tractor with advanced features for efficient farming",
                "listing_type": "rent",
                "price_per_day": 1500.0,
                "power_source": "Diesel",
                "maintenance_status": "Excellent",
                "last_maintenance_date": datetime.utcnow()
            },
            {
                "name": "Harvester Machine",
                "category": "Harvester",
                "brand": "New Holland",
                "condition": "Excellent",
                "description": "High-capacity harvester for quick crop collection",
                "listing_type": "rent",
                "price_per_day": 2000.0,
                "power_source": "Diesel",
                "maintenance_status": "Good",
                "last_maintenance_date": datetime.utcnow()
            },
            {
                "name": "Modern Plow",
                "category": "Plow",
                "brand": "Mahindra",
                "condition": "Good",
                "description": "Advanced plowing equipment for better soil preparation",
                "listing_type": "sale",
                "sale_price": 25000.0,
                "power_source": "Manual",
                "maintenance_status": "Good",
                "last_maintenance_date": datetime.utcnow()
            },
            {
                "name": "Sprinkler System",
                "category": "Irrigation Equipment",
                "brand": "Rainbird",
                "condition": "New",
                "description": "Automated sprinkler system for efficient irrigation",
                "listing_type": "sale",
                "sale_price": 15000.0,
                "power_source": "Electric",
                "maintenance_status": "Excellent",
                "last_maintenance_date": datetime.utcnow()
            },
            {
                "name": "Seed Drill",
                "category": "Seeder",
                "brand": "Kubota",
                "condition": "Good",
                "description": "Precision seed drilling machine for row crops",
                "listing_type": "rent",
                "price_per_day": 800.0,
                "power_source": "Manual",
                "maintenance_status": "Good",
                "last_maintenance_date": datetime.utcnow()
            }
        ]

        # Get the first admin user or create one if doesn't exist
        admin_user = User.query.filter_by(email="admin@example.com").first()
        if not admin_user:
            # Create admin user with hashed password
            hashed_password = generate_password_hash("admin123")
            admin_user = User(
                username="admin",
                email="admin@example.com",
                password_hash=hashed_password,
                mobile="1234567890"  # Changed from phone to mobile to match your User model
            )
            db.session.add(admin_user)
            db.session.commit()

        # Add tools to database
        tools_added = 0
        for tool_data in default_tools:
            tool = Tool(
                owner_id=admin_user.id,
                is_available=True,
                **tool_data
            )
            db.session.add(tool)
            tools_added += 1

        db.session.commit()

        return jsonify({
            'message': 'Default tools added successfully',
            'tools_added': tools_added
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'error': 'Failed to add default tools',
            'details': str(e)
        }), 500

# Create database tables
def init_db():
    print("Initializing database...")
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")

if __name__ == '__main__':
    init_db()   # Initialize database if tables don't exist
    app.run(debug=True, port=5002)

# Configuration
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
RECORD_SECONDS = 5  # Default recording duration
WAVE_OUTPUT_DIR = "recordings"

# Ensure recordings directory exists
if not os.path.exists(WAVE_OUTPUT_DIR):
    os.makedirs(WAVE_OUTPUT_DIR)

# Global variables for recording state
recording = False
audio = pyaudio.PyAudio()
frames = []
current_recording_thread = None

def generate_filename():
    """Generate a unique filename based on timestamp"""
    return os.path.join(WAVE_OUTPUT_DIR, f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")

def record_audio():
    """Function to record audio"""
    global recording, frames
    frames = []

    stream = audio.open(format=FORMAT,
                       channels=CHANNELS,
                       rate=RATE,
                       input=True,
                       frames_per_buffer=CHUNK)

    print("* recording")

    while recording:
        data = stream.read(CHUNK)
        frames.append(data)

    print("* done recording")

    stream.stop_stream()
    stream.close()

def save_audio(filename):
    """Save recorded audio to file"""
    wf = wave.open(filename, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

@app.route('/')
def index():
    return render_template('voice_book.html')

@app.route('/start_recording', methods=['POST'])
def start_recording():
    global recording, current_recording_thread

    if recording:
        return jsonify({"status": "error", "message": "Recording already in progress"})

    recording = True
    current_recording_thread = threading.Thread(target=record_audio)
    current_recording_thread.start()

    return jsonify({"status": "success", "message": "Recording started"})

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    try:
        if 'audio' not in request.files:
            print("No audio file in request")
            return jsonify({
                "status": "error",
                "message": "No audio file received"
            })

        audio_file = request.files['audio']
        if not audio_file:
            print("Empty audio file")
            return jsonify({
                "status": "error",
                "message": "Empty audio file"
            })

        # Create a temporary directory if it doesn't exist
        if not os.path.exists(WAVE_OUTPUT_DIR):
            os.makedirs(WAVE_OUTPUT_DIR)

        # Save the uploaded file temporarily
        temp_filename = os.path.join(WAVE_OUTPUT_DIR, f"temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
        print(f"Saving audio to: {temp_filename}")
        audio_file.save(temp_filename)

        # Initialize speech recognition
        recognizer = sr.Recognizer()

        try:
            with sr.AudioFile(temp_filename) as source:
                print("Reading audio file...")
                # Adjust for ambient noise
                recognizer.adjust_for_ambient_noise(source, duration=0.5)

                # Record audio from file
                audio_data = recognizer.record(source)

                print("Performing speech recognition...")
                # Attempt speech recognition with increased timeout
                text = recognizer.recognize_google(
                    audio_data,
                    language='en-US',
                    show_all=False  # Set to True for debugging
                )

                print(f"Recognition result: {text}")
                response = {
                    "status": "success",
                    "message": "Recording processed successfully",
                    "text": text
                }

        except sr.UnknownValueError as e:
            print(f"Speech recognition failed: {str(e)}")
            response = {
                "status": "error",
                "message": "Could not understand audio. Please speak clearly and try again.",
                "text": None
            }
        except sr.RequestError as e:
            print(f"Speech recognition request error: {str(e)}")
            response = {
                "status": "error",
                "message": f"Speech recognition service error: {str(e)}",
                "text": None
            }
        except Exception as e:
            print(f"Unexpected error during speech recognition: {str(e)}")
            response = {
                "status": "error",
                "message": "An unexpected error occurred during speech recognition",
                "text": None
            }
        finally:
            # Cleanup temporary file
            try:
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
                    print(f"Temporary file removed: {temp_filename}")
            except Exception as e:
                print(f"Error removing temporary file {temp_filename}: {e}")

        return jsonify(response)

    except Exception as e:
        print(f"Global error in stop_recording: {str(e)}")
        return jsonify({
            "status": "error",
            "message": "Server error processing audio",
            "text": None
        })  # Run on a different port to avoid conflict
