from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime, time
from decimal import Decimal
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

# ===============================================
# FUNCIONES AUXILIARES PARA BASE DE DATOS
# ===============================================

from datetime import date, datetime, time
from decimal import Decimal

def serialize_database_row(row_dict):
    """Convierte tipos de datos PostgreSQL a JSON serializable"""
    for key, value in row_dict.items():
        if isinstance(value, time):
            row_dict[key] = value.strftime('%H:%M:%S')
        elif isinstance(value, date) and not isinstance(value, datetime):
            row_dict[key] = value.isoformat()
        elif isinstance(value, datetime):
            row_dict[key] = value.isoformat()
        elif isinstance(value, Decimal):
            row_dict[key] = float(value)
    return row_dict

def authenticate_user(username, password):
    """Función para autenticar usuario"""
    try:
        cursor = db.session.connection().connection.cursor()
        cursor.execute("""
            SELECT id, username, email, full_name, is_admin, is_active
            FROM users 
            WHERE username = %s AND password = %s AND is_active = true
        """, (username, password))
        
        result = cursor.fetchone()
        if result:
            columns = ['id', 'username', 'email', 'full_name', 'is_admin', 'is_active']
            user_data = dict(zip(columns, result))
            
            # Actualizar último login
            cursor.execute("""
                UPDATE users 
                SET last_login = CURRENT_TIMESTAMP 
                WHERE id = %s
            """, (user_data['id'],))
            db.session.commit()
            
            return user_data
        return None
    except Exception as e:
        print(f"Error en authenticate_user: {str(e)}")
        return None

def create_user(username, password, email, full_name=None, is_admin=False):
    """Función para crear nuevo usuario"""
    try:
        cursor = db.session.connection().connection.cursor()
        
        # Verificar si el usuario ya existe
        cursor.execute("""
            SELECT id FROM users 
            WHERE username = %s OR email = %s
        """, (username, email))
        
        if cursor.fetchone():
            return None
        
        # Crear nuevo usuario
        cursor.execute("""
            INSERT INTO users (username, email, password, full_name, is_admin)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (username, email, password, full_name or username, is_admin))
        
        user_id = cursor.fetchone()[0]
        db.session.commit()
        
        return user_id
        
    except Exception as e:
        db.session.rollback()
        print(f"Error en create_user: {str(e)}")
        return None

def get_user_info(user_id):
    """Obtener información completa del usuario"""
    try:
        cursor = db.session.connection().connection.cursor()
        cursor.execute("""
            SELECT u.*, c.id_cliente, c.telefono as cliente_telefono, c.direccion as cliente_direccion,
                   a.id_admin, a.telefono as admin_telefono, a.direccion as admin_direccion
            FROM users u
            LEFT JOIN clientes c ON u.id = c.user_id
            LEFT JOIN administradores a ON u.id = a.user_id
            WHERE u.id = %s
        """, (user_id,))
        
        columns = [desc[0] for desc in cursor.description]
        result = cursor.fetchone()
        
        if result:
            return dict(zip(columns, result))
        return None
        
    except Exception as e:
        print(f"Error obteniendo info usuario: {str(e)}")
        return None

# ===============================================
# RUTAS BÁSICAS
# ===============================================

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
            session['user_name'] = user_data['full_name']
            session['is_admin'] = user_data['is_admin']
            
            # Verificar si es cliente
            cursor = db.session.connection().connection.cursor()
            cursor.execute("SELECT id_cliente FROM clientes WHERE user_id = %s", (user_data['id'],))
            cliente = cursor.fetchone()
            
            session['is_client'] = cliente is not None
            if cliente:
                session['cliente_id'] = cliente[0]
            
            return jsonify({
                'success': True,
                'message': 'Login exitoso',
                'is_admin': user_data['is_admin'],
                'is_client': session['is_client'],
                'redirect': '/client_dashboard' if session['is_client'] else '/dashboard'
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
        email = data.get('email')
        full_name = data.get('full_name')
        
        if not username or not password or not email:
            return jsonify({
                'success': False,
                'message': 'Usuario, contraseña y email son requeridos'
            }), 400
        
        # Crear usuario
        user_id = create_user(username, password, email, full_name, is_admin=False)
        
        if user_id:
            # Crear registro de cliente automáticamente
            try:
                cursor = db.session.connection().connection.cursor()
                cursor.execute("""
                    INSERT INTO clientes (user_id, nombre, telefono, direccion)
                    VALUES (%s, %s, %s, %s)
                """, (
                    user_id,
                    full_name or username,
                    data.get('telefono', ''),
                    data.get('direccion', '')
                ))
                db.session.commit()
            except Exception as e:
                print(f"Error creando cliente: {str(e)}")
            
            return jsonify({
                'success': True,
                'message': 'Usuario registrado exitosamente'
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': 'Error al registrar usuario. El usuario o email ya existe.'
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
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return render_template('login.html')
    
    # Si es cliente, renderizar dashboard de cliente
    if session.get('is_client'):
        return render_template('client_dashboard.html')
    
    user_info = {
        'username': session.get('user'),
        'name': session.get('user_name'),
        'is_admin': session.get('is_admin', False)
    }
    
    return render_template('admin_dashboard.html', user=user_info)

@app.route('/client_dashboard')
def client_dashboard():
    if 'user' not in session:
        return render_template('login.html')
    
    # Verificar si es cliente
    if not session.get('is_client'):
        user_info = {
            'username': session.get('user'),
            'name': session.get('user_name'),
            'is_admin': session.get('is_admin', False)
        }
        return render_template('admin_dashboard.html', user=user_info)
    
    return render_template('client_dashboard.html')

@app.route('/admin')
def admin():
    if 'user' not in session or not session.get('is_admin'):
        return render_template('client_dashboard.html')
    return render_template('admin_dashboard.html')

# ===============================================
# RUTAS API PARA CLIENTES
# ===============================================

@app.route('/api/cliente_info', methods=['GET'])
def get_cliente_info():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    try:
        user_info = get_user_info(session.get('user_id'))
        
        if user_info:
            return jsonify({
                'success': True,
                'cliente': {
                    'id_cliente': user_info.get('id_cliente'),
                    'nombre': user_info.get('full_name'),
                    'username': user_info.get('username'),
                    'email': user_info.get('email'),
                    'telefono': user_info.get('cliente_telefono'),
                    'direccion': user_info.get('cliente_direccion')
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Usuario no encontrado'
            }), 404
            
    except Exception as e:
        print(f"Error obteniendo info cliente: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error obteniendo información'
        }), 500

@app.route('/api/servicios', methods=['GET'])
def get_servicios():
    try:
        cursor = db.session.connection().connection.cursor()
        cursor.execute("SELECT * FROM servicios ORDER BY nombre_servicio")
        
        columns = [desc[0] for desc in cursor.description]
        servicios = []
        
        for row in cursor.fetchall():
            servicio = dict(zip(columns, row))
            servicios.append(servicio)
        
        return jsonify({
            'success': True,
            'servicios': servicios
        })
        
    except Exception as e:
        print(f"Error obteniendo servicios: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error obteniendo servicios'
        }), 500

@app.route('/api/articulos', methods=['GET'])
def get_articulos():
    try:
        cursor = db.session.connection().connection.cursor()
        cursor.execute("SELECT * FROM articulos WHERE cantidad_total > 0 ORDER BY nombre_articulo")
        
        columns = [desc[0] for desc in cursor.description]
        articulos = []
        
        for row in cursor.fetchall():
            articulo = dict(zip(columns, row))
            articulos.append(articulo)
        
        return jsonify({
            'success': True,
            'articulos': articulos
        })
        
    except Exception as e:
        print(f"Error obteniendo artículos: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error obteniendo artículos'
        }), 500

@app.route('/api/eventos', methods=['POST'])
def create_evento():
    if 'user' not in session or not session.get('is_client'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    try:
        data = request.get_json()
        
        # Obtener cliente ID
        cursor = db.session.connection().connection.cursor()
        cursor.execute("SELECT id_cliente FROM clientes WHERE user_id = %s", (session.get('user_id'),))
        result = cursor.fetchone()
        
        if not result:
            return jsonify({'success': False, 'message': 'Cliente no encontrado'}), 404
        
        cliente_id = result[0]
        
        # PRIMERO: Verificar y apartar stock ANTES de crear el evento
        servicios = data.get('servicios', [])
        for servicio in servicios:
            if servicio.get('tipo') == 'articulo':
                # Verificar stock disponible
                cursor.execute("""
                    SELECT cantidad_total FROM articulos 
                    WHERE id_articulo = %s
                """, (servicio.get('id_articulo'),))
                
                stock_actual = cursor.fetchone()
                if not stock_actual or stock_actual[0] < servicio.get('cantidad', 1):
                    return jsonify({
                        'success': False,
                        'message': f'Stock insuficiente para {servicio.get("nombre")}. Disponible: {stock_actual[0] if stock_actual else 0}'
                    }), 400
                
                # Apartar stock (reducir cantidad disponible)
                cursor.execute("""
                    UPDATE articulos 
                    SET cantidad_total = cantidad_total - %s
                    WHERE id_articulo = %s
                """, (servicio.get('cantidad', 1), servicio.get('id_articulo')))
        
        # SEGUNDO: Crear evento
        cursor.execute("""
            INSERT INTO eventos (id_cliente, fecha_evento, hora_inicio, hora_fin, estado, monto_total)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id_evento
        """, (
            cliente_id,
            data.get('fecha_evento'),
            data.get('hora_inicio'),
            data.get('hora_fin'),
            'reservado',
            data.get('monto_total', 0)
        ))
        
        evento_id = cursor.fetchone()[0]
        
        # TERCERO: Agregar detalles del evento
        for servicio in servicios:
            cursor.execute("""
                INSERT INTO detalle_evento (id_evento, id_articulo, cantidad, precio_unitario)
                VALUES (%s, %s, %s, %s)
            """, (
                evento_id,
                servicio.get('id_articulo'),
                servicio.get('cantidad', 1),
                servicio.get('precio_unitario')
            ))
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Evento creado exitosamente y stock apartado',
            'evento_id': evento_id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creando evento: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error creando evento'
        }), 500

@app.route('/api/mis_eventos', methods=['GET'])
def get_mis_eventos():
    if 'user' not in session or not session.get('is_client'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    try:
        cursor = db.session.connection().connection.cursor()
        # Corregido: JOIN con users para obtener el email
        cursor.execute("""
            SELECT e.*, c.nombre as cliente_nombre, c.telefono, u.email
            FROM eventos e
            JOIN clientes c ON e.id_cliente = c.id_cliente
            JOIN users u ON c.user_id = u.id
            WHERE c.user_id = %s
            ORDER BY e.fecha_evento DESC
        """, (session.get('user_id'),))
        
        columns = [desc[0] for desc in cursor.description]
        eventos = []
        
        for row in cursor.fetchall():
            evento = dict(zip(columns, row))
            evento = serialize_database_row(evento)
            
            # Obtener detalles del evento
            cursor.execute("""
                SELECT de.*, a.nombre_articulo, a.tipo
                FROM detalle_evento de
                JOIN articulos a ON de.id_articulo = a.id_articulo
                WHERE de.id_evento = %s
            """, (evento['id_evento'],))
            
            detalle_columns = [desc[0] for desc in cursor.description]
            detalles = []
            
            for detalle_row in cursor.fetchall():
                detalle = dict(zip(detalle_columns, detalle_row))
                detalle = serialize_database_row(detalle)
                detalles.append(detalle)
            
            evento['detalles'] = detalles
            eventos.append(evento)
        
        return jsonify({
            'success': True,
            'eventos': eventos
        })
        
    except Exception as e:
        print(f"Error obteniendo eventos: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error obteniendo eventos'
        }), 500

@app.route('/api/pagos', methods=['POST'])
def procesar_pago():
    if 'user' not in session or not session.get('is_client'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    try:
        data = request.get_json()
        
        # Verificar que el evento pertenece al cliente
        cursor = db.session.connection().connection.cursor()
        cursor.execute("""
            SELECT e.id_evento, e.monto_total
            FROM eventos e
            JOIN clientes c ON e.id_cliente = c.id_cliente
            WHERE e.id_evento = %s AND c.user_id = %s
        """, (data.get('id_evento'), session.get('user_id')))
        
        resultado = cursor.fetchone()
        
        if not resultado:
            return jsonify({'success': False, 'message': 'Evento no encontrado'}), 404
        
        # Crear registro de pago
        cursor.execute("""
            INSERT INTO pagos (id_evento, monto, metodo)
            VALUES (%s, %s, %s)
            RETURNING id_pago
        """, (
            data.get('id_evento'),
            data.get('monto'),
            data.get('metodo', 'efectivo')
        ))
        
        pago_id = cursor.fetchone()[0]
        
        # Actualizar estado del evento
        cursor.execute("""
            UPDATE eventos 
            SET estado = 'confirmado' 
            WHERE id_evento = %s
        """, (data.get('id_evento'),))
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Pago procesado exitosamente',
            'pago_id': pago_id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Error procesando pago: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error procesando pago'
        }), 500

@app.route('/api/generar_pdf/<int:evento_id>')
def generar_pdf_evento(evento_id):
    if 'user' not in session or not session.get('is_client'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from io import BytesIO
        import os
        
        cursor = db.session.connection().connection.cursor()
        
        # Obtener datos del evento
        cursor.execute("""
            SELECT e.*, c.nombre, c.telefono, u.email
            FROM eventos e
            JOIN clientes c ON e.id_cliente = c.id_cliente
            JOIN users u ON c.user_id = u.id
            WHERE e.id_evento = %s AND c.user_id = %s
        """, (evento_id, session.get('user_id')))
        
        columns = [desc[0] for desc in cursor.description]
        evento_row = cursor.fetchone()
        
        if not evento_row:
            return jsonify({'success': False, 'message': 'Evento no encontrado'}), 404
        
        evento_data = dict(zip(columns, evento_row))
        evento_data = serialize_database_row(evento_data)
        
        # Obtener detalles del evento
        cursor.execute("""
            SELECT de.*, a.nombre_articulo, a.tipo
            FROM detalle_evento de
            JOIN articulos a ON de.id_articulo = a.id_articulo
            WHERE de.id_evento = %s
        """, (evento_id,))
        
        detalle_columns = [desc[0] for desc in cursor.description]
        detalles = []
        for row in cursor.fetchall():
            detalle = dict(zip(detalle_columns, row))
            detalle = serialize_database_row(detalle)
            detalles.append(detalle)
        
        # Generar PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1*inch)
        styles = getSampleStyleSheet()
        story = []
        
        # Título
        title = Paragraph("Comprobante de Evento - La Calzada", styles['Title'])
        story.append(title)
        story.append(Spacer(1, 20))
        
        # Información del evento
        evento_info = [
            ['ID Evento:', str(evento_data['id_evento'])],
            ['Cliente:', evento_data['nombre']],
            ['Teléfono:', evento_data['telefono']],
            ['Email:', evento_data['email']],
            ['Fecha:', str(evento_data['fecha_evento'])],
            ['Hora:', f"{evento_data['hora_inicio']} - {evento_data['hora_fin']}"],
            ['Estado:', evento_data['estado'].upper()],
        ]
        
        evento_table = Table(evento_info, colWidths=[2*inch, 4*inch])
        evento_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ]))
        story.append(evento_table)
        story.append(Spacer(1, 20))
        
        # Detalles de servicios/artículos
        if detalles:
            story.append(Paragraph("Servicios y Artículos", styles['Heading2']))
            
            detalle_data = [['Artículo/Servicio', 'Cantidad', 'Precio Unit.', 'Subtotal']]
            for detalle in detalles:
                subtotal = float(detalle['cantidad']) * float(detalle['precio_unitario'])
                detalle_data.append([
                    detalle['nombre_articulo'],
                    str(detalle['cantidad']),
                    f"Q{float(detalle['precio_unitario']):.2f}",
                    f"Q{subtotal:.2f}"
                ])
            
            detalle_table = Table(detalle_data, colWidths=[3*inch, 1*inch, 1.5*inch, 1.5*inch])
            detalle_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ]))
            story.append(detalle_table)
            story.append(Spacer(1, 20))
        
        # Total
        total_data = [['TOTAL:', f"Q{float(evento_data['monto_total']):.2f}"]]
        total_table = Table(total_data, colWidths=[5*inch, 2*inch])
        total_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 14),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 2, colors.black),
            ('BACKGROUND', (0, 0), (-1, -1), colors.lightblue),
        ]))
        story.append(total_table)
        
        # Pie de página
        story.append(Spacer(1, 30))
        footer = Paragraph(f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", styles['Normal'])
        story.append(footer)
        
        # Construir PDF
        doc.build(story)
        
        # Preparar respuesta
        buffer.seek(0)
        pdf_data = buffer.getvalue()
        buffer.close()
        
        # Crear respuesta con el PDF
        from flask import make_response
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=evento_{evento_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        
        return response
        
    except ImportError:
        return jsonify({
            'success': False,
            'message': 'Error: Instala reportlab con: pip install reportlab'
        }), 500
        
    except Exception as e:
        print(f"Error generando PDF: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error generando PDF: {str(e)}'
        }), 500

# ===============================================
# RUTAS PARA ADMINISTRACIÓN
# ===============================================

@app.route('/api/users')
def get_users():
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        cursor = db.session.connection().connection.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.email, u.full_name, u.is_admin, u.is_active, u.created_at,
                   c.nombre as cliente_nombre, a.nombre as admin_nombre
            FROM users u
            LEFT JOIN clientes c ON u.id = c.user_id
            LEFT JOIN administradores a ON u.id = a.user_id
            ORDER BY u.created_at DESC
        """)
        
        columns = [desc[0] for desc in cursor.description]
        users_list = []
        
        for row in cursor.fetchall():
            user_data = dict(zip(columns, row))
            users_list.append(user_data)
        
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

@app.route('/api/populate_sample_data')
def populate_sample_data():
    """Los datos de ejemplo ya están en la base de datos"""
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    return jsonify({
        'success': True,
        'message': 'Los datos de ejemplo ya están cargados en la base de datos'
    })

@app.route('/admin_dashboard')
def admin_dashboard():
    if 'user' not in session or not session.get('is_admin'):
        return render_template('login.html')
    
    return render_template('admin_dashboard.html')

# ESTADÍSTICAS GENERALES PARA ADMIN
@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        cursor = db.session.connection().connection.cursor()
        
        # Total clientes
        cursor.execute("SELECT COUNT(*) FROM clientes")
        total_clientes = cursor.fetchone()[0]
        
        # Total eventos
        cursor.execute("SELECT COUNT(*) FROM eventos")
        total_eventos = cursor.fetchone()[0]
        
        # Eventos por estado
        cursor.execute("""
            SELECT estado, COUNT(*) 
            FROM eventos 
            GROUP BY estado
        """)
        eventos_por_estado = dict(cursor.fetchall())
        
        # Eventos del mes actual
        cursor.execute("""
            SELECT COUNT(*) FROM eventos 
            WHERE EXTRACT(MONTH FROM fecha_evento) = EXTRACT(MONTH FROM CURRENT_DATE)
            AND EXTRACT(YEAR FROM fecha_evento) = EXTRACT(YEAR FROM CURRENT_DATE)
        """)
        eventos_mes = cursor.fetchone()[0]
        
        # Total ingresos
        cursor.execute("SELECT SUM(monto_total) FROM eventos WHERE estado IN ('confirmado', 'completado')")
        total_ingresos = cursor.fetchone()[0] or 0
        
        # Artículos con stock bajo
        cursor.execute("SELECT COUNT(*) FROM articulos WHERE cantidad_total < 10")
        articulos_stock_bajo = cursor.fetchone()[0]
        
        return jsonify({
            'success': True,
            'stats': {
                'total_clientes': total_clientes,
                'total_eventos': total_eventos,
                'eventos_mes': eventos_mes,
                'total_ingresos': float(total_ingresos),
                'eventos_por_estado': eventos_por_estado,
                'articulos_stock_bajo': articulos_stock_bajo
            }
        })
        
    except Exception as e:
        print(f"Error obteniendo estadísticas admin: {str(e)}")
        return jsonify({'success': False, 'message': 'Error en el servidor'}), 500

# OBTENER TODOS LOS EVENTOS PARA ADMIN
@app.route('/api/admin/eventos', methods=['GET'])
def get_admin_eventos():
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 401
    
    try:
        cursor = db.session.connection().connection.cursor()
        # Corregido: JOIN con users para obtener el email
        cursor.execute("""
            SELECT e.*, c.nombre as cliente_nombre, c.telefono, u.email
            FROM eventos e
            JOIN clientes c ON e.id_cliente = c.id_cliente
            JOIN users u ON c.user_id = u.id
            ORDER BY e.fecha_evento DESC
        """)
        
        columns = [desc[0] for desc in cursor.description]
        eventos = []
        
        for row in cursor.fetchall():
            evento = dict(zip(columns, row))
            evento = serialize_database_row(evento)
            
            # Obtener detalles del evento
            cursor.execute("""
                SELECT de.*, a.nombre_articulo, a.tipo
                FROM detalle_evento de
                JOIN articulos a ON de.id_articulo = a.id_articulo
                WHERE de.id_evento = %s
            """, (evento['id_evento'],))
            
            detalle_columns = [desc[0] for desc in cursor.description]
            detalles = []
            
            for detalle_row in cursor.fetchall():
                detalle = dict(zip(detalle_columns, detalle_row))
                detalle = serialize_database_row(detalle)
                detalles.append(detalle)
            
            evento['detalles'] = detalles
            eventos.append(evento)
        
        return jsonify({
            'success': True,
            'eventos': eventos
        })
        
    except Exception as e:
        print(f"Error obteniendo eventos admin: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error obteniendo eventos'
        }), 500

# MARCAR EVENTO COMO EMBODEGADO
@app.route('/api/admin/eventos/<int:evento_id>/embodeagar', methods=['POST'])
def marcar_embodegado(evento_id):
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        cursor = db.session.connection().connection.cursor()
        
        # Obtener detalles del evento
        cursor.execute("""
            SELECT de.id_articulo, de.cantidad
            FROM detalle_evento de
            WHERE de.id_evento = %s
        """, (evento_id,))
        
        detalles = cursor.fetchall()
        
        # Restituir stock de artículos
        for id_articulo, cantidad in detalles:
            cursor.execute("""
                UPDATE articulos 
                SET cantidad_total = cantidad_total + %s
                WHERE id_articulo = %s
            """, (cantidad, id_articulo))
        
        # Actualizar estado del evento
        cursor.execute("""
            UPDATE eventos 
            SET estado = 'completado'
            WHERE id_evento = %s
        """, (evento_id,))
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Evento marcado como embodegado y stock restituido'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error marcando embodegado: {str(e)}")
        return jsonify({'success': False, 'message': 'Error procesando solicitud'}), 500

# OBTENER FECHAS OCUPADAS PARA CALENDARIO
@app.route('/api/admin/fechas-ocupadas', methods=['GET'])
def get_fechas_ocupadas():
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        cursor = db.session.connection().connection.cursor()
        cursor.execute("""
            SELECT fecha_evento, COUNT(*) as eventos_dia
            FROM eventos 
            WHERE estado IN ('reservado', 'confirmado')
            GROUP BY fecha_evento
        """)
        
        fechas_ocupadas = []
        for fecha, count in cursor.fetchall():
            fechas_ocupadas.append({
                'fecha': str(fecha),
                'eventos': count
            })
        
        return jsonify({
            'success': True,
            'fechas': fechas_ocupadas
        })
        
    except Exception as e:
        print(f"Error obteniendo fechas ocupadas: {str(e)}")
        return jsonify({'success': False, 'message': 'Error obteniendo fechas'}), 500

# BLOQUEAR/DESBLOQUEAR FECHA
@app.route('/api/admin/bloquear-fecha', methods=['POST'])
def bloquear_fecha():
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        data = request.get_json()
        fecha = data.get('fecha')
        bloquear = data.get('bloquear', True)
        
        # Aquí podrías crear una tabla de fechas bloqueadas
        # Por simplicidad, usaremos un evento especial con cliente_id NULL
        cursor = db.session.connection().connection.cursor()
        
        if bloquear:
            # Crear evento de bloqueo
            cursor.execute("""
                INSERT INTO eventos (id_cliente, fecha_evento, estado, monto_total)
                VALUES (NULL, %s, 'bloqueado', 0)
            """, (fecha,))
        else:
            # Eliminar eventos de bloqueo
            cursor.execute("""
                DELETE FROM eventos 
                WHERE fecha_evento = %s AND estado = 'bloqueado' AND id_cliente IS NULL
            """, (fecha,))
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Fecha {"bloqueada" if bloquear else "desbloqueada"} exitosamente'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error bloqueando fecha: {str(e)}")
        return jsonify({'success': False, 'message': 'Error procesando solicitud'}), 500

# GESTIÓN DE STOCK
@app.route('/api/admin/stock', methods=['GET'])
def get_stock_admin():
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        cursor = db.session.connection().connection.cursor()
        cursor.execute("""
            SELECT id_articulo, nombre_articulo, tipo, cantidad_total, precio_unitario,
                   CASE 
                       WHEN cantidad_total < 10 THEN 'bajo'
                       WHEN cantidad_total < 50 THEN 'medio'
                       ELSE 'alto'
                   END as nivel_stock
            FROM articulos
            ORDER BY cantidad_total ASC
        """)
        
        columns = [desc[0] for desc in cursor.description]
        articulos = []
        
        for row in cursor.fetchall():
            articulo = dict(zip(columns, row))
            articulo = serialize_database_row(articulo)
            articulos.append(articulo)
        
        return jsonify({
            'success': True,
            'articulos': articulos
        })
        
    except Exception as e:
        print(f"Error obteniendo stock: {str(e)}")
        return jsonify({'success': False, 'message': 'Error obteniendo stock'}), 500

# ACTUALIZAR STOCK MANUALMENTE
@app.route('/api/admin/stock/<int:articulo_id>', methods=['PUT'])
def actualizar_stock(articulo_id):
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        data = request.get_json()
        nueva_cantidad = data.get('cantidad')
        
        cursor = db.session.connection().connection.cursor()
        cursor.execute("""
            UPDATE articulos 
            SET cantidad_total = %s
            WHERE id_articulo = %s
        """, (nueva_cantidad, articulo_id))
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Stock actualizado exitosamente'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error actualizando stock: {str(e)}")
        return jsonify({'success': False, 'message': 'Error actualizando stock'}), 500

# GESTIÓN DE CLIENTES PARA ADMIN
@app.route('/api/admin/clientes', methods=['GET'])
def get_admin_clientes():
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        cursor = db.session.connection().connection.cursor()
        cursor.execute("""
            SELECT c.*, u.username, u.email, u.created_at as fecha_registro,
                   COUNT(e.id_evento) as total_eventos,
                   COALESCE(SUM(e.monto_total), 0) as total_gastado
            FROM clientes c
            JOIN users u ON c.user_id = u.id
            LEFT JOIN eventos e ON c.id_cliente = e.id_cliente
            GROUP BY c.id_cliente, u.id
            ORDER BY u.created_at DESC
        """)
        
        columns = [desc[0] for desc in cursor.description]
        clientes = []
        
        for row in cursor.fetchall():
            cliente = dict(zip(columns, row))
            cliente = serialize_database_row(cliente)
            clientes.append(cliente)
        
        return jsonify({
            'success': True,
            'clientes': clientes
        })
        
    except Exception as e:
        print(f"Error obteniendo clientes admin: {str(e)}")
        return jsonify({'success': False, 'message': 'Error obteniendo clientes'}), 500

# GRÁFICOS Y MÉTRICAS
@app.route('/api/admin/graficos', methods=['GET'])
def get_admin_graficos():
    if 'user' not in session or not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'No autorizado'}), 403
    
    try:
        cursor = db.session.connection().connection.cursor()
        
        # Eventos por mes (últimos 6 meses)
        cursor.execute("""
            SELECT 
                EXTRACT(MONTH FROM fecha_evento) as mes,
                EXTRACT(YEAR FROM fecha_evento) as anio,
                COUNT(*) as total
            FROM eventos 
            WHERE fecha_evento >= CURRENT_DATE - INTERVAL '6 months'
            GROUP BY EXTRACT(YEAR FROM fecha_evento), EXTRACT(MONTH FROM fecha_evento)
            ORDER BY anio, mes
        """)
        eventos_por_mes = [{'mes': int(row[0]), 'anio': int(row[1]), 'total': row[2]} for row in cursor.fetchall()]
        
        # Artículos más usados
        cursor.execute("""
            SELECT a.nombre_articulo, SUM(de.cantidad) as total_usado
            FROM detalle_evento de
            JOIN articulos a ON de.id_articulo = a.id_articulo
            GROUP BY a.id_articulo, a.nombre_articulo
            ORDER BY total_usado DESC
            LIMIT 5
        """)
        articulos_populares = [{'nombre': row[0], 'cantidad': row[1]} for row in cursor.fetchall()]
        
        # Ingresos por mes
        cursor.execute("""
            SELECT 
                EXTRACT(MONTH FROM fecha_evento) as mes,
                EXTRACT(YEAR FROM fecha_evento) as anio,
                SUM(monto_total) as ingresos
            FROM eventos 
            WHERE estado IN ('confirmado', 'completado')
            AND fecha_evento >= CURRENT_DATE - INTERVAL '6 months'
            GROUP BY EXTRACT(YEAR FROM fecha_evento), EXTRACT(MONTH FROM fecha_evento)
            ORDER BY anio, mes
        """)
        ingresos_por_mes = [{'mes': int(row[0]), 'anio': int(row[1]), 'ingresos': float(row[2] or 0)} for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'graficos': {
                'eventos_por_mes': eventos_por_mes,
                'articulos_populares': articulos_populares,
                'ingresos_por_mes': ingresos_por_mes
            }
        })
        
    except Exception as e:
        print(f"Error obteniendo gráficos: {str(e)}")
        return jsonify({'success': False, 'message': 'Error obteniendo gráficos'}), 500

# APARTAR STOCK CUANDO SE CREA EVENTO (Modificar la función create_evento existente)
def apartar_stock_evento(evento_id, servicios_articulos):
    """Apartar stock cuando se crea un evento"""
    try:
        cursor = db.session.connection().connection.cursor()
        
        for item in servicios_articulos:
            if item.get('tipo') == 'articulo':
                # Reducir stock disponible
                cursor.execute("""
                    UPDATE articulos 
                    SET cantidad_total = cantidad_total - %s
                    WHERE id_articulo = %s AND cantidad_total >= %s
                """, (item['cantidad'], item['id_articulo'], item['cantidad']))
                
                # Verificar si se pudo apartar
                if cursor.rowcount == 0:
                    raise Exception(f"Stock insuficiente para {item['nombre']}")
        
        return True
        
    except Exception as e:
        print(f"Error apartando stock: {str(e)}")
        raise e

# ===============================================
# MANEJO DE ERRORES
# ===============================================

@app.errorhandler(Exception)
def handle_db_error(error):
    if hasattr(db.session, 'rollback'):
        db.session.rollback()
    print(f"Error de aplicación: {str(error)}")
    return jsonify({
        'success': False,
        'message': 'Error interno del servidor'
    }), 500

# ===============================================
# INICIALIZACIÓN
# ===============================================

def verify_database_connection():
    """Verificar conexión a base de datos"""
    try:
        cursor = db.session.connection().connection.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print("Conexión a base de datos exitosa")
        return True
    except Exception as e:
        print(f"Error conectando a base de datos: {str(e)}")
        return False

# Inicializar aplicación
try:
    with app.app_context():
        if verify_database_connection():
            print("Base de datos lista para usar")
        else:
            print("Error en conexión a base de datos")
except Exception as e:
    print(f"Error inicializando aplicación: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print("Iniciando aplicación Flask...")
    app.run(host='0.0.0.0', port=port, debug=False)
