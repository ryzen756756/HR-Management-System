from flask import redirect, render_template, request, session, url_for, render_template_string
import os, cv2, numpy as np
from datetime import datetime
from utils import haversine

try:
    import face_recognition
except ImportError:
    face_recognition = None

def setup_employee_routes(app, db, Employee, Attendance, Settings, LeaveRequest, PayrollHistory, Announcement, AnnouncementComment, UPLOAD_FOLDER):
    
    @app.route('/emp_dashboard')
    def employee_dashboard():
        if not session.get('logged_in'): return redirect(url_for('login'))
        user, today = db.session.get(Employee, session.get('user_id')), datetime.now().date()
        att = Attendance.query.filter_by(user_id=user.id, date=today).first()
        
        msg = f'<div style="background:#d4edda; color:#155724; padding:15px; border-radius:10px; margin-bottom:10px; text-align:center; font-weight:bold;">✅ {request.args.get("msg")}</div>' if request.args.get('msg') else ""
        
        loc_script = "navigator.geolocation.getCurrentPosition(p=>{document.getElementById('lat').value=p.coords.latitude; document.getElementById('lng').value=p.coords.longitude;});"
        
        if not att:
            btn = f'<form action="/check_in_python" method="POST"><input type="hidden" name="lat" id="lat"><input type="hidden" name="lng" id="lng"><button type="submit" onmouseover="{loc_script}" style="width:100%; padding:20px; background:#007bff; color:white; border:none; border-radius:12px; font-size:18px; font-weight:bold; cursor:pointer;">📷 تسجيل الحضور (GPS + كاميرا)</button></form>'
        elif not att.check_out_time:
            btn = '<form action="/check_out_python" method="POST"><button type="submit" style="width:100%; padding:20px; background:#dc3545; color:white; border:none; border-radius:12px; font-size:18px; font-weight:bold; cursor:pointer;">🚪 تسجيل الانصراف الآن</button></form>'
        else:
            btn = '<div style="padding:20px; background:#f8f9fa; border-radius:12px; text-align:center; color:#6c757d; font-weight:bold;">✨ وردية اليوم مكتملة بنجاح</div>'

        ui = f'<div style="margin:20px 0;">{msg}{btn}<div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:15px;"><a href="/request_leave" style="background:#ffc107; padding:12px; border-radius:8px; text-decoration:none; text-align:center; color:black; font-weight:bold;">📅 الإجازات</a><a href="/my_payslips" style="background:#17a2b8; padding:12px; border-radius:8px; text-decoration:none; text-align:center; color:white; font-weight:bold;">💰 المرتبات</a></div><a href="/company_feed" style="display:block; margin-top:10px; background:white; color:#007bff; padding:12px; border-radius:8px; text-decoration:none; text-align:center; border:1px solid #007bff; font-weight:bold;">📢 أخبار الشركة</a><a href="/logout" style="display:block; margin-top:15px; background:#dc3545; color:white; padding:12px; border-radius:8px; text-decoration:none; text-align:center; font-weight:bold;">🚪 تسجيل الخروج</a></div>'
        
        orig = render_template('employee_dashboard.html', name=session['user_name'], user=user)
        return render_template_string(orig.split('<button')[0] + ui + '</div></div></body></html>') if '<button' in orig else orig + ui

    @app.route('/check_in_python', methods=['POST'])
    def check_in():
        user_id = session.get('user_id')
        u_lat, u_lng = request.form.get('lat'), request.form.get('lng')
        
        zone = db.session.get(Settings, 1)
        if zone and u_lat and u_lng:
            try:
                dist = haversine(float(u_lat), float(u_lng), zone.lat, zone.lng)
                if dist > zone.radius:
                    return render_template_string(f'<script>alert("❌ أنت خارج النطاق! المسافة: {int(dist)} متر"); window.location.href="/emp_dashboard";</script>')
            except: pass

        cap = cv2.VideoCapture(0)
        if not cap.isOpened(): return "خطأ في الكاميرا"
        for _ in range(5): cap.read()
        ret, frame = cap.read(); cap.release(); cv2.destroyAllWindows()
        if not ret: return "فشل التقاط الصورة"
        
        fn = f"checkin_{user_id}_{datetime.now().strftime('%H%M%S')}.jpg"
        fp = os.path.join(UPLOAD_FOLDER, fn); cv2.imwrite(fp, frame)
        
        try:
            emp = db.session.get(Employee, user_id)
            if face_recognition and emp.face_encoding:
                clean = emp.face_encoding.replace('[', '').replace(']', '').replace('\n', '')
                known = np.array([float(x.strip()) for x in clean.split(",") if x.strip()])
                curr = face_recognition.face_encodings(face_recognition.load_image_file(fp))
                if not curr or not face_recognition.compare_faces([known], curr[0], tolerance=0.6)[0]:
                    return render_template_string('<script>alert("❌ الوجه غير مطابق!"); window.location.href="/emp_dashboard";</script>')
            
            db.session.add(Attendance(user_id=user_id, date=datetime.now().date(), time=datetime.now().time().replace(microsecond=0), status="تم التحقق", photo=fn))
            db.session.commit(); return redirect(url_for('employee_dashboard', msg="تم تسجيل الحضور بنجاح"))
        except: return "خطأ في التسجيل"

    @app.route('/check_out_python', methods=['POST'])
    def check_out():
        now = datetime.now()
        att = Attendance.query.filter_by(user_id=session.get('user_id'), date=now.date()).first()
        if att:
            att.check_out_time = now.time().replace(microsecond=0)
            start_dt = datetime.combine(now.date(), att.time)
            att.work_hours = round((now - start_dt).total_seconds() / 3600, 2)
            db.session.commit()
            return redirect(url_for('employee_dashboard', msg="تم تسجيل الانصراف وحساب الساعات"))
        return redirect(url_for('employee_dashboard'))

    @app.route('/request_leave', methods=['GET', 'POST'])
    @app.route('/leave_request', methods=['GET', 'POST'])
    def request_leave():
        if not session.get('logged_in'): return redirect(url_for('login'))
        
        dash_link = '/dashboard' if session.get('role') == 'Admin' else '/emp_dashboard'
        
        if request.method == 'POST':
            try:
                start = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
                end = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
                db.session.add(LeaveRequest(user_id=session['user_id'], leave_type=request.form.get('leave_type'), start_date=start, end_date=end, reason=request.form.get('reason'), status="Pending"))
                db.session.commit()
                if session.get('role') == 'Admin':
                    return render_template_string(f'<script>alert("✅ تم إرسال الطلب"); window.location.href="{dash_link}";</script>')
                return redirect(url_for('employee_dashboard', msg="تم إرسال طلب الإجازة"))
            except: return "خطأ في البيانات"
            
        html = render_template('request_leave.html')
        return html.replace('href="/dashboard"', f'href="{dash_link}"').replace('href="/"', f'href="{dash_link}"').replace('href="/emp_dashboard"', f'href="{dash_link}"')

    @app.route('/my_payslips')
    def my_payslips():
        if not session.get('logged_in'): return redirect(url_for('login'))
        payslips = PayrollHistory.query.filter_by(user_id=session['user_id']).all()
        html = render_template('my_payslips.html', payslips=payslips)
        
        dash_link = '/dashboard' if session.get('role') == 'Admin' else '/emp_dashboard'
        return html.replace('href="/dashboard"', f'href="{dash_link}"').replace('href="/"', f'href="{dash_link}"').replace('href="/emp_dashboard"', f'href="{dash_link}"')

    @app.route('/company_feed', methods=['GET', 'POST'])
    @app.route('/admin/company_feed', methods=['GET', 'POST'])
    def company_feed():
        if not session.get('logged_in'): return redirect(url_for('login'))
        if request.method == 'POST':
            db.session.add(AnnouncementComment(announcement_id=request.form.get('announcement_id'), user_name=session['user_name'], comment=request.form.get('comment')))
            db.session.commit()
            
        html = render_template('company_feed.html', news=Announcement.query.all(), comments=AnnouncementComment.query.all())
        
        dash_link = '/dashboard' if session.get('role') == 'Admin' else '/emp_dashboard'
        return html.replace('href="/dashboard"', f'href="{dash_link}"').replace('href="/"', f'href="{dash_link}"').replace('href="/emp_dashboard"', f'href="{dash_link}"')