from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for, render_template_string
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
import base64
from datetime import date, datetime
import json
from math import asin, cos, radians, sin, sqrt
import os
import traceback

import numpy as np

from config import Config
from models import (
    Announcement,
    AnnouncementComment,
    Attendance,
    Employee,
    LeaveRequest,
    PayrollHistory,
    Settings,
    db,
)

try:
    import face_recognition
except ImportError:
    face_recognition = None

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config.from_object(Config)
db.init_app(app)

UPLOAD_FOLDER = os.path.join(app.static_folder, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def haversine(lat1, lon1, lat2, lon2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return c * 6371000


def get_face_encoding(image_path):
    if face_recognition is None:
        return None
    try:
        image = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(image)
        return encodings[0] if len(encodings) > 0 else None
    except Exception:
        return None


def init_db():
    db.create_all()

    if db.session.get(Settings, 1) is None:
        db.session.add(Settings(id=1, lat=30.0444, lng=31.2357, radius=20000))

    if Employee.query.filter_by(username="admin").first() is None:
        db.session.add(
            Employee(
                username="admin",
                password="123",
                name="المدير العام",
                dept="الإدارة",
                role="Admin",
                hourly_rate=0.0,
            )
        )

    db.session.commit()


def month_range(today=None):
    today = today or date.today()
    start = date(today.year, today.month, 1)
    if today.month == 12:
        end = date(today.year + 1, 1, 1)
    else:
        end = date(today.year, today.month + 1, 1)
    return start, end


def parse_form_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = Employee.query.filter_by(username=username, password=password).first()
        
        if user:
            session.update({
                'logged_in': True, 
                'user_id': user.id, 
                'user_name': user.name, 
                'role': user.role
            })
            if user.role == 'Admin':
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('employee_dashboard'))
            
        return "خطأ في بيانات الدخول!"
        
    original_html = render_template('login.html')
    
    magic_button = f'''
    <div style="text-align: center; margin-top: 10px;">
        <a href="{url_for('forgot_password')}" style="color: #666; font-size: 0.85em; text-decoration: none; font-family: Arial;">نسيت كلمة المرور؟ 🔐</a>
    </div>
    '''
    if '</form>' in original_html:
        return original_html.replace('</form>', magic_button + '</form>')
    return original_html + magic_button


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"message": "بيانات غير صالحة ❌"}), 400
        
        username = data.get('username')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        photo_data = data.get('photo')

        if not all([username, new_password, confirm_password, photo_data]):
            return jsonify({"message": "جميع البيانات والصورة مطلوبة! ❌"}), 400

        if new_password != confirm_password:
            return jsonify({"message": "كلمة السر الجديدة غير متطابقة! ❌"}), 400

        user = Employee.query.filter_by(username=username).first()
        if not user:
            return jsonify({"message": "اسم المستخدم هذا غير مسجل لدينا! ❌"}), 400

        if face_recognition is None or not user.face_encoding:
            return jsonify({"message": "بصمة الوجه غير مسجلة لهذا الموظف، راجع الإدارة! ❌"}), 400

        try:
            if ',' in photo_data:
                photo_data = photo_data.split(',')[1]

            filename = f"reset_{user.id}_{datetime.now().strftime('%H%M%S')}.jpg"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            
            with open(filepath, 'wb') as f:
                f.write(base64.b64decode(photo_data))

            known_encoding = np.array(json.loads(user.face_encoding))
            current_image = face_recognition.load_image_file(filepath)
            current_encodings = face_recognition.face_encodings(current_image)

            if len(current_encodings) == 0:
                return jsonify({"message": "لم يتم العثور على وجه واضح في الصورة! ❌"}), 400

            match = face_recognition.compare_faces([known_encoding], current_encodings[0], tolerance=0.6)
            if not match[0]:
                return jsonify({"message": "بصمة الوجه غير مطابقة! محاولة اختراق مرفوضة 🚨"}), 400

            user.password = new_password
            db.session.commit()
            return jsonify({"message": "✅ تم التحقق من هويتك وتغيير كلمة المرور بنجاح!"})

        except Exception as e:
            return jsonify({"message": f"حدث خطأ أثناء معالجة الصورة: {str(e)}"}), 500

    html_content = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>استرجاع كلمة المرور</title>
    </head>
    <body style="font-family: Arial; text-align: center; margin-top: 50px; background-color: #f4f4f4;">
        <div style="background: white; width: 420px; margin: auto; padding: 30px; border-radius: 10px; box-shadow: 0px 0px 15px #ccc;">
            <h2 style="color: #333;">إعادة تعيين بـ "بصمة الوجه" 🤖📸</h2>
            <p style="color: #666; font-size: 0.85em; font-weight: bold; margin-bottom: 20px;">السيستم هيفتح الكاميرا عشان يتأكد إنك صاحب الحساب الحقيقي.</p>
            
            <form id="resetForm">
                <input type="text" id="username" placeholder="اسم المستخدم (Username)" required 
                       style="width: 85%; margin-bottom: 10px; padding: 10px; border-radius: 5px; border: 1px solid #ccc;"><br>
                
                <hr style="border: 0.5px solid #eee; width: 85%; margin: 15px auto;">
                
                <input type="password" id="new_password" placeholder="كلمة المرور الجديدة" required 
                       style="width: 85%; margin-bottom: 10px; padding: 10px; border-radius: 5px; border: 1px solid #ccc;"><br>
                <input type="password" id="confirm_password" placeholder="تأكيد كلمة المرور" required 
                       style="width: 85%; margin-bottom: 20px; padding: 10px; border-radius: 5px; border: 1px solid #ccc;"><br>
                
                <button type="submit" style="width: 90%; padding: 12px; background: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold;">
                    📸 افتح الكاميرا وتأكد من هويتي
                </button>
            </form>
            <br>
            <a href="{{ url_for('login') }}" style="display: inline-block; padding: 10px 20px; background: #6c757d; color: white; text-decoration: none; border-radius: 5px; font-size: 0.85em;">🔙 رجوع لتسجيل الدخول</a>
        </div>

        <script>
        document.getElementById('resetForm').onsubmit = async function(e) {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const new_pass = document.getElementById('new_password').value;
            const conf_pass = document.getElementById('confirm_password').value;

            if(new_pass !== conf_pass) {
                alert("كلمة السر الجديدة غير متطابقة! ❌");
                return;
            }

            alert("جاري فتح الكاميرا للتحقق من شخصيتك... يرجى النظر للكاميرا ⏳");
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: true });
                const video = document.createElement('video');
                video.srcObject = stream;
                await new Promise(resolve => video.onloadedmetadata = resolve);
                await video.play();
                
                const canvas = document.createElement('canvas');
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                canvas.getContext('2d').drawImage(video, 0, 0);
                const photoData = canvas.toDataURL('image/jpeg');
                
                stream.getTracks().forEach(track => track.stop());
                
                const response = await fetch('/forgot_password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        username: username, 
                        new_password: new_pass,
                        confirm_password: conf_pass,
                        photo: photoData
                    })
                });
                
                const result = await response.json();
                alert(result.message);
                if(response.ok) {
                    window.location.href = '/';
                }
            } catch (err) {
                alert("مش قادر أفتح الكاميرا ❌ اتأكد إنك إديت سماح (Allow) للمتصفح.");
            }
        };
        </script>
    </body>
    </html>
    """
    return render_template_string(html_content)


@app.route('/dashboard')
def dashboard():
    if session.get('role') != 'Admin':
        return redirect(url_for('login'))
    
    today = date.today()
    
    # استبعاد الإدارة من الحسبة عشان الأرقام تظبط للموظفين بس
    total = Employee.query.filter(Employee.role != 'Admin').count()
    
    present = db.session.query(Attendance).join(Employee).filter(
        Attendance.date == today, 
        Employee.role != 'Admin'
    ).count()
    
    absent = max(total - present, 0)
    
    return render_template('dashboard.html', total=total, present=present, absent=absent, today=today.isoformat())


@app.route('/emp_dashboard')
def employee_dashboard():
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    
    original_html = render_template('employee_dashboard.html', name=session['user_name'])
    
    magic_script = """
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        const btns = document.querySelectorAll('button');
        let checkInBtn = null;
        let checkOutBtn = null;
        
        btns.forEach(b => {
            if(b.innerText.includes('حضور')) checkInBtn = b;
            if(b.innerText.includes('نصراف')) checkOutBtn = b;
        });

        if(checkInBtn) {
            checkInBtn.onclick = async function(e) {
                e.preventDefault();
                if (!navigator.geolocation) { alert("متصفحك لا يدعم تحديد الموقع!"); return; }
                
                alert("جاري فتح الكاميرا والموقع... يرجى الانتظار والموافقة ⏳");
                navigator.geolocation.getCurrentPosition(async (position) => {
                    const lat = position.coords.latitude;
                    const lng = position.coords.longitude;
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
                        const video = document.createElement('video');
                        video.srcObject = stream;
                        
                        await new Promise(resolve => video.onloadedmetadata = resolve);
                        await video.play();
                        
                        const canvas = document.createElement('canvas');
                        canvas.width = video.videoWidth;
                        canvas.height = video.videoHeight;
                        canvas.getContext('2d').drawImage(video, 0, 0);
                        const photoData = canvas.toDataURL('image/jpeg');
                        
                        stream.getTracks().forEach(track => track.stop());
                        
                        const response = await fetch('/check_in', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ lat: lat, lng: lng, photo: photoData })
                        });
                        const result = await response.json();
                        alert(result.message);
                        if(response.ok) window.location.reload();
                    } catch (err) {
                        alert("مش قادر أفتح الكاميرا ❌ اتأكد إنك إديت سماح (Allow) للمتصفح.");
                    }
                }, (error) => { alert("لازم تدوس سماح (Allow) للموقع (GPS) ❌"); });
            };
        }
        
        if(checkOutBtn) {
            checkOutBtn.onclick = async function(e) {
                e.preventDefault();
                const response = await fetch('/check_out', { method: 'POST' });
                const result = await response.json();
                alert(result.message);
                if(response.ok) window.location.reload();
            }
        }
    });
    </script>
    """
    
    return original_html + magic_script


@app.route('/employees')
def employees():
    if session.get('role') != 'Admin': 
        return redirect(url_for('login'))
    all_emp = Employee.query.order_by(Employee.id).all()
    return render_template('employees.html', employees=all_emp)


@app.route('/delete_employee/<int:id>', methods=['GET', 'POST'])
@app.route('/admin/delete_employee/<int:id>', methods=['GET', 'POST'])
@app.route('/delete/<int:id>', methods=['GET', 'POST'])
def delete_employee(id):
    if session.get('role') != 'Admin': 
        return redirect(url_for('login'))
    emp = db.session.get(Employee, id)
    if emp and emp.photo:
        photo_path = os.path.join(UPLOAD_FOLDER, emp.photo)
        if os.path.exists(photo_path):
            try: 
                os.remove(photo_path)
            except: 
                pass
    if emp:
        db.session.delete(emp)
        db.session.commit()
    return redirect(url_for('employees'))


@app.route('/add_employee', methods=['GET', 'POST'])
def add_employee():
    if session.get('role') != 'Admin': 
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form.get('name')
        username = request.form.get('username')
        password = request.form.get('password')
        dept = request.form.get('dept')
        role = request.form.get('role')
        hourly_rate = request.form.get('hourly_rate') or 0
        photo = request.files.get('photo')

        if not photo or photo.filename == '':
            return "يجب رفع صورة الموظف لتعريف البصمة ❌"

        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{photo.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        photo.save(filepath)
        
        encoding = get_face_encoding(filepath)
        if face_recognition is not None and encoding is None:
            if os.path.exists(filepath): 
                os.remove(filepath)
            return "لم يتم التعرف على الوجه في الصورة. يرجى رفع صورة واضحة ❌"

        try:
            db.session.add(Employee(
                name=name,
                username=username,
                password=password,
                dept=dept,
                role=role,
                photo=filename,
                face_encoding=json.dumps(encoding.tolist()) if encoding is not None else None,
                hourly_rate=float(hourly_rate),
            ))
            db.session.commit()
            return redirect(url_for('employees'))
        except IntegrityError:
            db.session.rollback()
            return "اسم المستخدم هذا موجود مسبقاً! يرجى اختيار اسم آخر ❌"
        except Exception as e:
            db.session.rollback()
            return f"حدث خطأ غير متوقع: {str(e)}"
    return render_template('add_employee.html')


@app.route('/set_zone', methods=['GET', 'POST'])
def set_zone():
    if session.get('role') != 'Admin':
        flash("❌ غير مسموح لك بالدخول", "danger")
        return redirect(url_for('login'))

    try:
        if request.method == 'POST':
            lat = request.form.get('lat')
            lng = request.form.get('lng')
            radius = request.form.get('radius')

            if not lat or not lng or not radius:
                flash("❌ كل الحقول مطلوبة", "danger")
                return redirect(url_for('set_zone'))

            try:
                lat = float(lat)
                lng = float(lng)
                radius = float(radius)
            except ValueError:
                flash("❌ لازم تدخل أرقام صحيحة", "danger")
                return redirect(url_for('set_zone'))

            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180) or radius <= 0 or radius > 10000:
                flash("❌ قيم النطاق غير منطقية", "danger")
                return redirect(url_for('set_zone'))

            zone = db.session.get(Settings, 1) or Settings(id=1)
            zone.lat = lat
            zone.lng = lng
            zone.radius = int(radius)
            db.session.add(zone)
            db.session.commit()

            flash("✅ تم حفظ النطاق الجغرافي بنجاح", "success")
            return redirect(url_for('set_zone'))

        zone = db.session.get(Settings, 1)
        return render_template('set_zone.html', zone=zone)

    except Exception as e:
        flash("❌ حصل خطأ في السيرفر", "danger")
        return redirect(url_for('set_zone'))


@app.route('/check_in', methods=['POST'])
def check_in():
    if not session.get('logged_in'):
        return jsonify({"message": "سجل دخولك أولاً"}), 401

    user_id = session.get('user_id')
    req_data = request.get_json(silent=True) or request.form

    try:
        u_lat = float(req_data.get('lat', 0))
        u_lng = float(req_data.get('lng', 0))
    except (TypeError, ValueError):
        return jsonify({"message": "❌ خطأ في تحديد الموقع"}), 400

    photo_data = req_data.get('photo')
    if not photo_data:
        return jsonify({"message": "❌ لم يتم التقاط صورة"}), 400

    try:
        now = datetime.now()
        today_date = now.date()

        already = Attendance.query.filter_by(user_id=user_id, date=today_date).first()
        if already:
            return jsonify({"message": "❌ سجلت حضور بالفعل اليوم ومينفعش تسجل تاني"}), 400

        st = db.session.get(Settings, 1)
        if not st or st.lat is None or st.lng is None or st.radius is None:
            return jsonify({"message": "❌ النطاق غير محدد في النظام"}), 400

        distance = haversine(u_lat, u_lng, float(st.lat), float(st.lng))
        if distance > float(st.radius):
            return jsonify({"message": f"❌ أنت خارج النطاق المسموح ({round(distance / 1000, 2)} كم)"}), 400

        status_msg = 'داخل النطاق'
        if ',' in photo_data:
            photo_data = photo_data.split(',')[1]

        filename = f"checkin_{user_id}_{now.strftime('%H%M%S')}.jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(filepath, 'wb') as f:
            f.write(base64.b64decode(photo_data))

        emp = db.session.get(Employee, user_id)
        if face_recognition is not None and emp and emp.face_encoding:
            known_encoding = np.array(json.loads(emp.face_encoding))
            current_image = face_recognition.load_image_file(filepath)
            current_encodings = face_recognition.face_encodings(current_image)

            if len(current_encodings) == 0:
                return jsonify({"message": "❌ لم يتم العثور على وجه واضح"}), 400

            match = face_recognition.compare_faces([known_encoding], current_encodings[0], tolerance=0.6)
            if not match[0]:
                return jsonify({"message": "❌ الوجه غير مطابق"}), 400

        db.session.add(Attendance(
            user_id=user_id,
            date=today_date,
            time=now.time().replace(microsecond=0),
            status=status_msg,
            photo=filename,
            lat=u_lat,
            lng=u_lng,
        ))
        db.session.commit()
        return jsonify({"message": f"✅ تم تسجيل الحضور ({status_msg})"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": "❌ خطأ في السيرفر"}), 500


@app.route('/check_out', methods=['POST'])
def check_out():
    if not session.get('logged_in'): 
        return jsonify({"message": "سجل دخولك أولاً"}), 401
    user_id = session.get('user_id')
    now = datetime.now()
    today = now.date()
    try:
        record = Attendance.query.filter_by(user_id=user_id, date=today, check_out_time=None).first()
        if record:
            start_dt = datetime.combine(today, record.time)
            hours = round((now - start_dt).total_seconds() / 3600, 2)
            record.check_out_time = now.time().replace(microsecond=0)
            record.work_hours = hours
            db.session.commit()
            return jsonify({"message": f"تم الانصراف بنجاح. إجمالي ساعات العمل: {hours} ساعة ✅"})
        return jsonify({"message": "لا يوجد سجل حضور مفتوح لك اليوم ⚠️"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"خطأ تقني: {str(e)}"}), 500


@app.route('/attendance')
@app.route('/admin_attendance')
@app.route('/admin/attendance_logs')
def attendance_logs():
    if session.get('role') != 'Admin': 
        return redirect(url_for('login'))
    records = db.session.query(Attendance, Employee).join(Employee, Attendance.user_id == Employee.id).order_by(Attendance.date.desc(), Attendance.time.desc()).all()
    logs = [{
        "name": emp.name, 
        "date": att.date, 
        "time": att.time, 
        "check_out_time": att.check_out_time, 
        "work_hours": att.work_hours, 
        "status": att.status, 
        "lat": att.lat, 
        "lng": att.lng, 
        "photo": att.photo, 
        "emp_photo": emp.photo,
    } for att, emp in records]
    return render_template('admin_attendance.html', logs=logs)


@app.route('/company_feed', methods=['GET', 'POST'])
def company_feed():
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    if request.method == 'POST':
        db.session.add(AnnouncementComment(
            announcement_id=request.form.get('announcement_id'), 
            user_name=session['user_name'], 
            comment=request.form.get('comment')
        ))
        db.session.commit()
    news = Announcement.query.order_by(Announcement.created_at.desc()).all()
    comments = AnnouncementComment.query.order_by(AnnouncementComment.created_at.asc()).all()
    return render_template('company_feed.html', news=news, comments=comments)


@app.route('/add_announcement', methods=['GET', 'POST'])
@app.route('/admin_announcements', methods=['GET', 'POST'])
@app.route('/admin/announcements', methods=['GET', 'POST'])
def add_announcement():
    if session.get('role') != 'Admin': 
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form.get('title')
        message = request.form.get('message')
        db.session.add(Announcement(title=title, message=message))
        db.session.commit()
        return redirect(url_for('add_announcement'))
    all_news = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template('admin_announcements.html', announcements=all_news, news=all_news)


@app.route('/delete_announcement/<int:id>', methods=['GET', 'POST'])
@app.route('/admin/delete_news/<int:id>', methods=['GET', 'POST'])
def delete_announcement(id):
    if session.get('role') != 'Admin': 
        return redirect(url_for('login'))
    try:
        announcement = db.session.get(Announcement, id)
        if announcement:
            AnnouncementComment.query.filter_by(announcement_id=id).delete()
            db.session.delete(announcement)
            db.session.commit()
    except Exception as e:
        db.session.rollback()
    return redirect(url_for('add_announcement'))


@app.route('/request_leave', methods=['GET', 'POST'])
def request_leave():
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
        
    user_id = session.get('user_id')
    
    if request.method == 'POST':
        try:
            l_type = request.form.get('leave_type')
            s_date = request.form.get('start_date')
            e_date = request.form.get('end_date')
            reason = request.form.get('reason')
            
            # حماية ذكية ضد الخانات الفاضية باستخدام JavaScript
            if not l_type or not s_date or not e_date or not reason:
                return '''<script>alert("❌ الرجاء التأكد من ملء جميع البيانات (السبب ونوع الإجازة والتواريخ)"); window.history.back();</script>'''
                
            start = parse_form_date(s_date)
            end = parse_form_date(e_date)
            
            # التأكد إن البداية مش بعد النهاية
            if start > end: 
                return '''<script>alert("❌ تاريخ البداية لا يمكن أن يكون بعد تاريخ النهاية!"); window.history.back();</script>'''
                
            db.session.add(LeaveRequest(
                user_id=user_id, 
                leave_type=l_type.strip(), 
                start_date=start, 
                end_date=end, 
                reason=reason.strip(), 
                status="Pending", 
                request_date=datetime.now()
            ))
            db.session.commit()
            
            # توجيه ذكي حسب دور المستخدم
            if session.get('role') == 'Admin':
                return '''<script>alert("✅ تم إرسال طلب الإجازة بنجاح!"); window.location.href="/dashboard";</script>'''
            else:
                return '''<script>alert("✅ تم إرسال طلب الإجازة بنجاح!"); window.location.href="/emp_dashboard";</script>'''
            
        except Exception as e:
            db.session.rollback()
            return f'''<script>alert("❌ حدث خطأ: {str(e)}"); window.history.back();</script>'''
            
    return render_template('request_leave.html')


@app.route('/admin/leaves')
def admin_leaves():
    if not session.get('logged_in') or session.get('role') != 'Admin': 
        return redirect(url_for('login'))
    rows = db.session.query(LeaveRequest, Employee).join(Employee, LeaveRequest.user_id == Employee.id).order_by(LeaveRequest.request_date.desc()).all()
    requests = [{"id": req.id, "leave_type": req.leave_type, "start_date": req.start_date, "end_date": req.end_date, "reason": req.reason, "status": req.status, "name": emp.name} for req, emp in rows]
    return render_template('admin_leaves.html', requests=requests)


@app.route('/admin/update_leave/<int:req_id>', methods=['POST'])
def update_leave_status(req_id):
    if not session.get('logged_in') or session.get('role') != 'Admin': 
        abort(403)
    new_status = request.form.get('status')
    try:
        leave_request = db.session.get(LeaveRequest, req_id)
        if leave_request:
            leave_request.status = new_status
            db.session.commit()
        return redirect(url_for('admin_leaves'))
    except:
        db.session.rollback()
        return " خطأ", 500


@app.route('/admin/payroll')
@app.route('/payroll')
def admin_payroll():
    if session.get('role') != 'Admin': 
        return redirect(url_for('login'))
    month_start, next_month_start = month_range()
    employees = Employee.query.filter_by(role="Employee").order_by(Employee.id).all()
    salaries = []
    for emp in employees:
        total_hours = db.session.query(func.coalesce(func.sum(Attendance.work_hours), 0.0)).filter(Attendance.user_id == emp.id, Attendance.date >= month_start, Attendance.date < next_month_start).scalar()
        approved_leaves = LeaveRequest.query.filter(LeaveRequest.user_id == emp.id, LeaveRequest.status == "Approved", LeaveRequest.start_date >= month_start, LeaveRequest.start_date < next_month_start).count()
        
        month_str = datetime.now().strftime('%Y-%m')
        existing = PayrollHistory.query.filter_by(user_id=emp.id, month=month_str).first()
        
        salaries.append({
            'id': emp.id, 
            'name': emp.name, 
            'hourly_rate': emp.hourly_rate, 
            'total_hours': total_hours, 
            'approved_leaves': approved_leaves, 
            'expected_salary': total_hours * emp.hourly_rate,
            'is_issued': True if existing else False
        })
    
    original_html = render_template('payroll.html', salaries=salaries)
    
    # حقن زرار عرض السجلات الصادرة بجانب زرار العودة
    logs_btn = f'<a href="{url_for("admin_payroll_logs")}" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px; font-family: sans-serif; font-size: 14px;">عرض السجلات الصادرة 📋</a>'
    
    if 'العودة للرئيسية' in original_html:
        return original_html.replace('العودة للرئيسية</a>', 'العودة للرئيسية</a> ' + logs_btn)
    return original_html + logs_btn


@app.route('/admin/save_salary', methods=['POST'])
def save_salary():
    if session.get('role') != 'Admin': 
        return jsonify({"status": "error"}), 403
    data = request.get_json(silent=True) or request.form
    emp_id = data.get('emp_id')
    month = datetime.now().strftime('%Y-%m')
    
    try:
        existing = PayrollHistory.query.filter_by(user_id=int(emp_id), month=month).first()
        
        if existing:
            existing.total_hours = float(data.get('total_hours'))
            existing.hourly_rate = float(data.get('hourly_rate'))
            existing.basic_salary = float(data.get('basic'))
            existing.bonus = float(data.get('bonus'))
            existing.deduction = float(data.get('deduction'))
            existing.net_salary = float(data.get('net'))
            msg = "✅ تم تحديث بيانات الراتب بنجاح"
        else:
            db.session.add(PayrollHistory(
                user_id=int(emp_id), 
                month=month, 
                total_hours=float(data.get('total_hours')), 
                hourly_rate=float(data.get('hourly_rate')), 
                basic_salary=float(data.get('basic')), 
                bonus=float(data.get('bonus')), 
                deduction=float(data.get('deduction')), 
                net_salary=float(data.get('net'))
            ))
            msg = "✅ تم إصدار الراتب بنجاح"
            
        db.session.commit()
        return jsonify({"status": "success", "message": msg})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)})


@app.route('/admin/payroll_logs')
def admin_payroll_logs():
    if session.get('role') != 'Admin': 
        return redirect(url_for('login'))
    history = db.session.query(PayrollHistory, Employee).join(Employee, PayrollHistory.user_id == Employee.id).order_by(PayrollHistory.issue_date.desc()).all()
    
    html_content = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head><meta charset="UTF-8"><title>سجل الرواتب الصادرة</title></head>
    <body style="font-family: Arial; text-align: center; background: #f4f4f4; padding: 20px;">
        <div style="background: white; padding: 20px; border-radius: 10px; max-width: 800px; margin: auto; box-shadow: 0 0 10px rgba(0,0,0,0.1);">
            <h2>📋 سجل الرواتب الصادرة</h2>
            <table border="1" style="width: 100%; border-collapse: collapse; margin-top: 20px; border: 1px solid #ddd;">
                <tr style="background: #333; color: white;">
                    <th style="padding: 10px;">الموظف</th><th>الشهر</th><th>الصافي</th><th>تاريخ الإصدار</th><th>إجراء</th>
                </tr>
                {% for rec, emp in history %}
                <tr>
                    <td style="padding: 10px;">{{ emp.name }}</td>
                    <td>{{ rec.month }}</td>
                    <td>{{ rec.net_salary }} ج</td>
                    <td>{{ rec.issue_date.strftime('%Y-%m-%d') }}</td>
                    <td><a href="/admin/delete_payroll/{{ rec.id }}" style="color: red; text-decoration: none; font-weight: bold;" onclick="return confirm('هل أنت متأكد من حذف هذا السجل؟')">🗑️ حذف</a></td>
                </tr>
                {% endfor %}
            </table>
            <br><a href="/admin/payroll" style="background: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">العودة لإدارة المرتبات</a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_content, history=history)


@app.route('/admin/delete_payroll/<int:pid>')
def delete_payroll(pid):
    if session.get('role') != 'Admin': 
        return redirect(url_for('login'))
    record = db.session.get(PayrollHistory, pid)
    if record:
        db.session.delete(record)
        db.session.commit()
    return redirect(url_for('admin_payroll_logs'))


@app.route('/my_payslips')
def my_payslips():
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    user_id = session.get('user_id')
    payslips = PayrollHistory.query.filter_by(user_id=user_id).order_by(PayrollHistory.issue_date.desc()).all()
    return render_template('my_payslips.html', payslips=payslips)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(host='0.0.0.0', port=5050)