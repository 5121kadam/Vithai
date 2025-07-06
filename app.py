# app.py
from flask import Flask, flash, render_template, request, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask import jsonify
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
import os
from urllib.parse import unquote, quote, urlparse
from sqlalchemy.exc import IntegrityError


app = Flask(__name__)
app.secret_key = os.urandom(24)
# Ensure proper database URI configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://ganesh.db').replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database configuration
def get_database_uri():
    if 'DATABASE_URL' in os.environ:  # Production (Render)
        uri = os.environ['DATABASE_URL']
        if uri.startswith('postgres://'):
            uri = uri.replace('postgres://', 'postgresql://', 1)
        return uri
    return 'postgresql://ganeshdb:ZfTm9fo82DHKV0XDoHvrPTJkTRcy0HgQ@dpg-d1l4c66mcj7s73bpa1e0-a.singapore-postgres.render.com/ganeshdb'  # Development

app.config['SQLALCHEMY_DATABASE_URI'] = get_database_uri()
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,  # Recycle connections after 5 minutes
}

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    __tablename__ = 'app_user'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(100))
    password_hash = db.Column(db.String(128))
    
    # Required methods for Flask-Login
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_active(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self.id)
    
    # Password handling
    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')
    
    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

class Idol(db.Model):
    __tablename__ = 'idol'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    material = db.Column(db.String(20),  nullable=False)  # 'POP' or 'Shadu'
    sizes = db.relationship('IdolSize', backref='idol', lazy=True)
    patterns = db.relationship('Pattern', backref='idol', lazy=True)

class IdolSize(db.Model):
    __tablename__ = 'idol_size'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idol_id = db.Column(db.Integer, db.ForeignKey('idol.id'), nullable=False)
    size = db.Column(db.String(50), nullable=False)  # e.g., "12 inches"
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(100),default='static/images/default.jpg')  # Path to image

class Pattern(db.Model):
    __tablename__ = 'pattern'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idol_id = db.Column(db.Integer, db.ForeignKey('idol.id'), nullable=False)
    name = db.Column(db.String(100))
    image = db.Column(db.String(100))

def create_sample_data():
    if not User.query.first():
        # Clear existing data
        db.session.query(User).delete()
        db.session.query(Idol).delete()
        db.session.query(IdolSize).delete()
        db.session.query(Pattern).delete()
        
        if not User.query.first():
            admin = User(
                name="Admin",
                phone="9876543210",
                address="123 Temple St, Mumbai",
                email="admin@ganeshidols.com",
                password="admin123"  # Will be hashed
            )
            db.session.add(admin)
        
        # Create idols with sizes
        ganesh1 = Idol(name="Sitting Ganesh", material="Both")
        ganesh2 = Idol(name="Dancing Ganesh", material="POP")
        
        # Create sizes
        sizes = [
            IdolSize(size="12 inches", price=1500, image="golden.jpg", idol=ganesh1),
            IdolSize(size="18 inches", price=2500, image="marble.jpg", idol=ganesh1),
            IdolSize(size="24 inches", price=3500, image="golden.jpg", idol=ganesh2)
        ]
        
        # Create patterns
        patterns = [
            Pattern(name="Traditional", image="golden.jpg", idol=ganesh1),
            Pattern(name="Modern", image="marble.jpg", idol=ganesh1)
        ]
        db.session.add_all([ganesh1, ganesh2] + sizes + patterns)
        db.session.commit()

# Routes
@app.route('/')
def home():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return redirect(url_for('catalog'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form['name']
            phone = request.form['phone']
            email = request.form.get('email')
            address = request.form['address']
            password = request.form['password']

            existing_user = User.query.filter_by(phone=phone).first()
            if existing_user:
                # Show error message: phone already registered
                return render_template('register.html', error="Phone number already registered.")
            
            # Check if email already exists
            existing_user = db.session.query(User).filter_by(email=email).first()
            if existing_user:
                return render_template('register.html', error="Email already registered.")
            
            # Create new user with hashed password
            new_user = User(
                name=name,
                phone=phone,
                email=email,
                address=address
            )
            new_user.password = password  # This will hash the password
            
            db.session.add(new_user)
            db.session.commit()
            
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            return render_template('register.html', error=str(e))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('catalog'))
        
    if request.method == 'POST':
        identifier = request.form['identifier']
        password = request.form['password']
        
        user = User.query.filter((User.email == identifier) | (User.phone == identifier)).first()
        
        if user and user.verify_password(password):
            login_user(user)
            next_page = request.args.get('next') or url_for('catalog')
            return redirect(next_page)
            
        #flash('Invalid credentials', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()  # Clear all session data
    #flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/testdb')
def testdb():
    users = db.session.query(User).all()
    user_list = []
    for user in users:
        user_list.append({
            "id": user.id,
            "name": user.name,
            "phone": user.phone,
            "address": user.address,
            "email": user.email
            # Do not include password_hash for security
        })
    return {"users": user_list}

@app.route('/catalog')
@login_required
def catalog():
    try:
        # Eager load sizes to prevent N+1 queries
        idols = Idol.query.options(db.joinedload(Idol.sizes)).all()
        
        # Verify and prepare data for template
        catalog_data = []
        for idol in idols:
            # Ensure we have valid data
            if not idol.name or not idol.sizes:
                app.logger.warning(f"Skipping idol {idol.id} - missing name or sizes")
                continue
            
            # Prepare sizes with safe defaults
            sizes = []
            for size in idol.sizes:
                sizes.append({
                    'id': size.id,
                    'size': size.size or 'N/A',
                    'price': size.price or 0.00,
                    'image': size.image or 'default.jpg'  # Provide default image
                })
            
            catalog_data.append({
                'id': idol.id,
                'name': idol.name or 'Unnamed Idol',
                'material': idol.material or 'Unknown',
                'sizes': sizes
            })
        
        return render_template('catalog.html', idols=catalog_data)
    
    except Exception as e:
        app.logger.error(f"Error loading catalog: {str(e)}")
        return render_template('error.html', message="Could not load catalog"), 500

@app.route('/idol/<int:idol_id>')
@login_required  # Use Flask-Login decorator
def idol_detail(idol_id):
    idol = Idol.query.get_or_404(idol_id)
    return render_template('idol_detail.html', idol=idol)

@app.route('/idol/<int:idol_id>/<material>')
def idol_material(idol_id, material):
    # Check authentication using Flask-Login instead of raw session
    if not current_user.is_authenticated:
        # Store intended URL before redirecting to login
        session['next'] = request.url
        return redirect(url_for('login'))  # Redirect to login instead of register
    
    idol = Idol.query.get_or_404(idol_id)
    
    if material not in ['POP', 'Shadu']:
        return redirect(url_for('idol_detail', idol_id=idol_id))
    
    sizes = IdolSize.query.filter_by(idol_id=idol_id).all()
    patterns = Pattern.query.filter_by(idol_id=idol_id).all()
    
    return render_template('idol_options.html', 
                         idol=idol,
                         material=material,
                         sizes=sizes,
                         patterns=patterns)

# Add these new routes
@app.route('/add_to_cart', methods=['POST'])
@login_required
def add_to_cart():
    # Get data from form submission
    idol_id = request.form.get('idol_id')
    material = request.form.get('material')
    size = request.form.get('size')
    
    # Validate required fields
    if not all([idol_id, material, size]):
        flash('Missing required cart information', 'error')
        return redirect(url_for('catalog'))
    
    try:
        idol_id = int(idol_id)
        idol = Idol.query.get_or_404(idol_id)
        size_obj = IdolSize.query.filter_by(idol_id=idol_id, size=size).first()
        
        if not size_obj:
            flash('Invalid size selected', 'error')
            return redirect(url_for('idol_material', idol_id=idol_id, material=material))
        
        # Initialize cart if not exists
        if 'cart' not in session:
            session['cart'] = []
        
        # Add item to cart
        session['cart'].append({
            'idol_id': idol.id,
            'name': idol.name,
            'material': material,
            'size': size,
            'price': size_obj.price,
            'image': size_obj.image or 'default.jpg'
        })
        session.modified = True
        
        # Redirect directly to checkout instead of showing message
        return redirect(url_for('checkout'))
    
    except Exception as e:
        app.logger.error(f"Error adding to cart: {str(e)}")
        flash('Error adding item to cart', 'error')
        return redirect(url_for('catalog'))

@app.route('/checkout')
@login_required
def checkout():
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('catalog'))
    
    # Get user information
    user = User.query.get(current_user.id)
    if not user:
        flash('User information not found', 'error')
        return redirect(url_for('login'))
    
    # Calculate total
    total = sum(item['price'] for item in session['cart'])
    
    # Prepare cart items with full details
    cart_items = []
    for item in session['cart']:
        idol = Idol.query.get(item['idol_id'])
        cart_items.append({
            'idol': idol,
            'material': item['material'],
            'size': item['size'],
            'price': item['price'],
            'image': item['image']
        })
    
    return render_template('checkout.html', 
                         cart=cart_items,
                         total=total,
                         user=user)

@app.route('/initiate_contact')
def initiate_contact():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    dealer_phone = "+917083502769"  # Your dealer's phone number
    
    # Prepare WhatsApp message
    cart_details = "\n".join(
        f"{item['name']} ({item['material']}, {item['size']}) - ₹{item['price']}"
        for item in session.get('cart', [])
    )
    
    whatsapp_message = (
        f"Hello, I'm interested in purchasing:\n{cart_details}\n\n"
        f"My details:\nName: {user.name}\nPhone: {user.phone}"
    )
    
    whatsapp_url = f"https://wa.me/{dealer_phone}?text={quote(whatsapp_message)}"
    
    return render_template('contact_options.html', 
                         whatsapp_url=whatsapp_url,
                         phone_number=dealer_phone)

@app.route('/confirm_order', methods=['POST'])
@login_required
def confirm_order():
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('catalog'))
    
    try:
        user = User.query.get(current_user.id)
        if not user:
            flash('User information not found', 'error')
            return redirect(url_for('login'))
        
        # Prepare cart details for the dealer
        cart_details = "\n".join(
            f"{item['name']} ({item['material']}, {item['size']}) - ₹{item['price']}"
            for item in session.get('cart', [])
        )
        
        whatsapp_message = (
            f"Hello, I'm interested in purchasing:\n{cart_details}\n\n"
            f"My details:\nName: {user.name}\nPhone: {user.phone}\n"
            f"Address: {user.address}"
        )
        
        dealer_phone = "+917083502769"  # Your dealer's phone number
        whatsapp_url = f"https://wa.me/{dealer_phone}?text={quote(whatsapp_message)}"
        
        # Don't clear cart yet - let dealer confirm first
        return render_template('contact_options.html',
                            whatsapp_url=whatsapp_url,
                            phone_number=dealer_phone,
                            cart=session['cart'])
    
    except Exception as e:
        app.logger.error(f"Error confirming order: {str(e)}")
        flash('Error processing your order', 'error')
        return redirect(url_for('checkout'))

@app.route('/order_completed')
@login_required
def order_completed():
    # Clear the cart after successful order
    session.pop('cart', None)
    flash('Your order has been received! The dealer will contact you shortly.', 'success')
    return redirect(url_for('catalog'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        #create_sample_data()
    app.run(debug=True)
    from app import db, User
    print(User.query.all())  # Should show all users without duplicates