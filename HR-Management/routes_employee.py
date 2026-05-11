from flask import redirect, render_template, request, session, url_for, render_template_string
import os
import base64
from datetime import date, datetime
import numpy as np

from utils import haversine, parse_form_date

try:
    import face_recognition
except ImportError:
    face_recognition = None

def setup_employee_routes(app, db, Employee, Attendance, Settings, LeaveRequest, PayrollHistory, Announcement, AnnouncementComment, UPLOAD_FOLDER):
    
    @app.route('/emp_dashboard')
    def employee_dashboard():
        if not session.get('logged_in'): return redirect(url_for('login'))
        
        user = db.session.get(Employee, session.get('user_id'))
        original_html = render_template('employee_dashboard.html', name=session['user_name'], user=user)
        
        original_html = original_html.replace('Attendance History', '').replace('My Profile', '')
        original_html = original_html.replace('href="/my_attendance_history"', 'style="display:none;"')
        original_html = original_html.replace('href="/my_profile"', 'style="display:none;"')
        
        magic_script = """
        <script>
        document.addEventListener('DOMContentLoaded', function() {
            const btns = document.querySelectorAll('button'); let checkInBtn = null; let checkOutBtn = null;
            btns.forEach(b => { if(b.innerText.includes('حضور')) checkInBtn = b; if(b.innerText.includes('نصراف')) checkOutBtn = b; });
            if(checkInBtn) {
                checkInBtn.onclick = async function(e) {
                    e.preventDefault(); if (!navigator.geolocation) { alert("متصفحك لا يدعم تحديد الموقع!"); return; }
                    alert("جاري فتح الكاميرا والموقع... يرجى الانتظار والموافقة ⏳");
                    navigator.geolocation.getCurrentPosition(async (position) => {
                        const lat = position.coords.latitude; const lng = position.coords.longitude;
                        try {
                            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
                            const video = document.createElement('video'); video.srcObject = stream;
                            await new Promise(resolve => video.onloadedmetadata = resolve); await video.play();
                            const canvas = document.createElement('canvas'); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
                            canvas.getContext('2d').drawImage(video, 0, 0); const photoData = canvas.toDataURL('image/jpeg');
                            stream.getTracks().forEach(track => track.stop());
                            const response = await fetch('/check_in', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lat: lat, lng: lng, photo: photoData }) });
                            const result = await response.json(); alert(result.message); if(response.ok) window.location.reload();
                        } catch (err) { alert("مش قادر أفتح الكاميرا ❌ اتأكد إنك إديت سماح."); }
                    }, (error) => { alert("لازم تدوس سماح للموقع (GPS) ❌"); });
                };
            }
            if(checkOutBtn) {
                checkOutBtn.onclick = async function(e) {
                    e.preventDefault(); const response = await fetch('/check_out', { method: 'POST' });
                    const result = await response.json(); alert(result.message); if(response.ok) window.location.reload();
                }
            }
        });
        </script>
        """
        return original_html + magic_script

    @app.route('/my_profile')
    def my_profile():
        if not session.get('logged_in'): return redirect(url_for('login'))
        user = db.session.get(Employee, session.get('user_id'))
        html_content = render_template('my_profile.html', user=user)
        html_content = html_content.replace('Email:', '').replace('Not set', '')
        return html_content

    @app.route('/my_attendance_history')
    def my_attendance_history():
        if not session.get('logged_in'): return redirect(url_for('login'))
        user_id = session.get('user_id')
        logs = Attendance.query.filter_by(user_id=user_id).order_by(Attendance.date.desc(), Attendance.time.desc()).all()
        return render_template('my_attendance_history.html', logs=logs)

    @app.route('/check_in', methods=['POST'])
    def check_in():
        if not session.get('logged_in'): return '{"message": "سجل دخولك أولاً"}', 401
        user_id, req_data = session.get('user_id'), request.get_json(silent=True) or request.form
        try: u_lat, u_lng = float(req_data.get('lat', 0)), float(req_data.get('lng', 0))
        except: return '{"message": "❌ خطأ في تحديد الموقع"}', 400
        photo_data = req_data.get('photo')
        if not photo_data: return '{"message": "❌ لم يتم التقاط صورة"}', 400
        try:
            now = datetime.now(); today_date = now.date()
            if Attendance.query.filter_by(user_id=user_id, date=today_date).first(): return '{"message": "❌ سجلت حضور بالفعل اليوم"}', 400
            st = db.session.get(Settings, 1)
            if not st or st.lat is None or st.lng is None or st.radius is None: return '{"message": "❌ النطاق غير محدد في النظام"}', 400
            if haversine(u_lat, u_lng, float(st.lat), float(st.lng)) > float(st.radius): return '{"message": "❌ أنت خارج النطاق المسموح"}', 400
            status_msg = 'داخل النطاق'
            if ',' in photo_data: photo_data = photo_data.split(',')[1]
            filename = f"checkin_{user_id}_{now.strftime('%H%M%S')}.jpg"; filepath = os.path.join(UPLOAD_FOLDER, filename)
            with open(filepath, 'wb') as f: f.write(base64.b64decode(photo_data))
            
            emp = db.session.get(Employee, user_id)
            if face_recognition is not None and emp and emp.face_encoding:
                known_encoding = np.array([float(x) for x in emp.face_encoding.split(",")])
                current_image = face_recognition.load_image_file(filepath)
                current_encodings = face_recognition.face_encodings(current_image)
                if len(current_encodings) == 0: return '{"message": "❌ لم يتم العثور على وجه واضح"}', 400
                match = face_recognition.compare_faces([known_encoding], current_encodings[0], tolerance=0.6)
                if not match[0]: return '{"message": "❌ الوجه غير مطابق"}', 400
            
            db.session.add(Attendance(user_id=user_id, date=today_date, time=now.time().replace(microsecond=0), status=status_msg, photo=filename, lat=u_lat, lng=u_lng))
            db.session.commit()
            return '{"message": "✅ تم تسجيل الحضور (' + status_msg + ')"}'
        except Exception as e:
            db.session.rollback()
            return '{"message": "❌ خطأ في السيرفر"}', 500

    @app.route('/check_out', methods=['POST'])
    def check_out():
        if not session.get('logged_in'): return '{"message": "سجل دخولك أولاً"}', 401
        user_id = session.get('user_id')
        now = datetime.now()
        today = now.date()
        
        try:
            record = Attendance.query.filter_by(user_id=user_id, date=today).order_by(Attendance.id.desc()).first()
            if record and not record.check_out_time:
                start_dt = datetime.combine(today, record.time)
                record.check_out_time = now.time().replace(microsecond=0)
                record.work_hours = round((now - start_dt).total_seconds() / 3600, 2)
                db.session.commit()
                return '{"message": "تم الانصراف بنجاح. الساعات: ' + str(record.work_hours) + ' ✅"}'
            return '{"message": "لا يوجد سجل حضور مفتوح لك اليوم أو تم الانصراف مسبقاً ⚠️"}'
        except Exception as e:
            db.session.rollback()
            return '{"message": "خطأ تقني في السيرفر"}', 500

    @app.route('/company_feed', methods=['GET', 'POST'])
    def company_feed():
        if not session.get('logged_in'): return redirect(url_for('login'))
        if request.method == 'POST':
            db.session.add(AnnouncementComment(announcement_id=request.form.get('announcement_id'), user_name=session['user_name'], comment=request.form.get('comment')))
            db.session.commit()
        news = Announcement.query.order_by(Announcement.created_at.desc()).all()
        comments = AnnouncementComment.query.order_by(AnnouncementComment.created_at.asc()).all()
        
        original_html = render_template('company_feed.html', news=news, comments=comments)
        # تحويل الرابط للموظف عشان ما ينطردش
        if session.get('role') != 'Admin':
            original_html = original_html.replace('href="/dashboard"', 'href="/emp_dashboard"')
        
        return original_html

    @app.route('/request_leave', methods=['GET', 'POST'])
    def request_leave():
        if not session.get('logged_in'): return redirect(url_for('login'))
        user_id = session.get('user_id')
        if request.method == 'POST':
            try:
                l_type, s_date, e_date, reason = request.form.get('leave_type'), request.form.get('start_date'), request.form.get('end_date'), request.form.get('reason')
                if not l_type or not s_date or not e_date or not reason: return '''<script>alert("❌ الرجاء ملء جميع البيانات"); window.history.back();</script>'''
                start, end = parse_form_date(s_date), parse_form_date(e_date)
                if start > end: return '''<script>alert("❌ البداية لا يمكن أن تكون بعد النهاية!"); window.history.back();</script>'''
                db.session.add(LeaveRequest(user_id=user_id, leave_type=l_type.strip(), start_date=start, end_date=end, reason=reason.strip(), status="Pending", request_date=datetime.now()))
                db.session.commit()
                return '''<script>alert("✅ تم إرسال الطلب بنجاح!"); window.location.href="/emp_dashboard";</script>'''
            except Exception as e: db.session.rollback(); return f'''<script>alert("❌ حدث خطأ"); window.history.back();</script>'''
        
        original_html = render_template('request_leave.html')
        
        # إضافة زرار العودة لصفحة الإجازات
        back_url = url_for('dashboard') if session.get('role') == 'Admin' else url_for('employee_dashboard')
        back_btn = f'''<div style="position: absolute; top: 20px; left: 20px; z-index: 9999;"><a href="{back_url}" style="background: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">🔙 العودة للرئيسية</a></div>'''
        
        return original_html + back_btn

    @app.route('/my_payslips')
    def my_payslips():
        if not session.get('logged_in'): return redirect(url_for('login'))
        payslips = PayrollHistory.query.filter_by(user_id=session.get('user_id')).order_by(PayrollHistory.issue_date.desc()).all()
        
        original_html = render_template('my_payslips.html', payslips=payslips)
        
        # تغيير رابط العودة للموظف عشان ما ينطردش
        if session.get('role') != 'Admin':
            original_html = original_html.replace('href="/dashboard"', 'href="/emp_dashboard"')
            
        return original_html