# app.py
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ganesh.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    address = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=True)  # Changed to nullable

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
        
        # Create users
        users = [
            User(name="Admin", phone="9876543210", address="123 Temple St", email="admin@example.com"),
            User(name="Test User", phone="1234567890", address="456 Test Ave", email="user@example.com")
        ]
        db.session.add_all(users)
        
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
        name = request.form['name']
        phone = request.form['phone']
        address = request.form['address']
        email = request.form.get('email', '').strip()  # Optional field
        
        try:
            # Check if email already exists (only if provided)
            if email:
                existing_user = User.query.filter_by(email=email).first()
                if existing_user:
                    return render_template('register.html', 
                                       error="Email already registered",
                                       form_data=request.form)
            
            # Check if phone already exists
            existing_phone = User.query.filter_by(phone=phone).first()
            if existing_phone:
                return render_template('register.html',
                                   error="Phone number already registered",
                                   form_data=request.form)
            
            user = User(name=name, phone=phone, address=address, email=email if email else None)
            db.session.add(user)
            db.session.commit()
            
            session['user_id'] = user.id
            return redirect(url_for('catalog'))
            
        except Exception as e:
            db.session.rollback()
            return render_template('register.html', 
                               error="Registration failed. Please try again.",
                               form_data=request.form)
    
    return render_template('register.html')

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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_sample_data()
    app.run(debug=True)
    from app import db, User
    print(User.query.all())  # Should show all users without duplicates