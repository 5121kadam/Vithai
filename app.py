# app.py
from flask import Flask, render_template, request, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask import jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os
from urllib.parse import unquote, quote


app = Flask(__name__)
app.secret_key = os.urandom(24)
# Ensure proper database URI configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///ganesh.db').replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    address = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=True)  # Changed to nullable
    password_hash = db.Column(db.String(128))

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')
    
    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)

class Idol(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    material = db.Column(db.String(20))  # 'POP' or 'Shadu'
    sizes = db.relationship('IdolSize', backref='idol', lazy=True)
    patterns = db.relationship('Pattern', backref='idol', lazy=True)

class IdolSize(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    idol_id = db.Column(db.Integer, db.ForeignKey('idol.id'), nullable=False)
    size = db.Column(db.String(50), nullable=False)  # e.g., "12 inches"
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(100))  # Path to image

class Pattern(db.Model):
    id = db.Column(db.Integer, primary_key=True)
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
    if 'user_id' not in session:
        return redirect(url_for('register'))
    return redirect(url_for('catalog'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            name = request.form['name']
            phone = request.form['phone']
            address = request.form['address']
            email = request.form.get('email', '').strip()
            password = request.form['password']

             # Check if user exists
            existing_user = User.query.filter(
            (User.email == email) | (User.phone == phone)
            ).first()

            if existing_user:
                return render_template('register.html', 
                               error="User already exists",
                               form_data=request.form)

            # Debug print (check Render logs)
            print(f"Attempting to register: {name}, {phone}, {email}")

            new_user = User(
                name=name,
                phone=phone,
                address=address,
                email=email if email else None,
                password=password  # This will hash automatically
            )
            
            db.session.add(new_user)
            db.session.commit()
            
            print(f"Successfully registered user ID: {new_user.id}")  # Check logs
            session['user_id'] = new_user.id
            return redirect(url_for('catalog'))

        except Exception as e:
            db.session.rollback()
            print(f"Registration error: {str(e)}")  # Check logs
            return render_template('register.html', error="Registration failed")

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('catalog'))
        
    if request.method == 'POST':
        identifier = request.form['identifier']  # Can be email or phone
        password = request.form['password']
        
        # Check if identifier is email or phone
        if '@' in identifier:
            user = User.query.filter_by(email=identifier).first()
        else:
            user = User.query.filter_by(phone=identifier).first()
        
        if user and user.verify_password(password):
            session['user_id'] = user.id
            return redirect(url_for('catalog'))
        
        return render_template('login.html', error="Invalid credentials")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/testdb')
def testdb():
    try:
        # Try to fetch users
        users = User.query.all()
        return f"Database connection working. Users: {len(users)}"
    except Exception as e:
        return f"Database error: {str(e)}", 500

@app.route('/catalog')
def catalog():
    if 'user_id' not in session:
        return redirect(url_for('register'))
    
    try:
        # Eager load sizes to prevent N+1 queries
        idols = Idol.query.options(db.joinedload(Idol.sizes)).all()
        
        # Verify each idol has at least one size
        for idol in idols:
            if not idol.sizes:
                app.logger.warning(f"Idol {idol.id} has no sizes assigned")
        
        return render_template('catalog.html', idols=idols)
    except Exception as e:
        app.logger.error(f"Error loading catalog: {str(e)}")
        return render_template('error.html', message="Could not load catalog"), 500

@app.route('/idol/<int:idol_id>')
def idol_detail(idol_id):
    if 'user_id' not in session:
        return redirect(url_for('register'))
    
    idol = Idol.query.get_or_404(idol_id)
    return render_template('idol_detail.html', idol=idol)

@app.route('/idol/<int:idol_id>/<material>')
def idol_material(idol_id, material):
    if 'user_id' not in session:
        return redirect(url_for('register'))
    
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
@app.route('/add_to_cart/<int:idol_id>/<material>/<path:size>')
def add_to_cart(idol_id, material, size):
    if 'user_id' not in session:
        return jsonify({'error': 'Please login first'}), 401
    
    # Decode URL-encoded size (e.g., "12%20inches" -> "12 inches")
    size = unquote(size)
    
    idol = Idol.query.get_or_404(idol_id)
    size_obj = IdolSize.query.filter_by(idol_id=idol_id, size=size).first()
    
    if not size_obj:
        return jsonify({'error': 'Invalid size selected'}), 400
    
    # Initialize cart if not exists
    if 'cart' not in session:
        session['cart'] = []
    
    # Add item to cart
    cart_item = {
        'idol_id': idol.id,
        'name': idol.name,
        'material': material,
        'size': size,
        'price': size_obj.price,
        'image': size_obj.image,
        'pattern': request.args.get('pattern', 'Default')  # Optional pattern selection
    }
    
    session['cart'].append(cart_item)
    session.modified = True
    
    return jsonify({
        'success': True,
        'cart_count': len(session['cart']),
        'message': 'Item added to cart'
    })

@app.route('/checkout')
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('catalog'))
    
    total = sum(item['price'] for item in session['cart'])
    return render_template('checkout.html', cart=session['cart'], total=total)

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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_sample_data()
    app.run(debug=True)
    from app import db, User
    print(User.query.all())  # Should show all users without duplicates