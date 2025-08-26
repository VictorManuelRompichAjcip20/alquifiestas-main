from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

# Inicialización de Flask
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tu-clave-secreta-muy-segura')

# Configuración de la base de datos
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    # Producción - Render proporciona DATABASE_URL automáticamente
    # Convertir postgresql:// a postgresql+psycopg:// para psycopg3
    if DATABASE_URL.startswith('postgresql://'):
        DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)
    elif DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    # Desarrollo - conectar directo a tu base en Render con psycopg3
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg://alquifiestas_user:OGKpbEmUIefuJ2R8YRJ8AUo7ZmlfNFW1@dpg-d2me99ogjchc73ci0mf0-a.oregon-postgres.render.com:5432/alquifiestas'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Modelo de usuario
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'is_admin': self.is_admin,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

def create_default_users():
    """Crear usuarios por defecto si no existen"""
    try:
        # Verificar si existen usuarios
        if User.query.count() == 0:
            # Crear admin
            admin = User(
                username='admin',
                password='admin123',
                is_admin=True
            )
            db.session.add(admin)
            
            # Crear usuario normal
            user = User(
                username='usuario',
                password='user123',
                is_admin=False
            )
            db.session.add(user)
            
            db.session.commit()
            print("Usuarios por defecto creados")
        else:
            print("Usuarios ya existen")
            
    except Exception as e:
        print(f"Error creando usuarios por defecto: {str(e)}")

def authenticate_user(username, password):
    """Función para autenticar usuario"""
    try:
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            return user.to_dict()
        return None
    except Exception as e:
        print(f"Error en authenticate_user: {str(e)}")
        return None

def create_user(username, password, is_admin=False):
    """Función para crear nuevo usuario"""
    try:
        # Verificar si el usuario ya existe
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return None
        
        # Crear nuevo usuario
        new_user = User(
            username=username,
            password=password,
            is_admin=is_admin
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        return new_user.id
        
    except Exception as e:
        print(f"Error en create_user: {str(e)}")
        return None

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/register_page')
def register_page():
    return render_template('register.html')

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({
                'success': False,
                'message': 'Usuario y contraseña son requeridos'
            }), 400
        
        user_data = authenticate_user(username, password)
        
        if user_data:
            session['user'] = username
            session['user_id'] = user_data['id']
            session['user_name'] = username
            session['is_admin'] = user_data['is_admin']
            
            return jsonify({
                'success': True,
                'message': 'Login exitoso',
                'is_admin': user_data['is_admin']
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Usuario o contraseña incorrectos'
            }), 401
            
    except Exception as e:
        print(f"Error en login: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error en el servidor'
        }), 500

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({
                'success': False,
                'message': 'Usuario y contraseña son requeridos'
            }), 400
        
        user_id = create_user(username, password)
        
        if user_id:
            return jsonify({
                'success': True,
                'message': 'Usuario registrado exitosamente'
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': 'Error al registrar usuario. Usuario ya existe.'
            }), 400
            
    except Exception as e:
        print(f"Error en register: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error en el servidor'
        }), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('index'))
    
    user_info = {
        'username': session.get('user'),
        'name': session.get('user_name'),
        'is_admin': session.get('is_admin', False)
    }
    
    return render_template('dashboard.html', user=user_info)

@app.route('/admin')
def admin():
    if 'user' not in session or not session.get('is_admin'):
        return redirect(url_for('dashboard'))
    return render_template('admin.html')

@app.route('/api/users')
def get_users():
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        users = User.query.all()
        users_list = [user.to_dict() for user in users]
        
        return jsonify({
            'success': True,
            'users': users_list
        })
        
    except Exception as e:
        print(f"Error en get_users: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error en el servidor'
        }), 500

# Inicializar base de datos al cargar la aplicación
try:
    with app.app_context():
        db.create_all()
        create_default_users()
        print("Base de datos inicializada")
except Exception as e:
    print(f"Error inicializando DB: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print("Iniciando aplicación Flask con SQLAlchemy...")
    app.run(host='0.0.0.0', port=port, debug=False)
