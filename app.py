from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, get_flashed_messages, session as flask_session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
from functools import wraps
import os
import logging
import hashlib
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, text, func, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import base64
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from contextlib import contextmanager

# Inisialisasi logging
logging.basicConfig(level=logging.DEBUG)

# Inisialisasi aplikasi
app = Flask(__name__)
app.config['SECRET_KEY'] = 'kunci_rahasia_anda'  # Ganti dengan kunci rahasia yang aman

# Konfigurasi Supabase

# Konfigurasi SQLAlchemy
DATABASE_URL = f"postgresql://postgres.isadrgmnkdggmoqinxiq:arisdevdatabase@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
engine = create_engine(DATABASE_URL)
Base = declarative_base()
Session = sessionmaker(bind=engine)

# Model SQLAlchemy
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)  # Tambahkan ini
    password = Column(String, nullable=False)
    role = Column(String, nullable=False)

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String)
    price = Column(Float, nullable=False)
    qty = Column(Integer, nullable=False)
    image = Column(Text)  # Ubah tipe data menjadi Text
    category_id = Column(Integer, ForeignKey('categories.id'))
    discount = Column(Float, default=0)
    category = relationship("Category", back_populates="products")

class Category(Base):
    __tablename__ = 'categories'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    products = relationship("Product", back_populates="category")

class Visitor(Base):
    __tablename__ = 'visitors'
    id = Column(Integer, primary_key=True)
    ip_address = Column(String, nullable=False)
    user_agent = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Konfigurasi untuk upload gambar
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Fungsi untuk memeriksa ekstensi file yang diizinkan
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Fungsi dekorator admin_required
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in flask_session or flask_session['user_role'] != 'admin':
            flash('Anda harus login sebagai admin untuk mengakses halaman ini.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Rute untuk halaman home
@app.route('/')
def home():
    try:
        record_visit()
    except Exception as e:
        logging.error(f"Gagal merekam kunjungan: {str(e)}")
    return render_template('home.html', user=flask_session.get('user_role'))

# Rute untuk login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in flask_session:
        if flask_session['user_role'] == 'admin':
            return redirect(url_for('admin'))
        else:
            return redirect(url_for('home'))

    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            
            session = Session()
            user = session.query(User).filter_by(username=username).first()
            
            if user and check_password_hash(user.password, password):
                # Simpan informasi login di session Flask
                flask_session['user_id'] = user.id
                flask_session['username'] = username
                flask_session['user_role'] = user.role
                session.close()
                if user.role == 'admin':
                    return redirect(url_for('admin'))
                else:
                    return redirect(url_for('home'))
            else:
                session.close()
                flash('Username atau password salah', 'danger')
        except Exception as e:
            app.logger.error(f"Kesalahan saat login: {str(e)}")
            flash('Terjadi kesalahan saat mencoba login. Silakan coba lagi.', 'danger')
    return render_template('login.html')

# Rute untuk logout
@app.route('/logout')
def logout():
    flask_session.clear()
    flash('Anda telah berhasil logout', 'success')
    return redirect(url_for('home'))

# Fungsi untuk merekam kunjungan
def record_visit():
    try:
        ip_address = request.remote_addr
        user_agent = request.user_agent.string
        new_visitor = Visitor(ip_address=ip_address, user_agent=user_agent)
        session = Session()
        session.add(new_visitor)
        session.commit()
        session.close()
    except Exception as e:
        logging.error(f"Terjadi kesalahan saat merekam kunjungan: {str(e)}")

# Rute untuk menambahkan produk baru
@app.route('/product', methods=['POST'])
@admin_required
def add_product():
    try:
        logging.debug(f"Form data: {request.form}")
        logging.debug(f"Files: {request.files}")
        
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price')
        qty = request.form.get('qty')
        category_id = request.form.get('category_id')
        discount = request.form.get('discount', 0)
        
        logging.debug(f"Extracted data: name={name}, description={description}, price={price}, qty={qty}, category_id={category_id}, discount={discount}")
        
        if not all([name, description, price, qty, category_id]):
            missing_fields = [field for field in ['name', 'description', 'price', 'qty', 'category_id'] if not request.form.get(field)]
            return jsonify({"error": f"Field berikut harus diisi: {', '.join(missing_fields)}"}), 400
        
        try:
            price = float(price)
            qty = int(qty)
            category_id = int(category_id)
            discount = float(discount)
        except ValueError as e:
            return jsonify({"error": f"Error konversi tipe data: {str(e)}"}), 400
        
        file = request.files.get('image')
        image_data = None
        if file and allowed_file(file.filename):
            try:
                # Baca file gambar sebagai bytes
                image_bytes = file.read()
                # Encode bytes menjadi base64
                image_data = base64.b64encode(image_bytes).decode('utf-8')
            except Exception as e:
                return jsonify({"error": f"Gagal memproses file: {str(e)}"}), 500

        new_product = Product(
            name=name,
            description=description,
            price=price,
            qty=qty,
            image=image_data,  # Simpan data gambar base64
            category_id=category_id,
            discount=discount
        )
        
        session = Session()
        session.add(new_product)
        session.commit()
        result = {
            'id': new_product.id,
            'name': new_product.name,
            'description': new_product.description,
            'price': new_product.price,
            'qty': new_product.qty,
            'image': new_product.image,
            'category_id': new_product.category_id,
            'discount': new_product.discount
        }
        session.close()
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error dalam add_product: {str(e)}")
        if session:
            session.rollback()
            session.close()
        return jsonify({"error": "Terjadi kesalahan saat menambahkan produk"}), 500

# Rute untuk mendapatkan semua produk
@app.route('/product', methods=['GET'])
def get_products():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')
    per_page = 10  # Jumlah produk per halaman

    session = Session()
    query = session.query(Product)
    
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%') | Product.description.ilike(f'%{search}%'))
    
    if category:
        query = query.filter(Product.category_id == category)
    
    if min_price:
        query = query.filter(Product.price >= float(min_price))
    
    if max_price:
        query = query.filter(Product.price <= float(max_price))
    
    total_count = query.count()
    total_pages = (total_count + per_page - 1) // per_page
    
    products = query.offset((page-1)*per_page).limit(per_page).all()

    result = [{
        'id': p.id,
        'name': p.name,
        'description': p.description,
        'price': p.price,
        'qty': p.qty,
        'category_name': p.category.name if p.category else 'Tidak ada kategori',
        'image': f"data:image/jpeg;base64,{p.image}" if p.image else None
    } for p in products]

    session.close()
    return jsonify({
        'products': result,
        'total_pages': total_pages,
        'current_page': page
    })

# Tambahkan rute untuk registrasi
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Periksa apakah username atau email sudah ada
        session = Session()
        existing_user = session.query(User).filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            session.close()
            flash('Username atau email sudah digunakan', 'danger')
            return redirect(url_for('register'))
        
        # Buat user baru
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, email=email, password=hashed_password, role='user')
        session.add(new_user)
        session.commit()
        session.close()
        
        flash('Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

def create_default_admin():
    session = Session()
    try:
        # Baca isi file SQL
        with open('create_admin.sql', 'r') as file:
            sql_script = file.read()
        
        # Ganti placeholder password dengan hash yang sebenarnya
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        hashed_password = generate_password_hash(admin_password)
        sql_script = sql_script.replace('hashed_password_placeholder', hashed_password)
        
        # Eksekusi script SQL
        session.execute(text(sql_script))
        session.commit()
        print("Script create_admin.sql telah dieksekusi.")
    except Exception as e:
        print(f"Terjadi kesalahan saat membuat admin: {str(e)}")
    finally:
        session.close()

# Inisialisasi database
Base.metadata.create_all(engine)

# Menjalankan server
if __name__ == '__main__':
    create_default_admin()  # Panggil fungsi ini sebelum menjalankan server
    app.run(debug=True)

# Tambahkan rute untuk halaman admin
@app.route('/admin')
@admin_required
def admin():
    if 'user_id' not in flask_session or flask_session['user_role'] != 'admin':
        flash('Anda harus login sebagai admin untuk mengakses halaman ini.', 'danger')
        return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/admin/change-password', methods=['GET', 'POST'])
@admin_required
def change_admin_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # Periksa apakah password saat ini benar
        session = Session()
        admin = session.query(User).filter_by(username=flask_session['username']).first()
        
        if not check_password_hash(admin.password, current_password):
            flash('Password saat ini salah', 'danger')
            return redirect(url_for('change_admin_password'))
        
        if new_password != confirm_password:
            flash('Password baru dan konfirmasi password tidak cocok', 'danger')
            return redirect(url_for('change_admin_password'))
        
        # Update password
        admin.password = generate_password_hash(new_password)
        session.commit()
        session.close()
        
        flash('Password berhasil diubah', 'success')
        return redirect(url_for('admin'))
    
    return render_template('change_admin_password.html')

# Tambahkan rute untuk statistik pengunjung
@app.route('/visitor_stats', methods=['GET'])
@admin_required
def visitor_stats():
    session = Session()
    total_visits = session.query(func.count(Visitor.id)).scalar()
    unique_visitors = session.query(func.count(func.distinct(Visitor.ip_address))).scalar()
    recent_visits = session.query(Visitor).order_by(Visitor.timestamp.desc()).limit(10).all()
    
    result = {
        'total_visits': total_visits,
        'unique_visitors': unique_visitors,
        'recent_visits': [
            {
                'ip_address': v.ip_address,
                'user_agent': v.user_agent,
                'timestamp': v.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            } for v in recent_visits
        ]
    }
    session.close()
    return jsonify(result)

# Fungsi untuk mendapatkan produk berdasarkan ID
@app.route('/product/<int:product_id>', methods=['GET'])
def get_product(product_id):
    session = Session()
    product = session.query(Product).get(product_id)
    if product:
        result = {
            'id': product.id,
            'name': product.name,
            'description': product.description,
            'price': product.price,
            'qty': product.qty,
            'category_id': product.category_id,
            'discount': product.discount,
            'image': f"data:image/jpeg;base64,{product.image}" if product.image else None
        }
        session.close()
        return jsonify(result)
    session.close()
    return jsonify({"error": "Produk tidak ditemukan"}), 404

# Fungsi untuk memperbarui produk
@app.route('/product/<int:product_id>', methods=['PUT'])
@admin_required
def update_product(product_id):
    try:
        session = Session()
        product = session.query(Product).get(product_id)
        if not product:
            session.close()
            return jsonify({"error": "Produk tidak ditemukan"}), 404

        data = request.form
        product.name = data.get('name', product.name)
        product.description = data.get('description', product.description)
        product.price = float(data.get('price', product.price))
        product.qty = int(data.get('qty', product.qty))
        product.category_id = int(data.get('category_id', product.category_id))
        product.discount = float(data.get('discount', product.discount))

        file = request.files.get('image')
        if file and allowed_file(file.filename):
            image_bytes = file.read()
            product.image = base64.b64encode(image_bytes).decode('utf-8')

        session.commit()
        result = {
            'id': product.id,
            'name': product.name,
            'description': product.description,
            'price': product.price,
            'qty': product.qty,
            'category_id': product.category_id,
            'discount': product.discount,
            'image': f"data:image/jpeg;base64,{product.image}" if product.image else None
        }
        session.close()
        return jsonify(result)
    except Exception as e:
        session.rollback()
        session.close()
        return jsonify({"error": f"Terjadi kesalahan saat memperbarui produk: {str(e)}"}), 500

# Fungsi untuk menghapus produk
@app.route('/product/<int:product_id>', methods=['DELETE'])
@admin_required
def delete_product(product_id):
    try:
        session = Session()
        product = session.query(Product).get(product_id)
        if not product:
            session.close()
            return jsonify({"error": "Produk tidak ditemukan"}), 404

        session.delete(product)
        session.commit()
        session.close()
        return jsonify({"message": "Produk berhasil dihapus"})
    except Exception as e:
        session.rollback()
        session.close()
        return jsonify({"error": f"Terjadi kesalahan saat menghapus produk: {str(e)}"}), 500

# Rute untuk mendapatkan daftar pengguna
@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    session = Session()
    users = session.query(User).all()
    result = [{
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'is_active': True  # Asumsikan semua pengguna aktif, sesuaikan jika ada field is_active
    } for user in users]
    session.close()
    return jsonify(result)

# Rute untuk menambah pengguna baru
@app.route('/api/users', methods=['POST'])
@admin_required
def add_user():
    data = request.json
    session = Session()
    new_user = User(
        username=data['username'],
        email=data['email'],
        password=generate_password_hash(data['password']),
        role=data['role']
    )
    session.add(new_user)
    session.commit()
    session.close()
    return jsonify({'message': 'Pengguna berhasil ditambahkan'}), 201

# Rute untuk mengubah status aktif/nonaktif pengguna
@app.route('/api/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def toggle_user_status(user_id):
    session = Session()
    user = session.query(User).get(user_id)
    if user:
        user.is_active = not user.is_active
        session.commit()
        session.close()
        return jsonify({'message': 'Status pengguna berhasil diubah'})
    session.close()
    return jsonify({'error': 'Pengguna tidak ditemukan'}), 404

# Rute untuk mendapatkan daftar kategori
@app.route('/api/categories', methods=['GET'])
def get_categories():
    session = Session()
    try:
        categories = session.query(Category).all()
        result = [{
            'id': category.id,
            'name': category.name,
            'product_count': session.query(Product).filter_by(category_id=category.id).count()
        } for category in categories]
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

# Rute untuk menambah kategori baru
@app.route('/api/categories/add', methods=['POST'])
@admin_required
def add_category():
    data = request.json
    session = Session()
    try:
        new_category = Category(name=data['name'])
        session.add(new_category)
        session.commit()
        return jsonify({'message': 'Kategori berhasil ditambahkan'}), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@app.route('/api/categories/<int:category_id>', methods=['DELETE'])
@admin_required
def delete_category(category_id):
    session = Session()
    try:
        category = session.query(Category).get(category_id)
        if category:
            session.delete(category)
            session.commit()
            return jsonify({'message': 'Kategori berhasil dihapus'})
        return jsonify({'error': 'Kategori tidak ditemukan'}), 404
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

# Rute untuk mendapatkan laporan stok
@app.route('/api/stock-report', methods=['GET'])
@admin_required
def get_stock_report():
    session = Session()
    products = session.query(Product).all()
    result = [{
        'product_id': product.id,
        'product_name': product.name,
        'category': product.category.name if product.category else 'Tidak ada kategori',
        'stock': product.qty
    } for product in products]
    session.close()
    return jsonify(result)

# Rute untuk menghasilkan laporan stok PDF
@app.route('/api/generate-stock-report', methods=['GET'])
@admin_required
def generate_stock_report():
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    session = Session()
    products = session.query(Product).all()
    data = [['ID', 'Nama Produk', 'Kategori', 'Stok']]
    for product in products:
        data.append([
            product.id,
            product.name,
            product.category.name if product.category else 'Tidak ada kategori',
            product.qty
        ])
    session.close()

    table = Table(data)
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ])
    table.setStyle(style)
    elements.append(table)

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        attachment_filename='laporan_stok.pdf'
    )

