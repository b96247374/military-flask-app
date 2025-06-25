from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from datetime import datetime
from functools import wraps
import os
import time
from models import db, User, Report, SystemSettings, ReportTemplate

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'reports.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.before_first_request
def create_tables():
    db.create_all()
    # إنشاء مستخدم افتراضي admin/1234 إذا لم يكن موجودًا
    if not User.query.filter_by(username='admin').first():
        default_user = User(username='admin', password='1234', role='admin')
        db.session.add(default_user)
        db.session.commit()

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود مسبقاً', 'danger')
            return redirect(url_for('register'))
        new_user = User(username=username, password=password, role='user')
        db.session.add(new_user)
        db.session.commit()
        flash('تم إنشاء الحساب بنجاح', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('بيانات الدخول غير صحيحة', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/reports')
@login_required
def view_reports():
    if not has_permission(current_user, 'view_reports'):
        flash('غير مصرح لك بعرض هذه الصفحة', 'danger')
        return redirect(url_for('dashboard'))
    reports = Report.query.filter_by(author_id=current_user.id).order_by(Report.date.desc()).all()
    return render_template('view_reports.html', reports=reports)

@app.route('/reports/create', methods=['GET', 'POST'])
@login_required
def create_report():
    if not has_permission(current_user, 'create_report'):
        flash('غير مصرح لك بإنشاء تقرير', 'danger')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        title = request.form['title']
        accepted_violations = int(request.form['accepted_violations'])
        rejected_violations = int(request.form['rejected_violations'])
        total_violations = accepted_violations + rejected_violations
        image_path = None
        if 'image' in request.files and request.files['image'].filename != '':
            image = request.files['image']
            upload_folder = os.path.join(basedir, 'static', 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filename = f"{int(time.time())}_{image.filename}"
            filepath = os.path.join(upload_folder, filename)
            image.save(filepath)
            image_path = f"uploads/{filename}"
        # حفظ التوقيع الإلكتروني
        signature_path = None
        signature_data = request.form.get('signature')
        if signature_data and signature_data.startswith('data:image'):
            import base64
            signature_folder = os.path.join(basedir, 'static', 'uploads', 'signatures')
            os.makedirs(signature_folder, exist_ok=True)
            sig_filename = f"signature_{int(time.time())}_{current_user.id}.png"
            sig_filepath = os.path.join(signature_folder, sig_filename)
            with open(sig_filepath, 'wb') as f:
                f.write(base64.b64decode(signature_data.split(',')[1]))
            signature_path = f"uploads/signatures/{sig_filename}"
        new_report = Report(
            title=title,
            content='',
            date=datetime.utcnow(),
            author=current_user,
            accepted_violations=accepted_violations,
            rejected_violations=rejected_violations,
            total_violations=total_violations,
            image_path=image_path,
            signature_path=signature_path
        )
        db.session.add(new_report)
        db.session.commit()
        flash('تم حفظ التقرير بنجاح', 'success')
        return redirect(url_for('view_reports'))
    current_date = datetime.utcnow().strftime('%Y-%m-%d')
    current_time = datetime.utcnow().strftime('%H:%M')
    return render_template('create_report.html', current_date=current_date, current_time=current_time)

@app.route('/reports/edit/<int:report_id>', methods=['GET', 'POST'])
@login_required
def edit_report(report_id):
    report = Report.query.get_or_404(report_id)
    if report.author != current_user:
        flash('غير مصرح', 'danger')
        return redirect(url_for('view_reports'))
    if request.method == 'POST':
        report.title = request.form['title']
        report.content = request.form['content']
        report.date = datetime.strptime(request.form['date'], '%Y-%m-%d')
        db.session.commit()
        flash('تم تعديل التقرير', 'success')
        return redirect(url_for('view_reports'))
    return render_template('edit_report.html', report=report)

@app.route('/reports/delete/<int:report_id>')
@login_required
def delete_report(report_id):
    report = Report.query.get_or_404(report_id)
    if report.author == current_user:
        db.session.delete(report)
        db.session.commit()
        flash('تم حذف التقرير', 'success')
    return redirect(url_for('view_reports'))

@app.route('/reports/print/<int:report_id>')
@login_required
def print_report(report_id):
    report = Report.query.get_or_404(report_id)
    if report.author != current_user and current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('view_reports'))
    return render_template('print_report.html', report=report)

@app.route('/reports/view/<int:report_id>', methods=['GET', 'POST'])
@login_required
def view_report(report_id):
    report = Report.query.get_or_404(report_id)
    settings = SystemSettings.query.first()
    is_commander = (current_user.username == settings.commander_name)
    if report.author != current_user and not is_commander:
        flash('غير مصرح', 'danger')
        return redirect(url_for('view_reports'))
    # معالجة قبول/رفض التقرير أو التوقيع
    if request.method == 'POST' and is_commander:
        if 'accept' in request.form:
            report.status = 'مقبول'
            db.session.commit()
            flash('تم قبول التقرير', 'success')
        elif 'reject' in request.form:
            report.status = 'مرفوض'
            db.session.commit()
            flash('تم رفض التقرير', 'danger')
        elif 'signature' in request.form:
            import base64, time, os
            signature_data = request.form.get('signature')
            if signature_data and signature_data.startswith('data:image'):
                signature_folder = os.path.join(basedir, 'static', 'uploads', 'signatures')
                os.makedirs(signature_folder, exist_ok=True)
                sig_filename = f"signature_{int(time.time())}_{current_user.id}_{report.id}.png"
                sig_filepath = os.path.join(signature_folder, sig_filename)
                with open(sig_filepath, 'wb') as f:
                    f.write(base64.b64decode(signature_data.split(',')[1]))
                report.signature_path = f"uploads/signatures/{sig_filename}"
                db.session.commit()
                flash('تم توقيع التقرير إلكترونيًا', 'success')
        return redirect(url_for('view_report', report_id=report.id))
    return render_template('view_report.html', report=report, is_commander=is_commander, settings=settings)

def requires_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('غير مصرح لك بالدخول لهذه الصفحة', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/users')
@login_required
@requires_admin
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
@requires_admin
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.username = request.form['username']
        user.role = request.form['role']
        permissions = request.form.getlist('permissions')
        user.permissions = ','.join(permissions)
        db.session.commit()
        flash('تم تعديل بيانات المستخدم', 'success')
        return redirect(url_for('manage_users'))
    return render_template('edit_user.html', user=user)

@app.route('/users/delete/<int:user_id>')
@login_required
@requires_admin
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        flash('لا يمكن حذف المستخدم الرئيسي', 'danger')
        return redirect(url_for('manage_users'))
    db.session.delete(user)
    db.session.commit()
    flash('تم حذف المستخدم', 'success')
    return redirect(url_for('manage_users'))

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
@requires_admin
def add_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        permissions = request.form.getlist('permissions')
        # صلاحيات افتراضية للمستخدم العادي إذا لم يتم تحديدها
        if role != 'admin' and not permissions:
            permissions = ['view_reports', 'create_report']
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود مسبقاً', 'danger')
            return redirect(url_for('add_user'))
        new_user = User(username=username, password=password, role=role, permissions=','.join(permissions))
        db.session.add(new_user)
        db.session.commit()
        flash('تم إضافة المستخدم بنجاح', 'success')
        return redirect(url_for('manage_users'))
    return render_template('add_user.html')

@app.route('/settings', methods=['GET', 'POST'])
@login_required
@requires_admin
def system_settings():
    settings = SystemSettings.query.first()
    if not settings:
        settings = SystemSettings()
        db.session.add(settings)
        db.session.commit()
    if request.method == 'POST':
        header_text = request.form.get('header_text', settings.header_text)
        commander_name = request.form.get('commander_name', settings.commander_name)
        paper_size = request.form.get('paper_size', settings.paper_size)
        margin_top = request.form.get('margin_top', settings.margin_top)
        margin_bottom = request.form.get('margin_bottom', settings.margin_bottom)
        margin_right = request.form.get('margin_right', settings.margin_right)
        margin_left = request.form.get('margin_left', settings.margin_left)
        font_family = request.form.get('font_family', settings.font_family)
        font_size = request.form.get('font_size', settings.font_size)
        show_logo = bool(request.form.get('show_logo'))
        show_header = bool(request.form.get('show_header'))
        show_signature = bool(request.form.get('show_signature'))
        show_image = bool(request.form.get('show_image'))
        footer_text = request.form.get('footer_text', settings.footer_text)
        logo_path = settings.logo_path
        if 'logo' in request.files and request.files['logo'].filename != '':
            logo = request.files['logo']
            upload_folder = os.path.join(basedir, 'static')
            filename = 'logo.png'
            logo.save(os.path.join(upload_folder, filename))
            logo_path = filename
        settings.header_text = header_text
        settings.logo_path = logo_path
        settings.commander_name = commander_name
        settings.paper_size = paper_size
        settings.margin_top = margin_top
        settings.margin_bottom = margin_bottom
        settings.margin_right = margin_right
        settings.margin_left = margin_left
        settings.font_family = font_family
        settings.font_size = font_size
        settings.show_logo = show_logo
        settings.show_header = show_header
        settings.show_signature = show_signature
        settings.show_image = show_image
        settings.footer_text = footer_text
        db.session.commit()
        flash('تم تحديث إعدادات النظام بنجاح', 'success')
        return redirect(url_for('system_settings'))
    return render_template('system_settings.html', settings=settings)

@app.route('/templates')
@login_required
@requires_admin
def manage_templates():
    templates = ReportTemplate.query.order_by(ReportTemplate.created_at.desc()).all()
    return render_template('manage_templates.html', templates=templates)

@app.route('/templates/add', methods=['GET', 'POST'])
@login_required
@requires_admin
def add_template():
    if request.method == 'POST':
        name = request.form['name']
        content = request.form['content']
        if ReportTemplate.query.filter_by(name=name).first():
            flash('اسم القالب موجود مسبقاً', 'danger')
            return redirect(url_for('add_template'))
        template = ReportTemplate(name=name, content=content)
        db.session.add(template)
        db.session.commit()
        flash('تم إضافة القالب بنجاح', 'success')
        return redirect(url_for('manage_templates'))
    return render_template('add_template.html')

@app.route('/templates/import', methods=['GET', 'POST'])
@login_required
@requires_admin
def import_template():
    if request.method == 'POST':
        try:
            name = request.form['name']
            file = request.files['file']
            if not file or file.filename == '':
                flash('يرجى اختيار ملف قالب', 'danger')
                return redirect(url_for('import_template'))
            content = file.read().decode('utf-8')
            if ReportTemplate.query.filter_by(name=name).first():
                flash('اسم القالب موجود مسبقاً', 'danger')
                return redirect(url_for('import_template'))
            template = ReportTemplate(name=name, content=content)
            db.session.add(template)
            db.session.commit()
            flash('تم استيراد القالب بنجاح', 'success')
            return redirect(url_for('manage_templates'))
        except Exception as e:
            flash(f'حدث خطأ أثناء الاستيراد: {e}', 'danger')
            return redirect(url_for('import_template'))
    return render_template('import_template.html')

@app.route('/templates/delete/<int:template_id>')
@login_required
@requires_admin
def delete_template(template_id):
    template = ReportTemplate.query.get_or_404(template_id)
    db.session.delete(template)
    db.session.commit()
    flash('تم حذف القالب', 'success')
    return redirect(url_for('manage_templates'))

@app.route('/digital-editor', methods=['GET', 'POST'])
@login_required
def digital_document_editor():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        # يمكن هنا مستقبلاً حفظ المستند في قاعدة البيانات أو تحميله كملف
        return render_template('digital_document_editor.html', title=title, content=content, saved=True)
    return render_template('digital_document_editor.html', saved=False)

def has_permission(user, perm):
    if user.role == 'admin':
        # admin always has all permissions
        return True
    if not user.permissions:
        return False
    return perm in user.permissions.split(',')

@app.before_request
def ensure_admin_permissions():
    if current_user.is_authenticated and current_user.role == 'admin':
        all_perms = ['view_reports', 'create_report', 'manage_users', 'manage_templates', 'system_settings', 'digital_editor']
        perms = current_user.permissions.split(',') if current_user.permissions else []
        if set(all_perms) != set(perms):
            current_user.permissions = ','.join(all_perms)
            db.session.commit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 