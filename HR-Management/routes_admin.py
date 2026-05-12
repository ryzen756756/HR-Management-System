from flask import redirect, render_template, request, session, url_for, abort, render_template_string, Response
import os, cv2, re
from datetime import date, datetime
import numpy as np
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from utils import month_range, get_face_encoding
from routes_auth import RESET_REQUESTS

try:
    import face_recognition
except ImportError:
    face_recognition = None

def setup_admin_routes(app, db, Employee, Attendance, Settings, LeaveRequest, PayrollHistory, Announcement, AnnouncementComment, UPLOAD_FOLDER):
    
    @app.route('/dashboard')
    def dashboard():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        today = date.today()
        total = Employee.query.filter(Employee.username != 'admin').count()
        present = db.session.query(Attendance).join(Employee).filter(Attendance.date == today, Employee.username != 'admin').count()
        absent = max(total - present, 0)
        
        html_content = render_template('dashboard.html', total=total, present=present, absent=absent, today=today.isoformat())
        current_user = db.session.get(Employee, session.get('user_id'))
        
        if current_user:
            if current_user.username != 'admin':
                att = Attendance.query.filter_by(user_id=current_user.id, date=today).first()
                att_btn = ""
                if not att:
                    att_btn = '<form action="/admin/check_in" method="POST" style="margin-bottom:10px;"><button type="submit" style="background:#28a745; color:white; padding:12px 20px; border-radius:50px; font-weight:bold; border:none; cursor:pointer; width:100%; box-shadow:0 4px 10px rgba(0,0,0,0.2);">📷 حضور بالكاميرا (IT)</button></form>'
                elif not att.check_out_time:
                    att_btn = '<form action="/admin/check_out" method="POST" style="margin-bottom:10px;"><button type="submit" style="background:#dc3545; color:white; padding:12px 20px; border-radius:50px; font-weight:bold; border:none; cursor:pointer; width:100%; box-shadow:0 4px 10px rgba(0,0,0,0.2);">🚪 تسجيل انصراف (IT)</button></form>'
                else:
                    att_btn = '<div style="background:#f8f9fa; color:#6c757d; padding:12px 20px; border-radius:50px; text-align:center; font-weight:bold; margin-bottom:10px; border:1px dashed #ccc;">✨ الوردية مكتملة</div>'

                payslip_btn = "<a href='/my_payslips' style='background:#17a2b8; color:white; padding:12px 20px; border-radius:50px; text-decoration:none; font-weight:bold; display:block; text-align:center; box-shadow:0 4px 10px rgba(0,0,0,0.2);'>💰 عرض مرتبي</a>"
                it_menu = f'<div style="position:fixed; bottom:20px; left:20px; z-index:9999; display:flex; flex-direction:column;">{att_btn}{payslip_btn}</div>'
                html_content = html_content.replace('</body>', it_menu + '</body>') if '</body>' in html_content else html_content + it_menu
                
                hide_payroll_css = '<style>a[href="/admin/payroll"], a[href="/payroll"] { display: none !important; }</style>'
                html_content = html_content.replace('</head>', hide_payroll_css + '</head>') if '</head>' in html_content else html_content + hide_payroll_css
            
            all_wait = Employee.query.filter(Employee.username.in_(RESET_REQUESTS)).all()
            relevant = [u for u in all_wait if (current_user.username == 'admin' and u.role == 'Admin' and u.username != 'admin') or (current_user.username != 'admin' and u.role != 'Admin')]
            if relevant:
                msg = f"يوجد {len(relevant)} طلبات"
                bar = f'<div style="background:#ff4d4d; color:white; padding:15px; text-align:center; font-weight:bold; width:100%; position:relative; z-index: 9998; direction:rtl; box-sizing: border-box;">⚠️ {msg}! <a href="/admin/reset_notifications" style="color:yellow; font-weight:bold;">[ عرض ومعالجة الطلبات ]</a></div>'
                html_content = html_content.replace('<body>', '<body>' + bar) if '<body>' in html_content else bar + html_content
            
            if request.args.get('msg'):
                msg_alert = f'<script>alert("{request.args.get("msg")}");</script>'
                html_content = html_content.replace('</body>', msg_alert + '</body>')

        return html_content

    @app.route('/admin/check_in', methods=['POST'])
    def admin_check_in():
        user_id = session.get('user_id')
        cap = cv2.VideoCapture(0)
        if not cap.isOpened(): return redirect(url_for('dashboard', msg="❌ خطأ في الكاميرا"))
        for _ in range(5): cap.read()
        ret, frame = cap.read(); cap.release(); cv2.destroyAllWindows()
        if not ret: return redirect(url_for('dashboard', msg="❌ فشل التقاط الصورة"))
        
        fn = f"checkin_{user_id}_{datetime.now().strftime('%H%M%S')}.jpg"
        fp = os.path.join(UPLOAD_FOLDER, fn); cv2.imwrite(fp, frame)
        
        try:
            emp = db.session.get(Employee, user_id)
            if face_recognition and emp.face_encoding:
                clean = emp.face_encoding.replace('[', '').replace(']', '').replace('\n', '')
                known = np.array([float(x.strip()) for x in clean.split(",") if x.strip()])
                curr = face_recognition.face_encodings(face_recognition.load_image_file(fp))
                if not curr or not face_recognition.compare_faces([known], curr[0], tolerance=0.6)[0]:
                    return redirect(url_for('dashboard', msg="❌ الوجه غير مطابق!"))
            
            db.session.add(Attendance(user_id=user_id, date=datetime.now().date(), time=datetime.now().time().replace(microsecond=0), status="تم التحقق", photo=fn))
            db.session.commit(); return redirect(url_for('dashboard', msg="✅ تم تسجيل حضور الـ IT بنجاح"))
        except: return redirect(url_for('dashboard', msg="❌ خطأ في التسجيل"))

    @app.route('/admin/check_out', methods=['POST'])
    def admin_check_out():
        now = datetime.now()
        att = Attendance.query.filter_by(user_id=session.get('user_id'), date=now.date()).first()
        if att:
            att.check_out_time = now.time().replace(microsecond=0)
            start_dt = datetime.combine(now.date(), att.time)
            att.work_hours = round((now - start_dt).total_seconds() / 3600, 2)
            db.session.commit()
            return redirect(url_for('dashboard', msg="✅ تم تسجيل الانصراف وحساب الساعات"))
        return redirect(url_for('dashboard'))

    @app.route('/employees')
    @app.route('/admin/employees')
    def employees():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        all_emp = Employee.query.order_by(Employee.id).all()
        html_content = render_template('employees.html', employees=all_emp)
        
        for emp in all_emp:
            del_btn = f'<br><a href="/admin/delete_employee/{emp.id}" style="color:red; font-size:11px; font-weight:bold; text-decoration:none;" onclick="return confirm(\'تأكيد الحذف النهائي؟\')">[حذف 🗑️]</a>'
            html_content = html_content.replace(f'<td>#{emp.id}</td>', f'<td>#{emp.id}{del_btn}</td>')

            role_ar = '<span style="background:#007bff; color:white; padding:4px 10px; border-radius:5px; font-size:12px; font-weight:bold;">مدير</span>' if emp.role == 'Admin' else '<span style="background:#28a745; color:white; padding:4px 10px; border-radius:5px; font-size:12px; font-weight:bold;">موظف</span>'
            html_content = html_content.replace(f'<td>{emp.role}</td>', f'<td>{role_ar}</td>')
            if emp.dept == 'General': html_content = html_content.replace('<td>General</td>', '<td>عام</td>')

        fix_table_script = '''<style>table th:nth-child(n+5), table td:nth-child(n+5) { display: none !important; }</style><script>document.addEventListener("DOMContentLoaded", function() { var ths = document.querySelectorAll("table th"); if(ths.length >= 4) { ths[0].innerText = "ID"; ths[1].innerText = "الاسم"; ths[2].innerText = "القسم"; ths[3].innerText = "الصلاحية"; } });</script>'''
        return html_content.replace('</head>', fix_table_script + '</head>') if '</head>' in html_content else html_content + fix_table_script

    @app.route('/admin/delete_employee/<int:id>')
    def delete_employee(id):
        if session.get('role') != 'Admin': abort(403)
        current_uid = session.get('user_id')
        current_user = db.session.get(Employee, current_uid)
        target = db.session.get(Employee, id)
        
        if not target: return redirect(url_for('employees'))
        if target.id == current_uid:
            return '<script>alert("❌ لا يمكنك حذف نفسك!"); window.history.back();</script>'
        if current_user.username != 'admin' and (target.username == 'admin' or target.role == 'Admin'):
            return '<script>alert("❌ لا تملك صلاحية لحذف حسابات الإدارة!"); window.history.back();</script>'

        if target.photo:
            p = os.path.join(UPLOAD_FOLDER, target.photo)
            if os.path.exists(p): os.remove(p)
        db.session.delete(target); db.session.commit()
        return redirect(url_for('employees'))

    @app.route('/add_employee', methods=['GET', 'POST'])
    def add_employee():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        if request.method == 'POST':
            name, u, p, r = request.form.get('name'), request.form.get('username'), request.form.get('password'), request.form.get('role')
            photo = request.files.get('photo')
            if not photo: return 'يرجى رفع صورة لتعريف البصمة'
            fn = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{photo.filename}"
            fp = os.path.join(UPLOAD_FOLDER, fn); photo.save(fp)
            enc = get_face_encoding(fp)
            e_str = ",".join(str(x) for x in enc.tolist()) if enc is not None else ""
            try:
                db.session.add(Employee(name=name, username=u, password=p, role=r, photo=fn, face_encoding=e_str, hourly_rate=100.0, dept="عام"))
                db.session.commit(); return redirect(url_for('employees'))
            except IntegrityError:
                db.session.rollback(); return 'اسم المستخدم مكرر'
        return render_template('add_employee.html')

    @app.route('/admin/attendance_logs')
    @app.route('/attendance')
    def attendance_logs():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        records = db.session.query(Attendance, Employee).join(Employee, Attendance.user_id == Employee.id).order_by(Attendance.date.desc(), Attendance.time.desc()).all()
        logs_data = [{"name": e.name, "date": a.date, "time": a.time, "check_out_time": a.check_out_time, "work_hours": a.work_hours, "status": a.status, "photo": a.photo} for a, e in records]
        
        html_content = render_template('admin_attendance.html', logs=logs_data)
        style = '<style>table th:nth-child(6), table td:nth-child(6) { display: none !important; }</style>'
        return html_content.replace('</head>', style + '</head>') if '</head>' in html_content else html_content + style

    @app.route('/admin/payroll')
    @app.route('/payroll')
    def admin_payroll():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        current_user = db.session.get(Employee, session.get('user_id'))
        
        if current_user.username != 'admin':
            return '<script>alert("❌ عذراً، إدارة المرتبات مخصصة للمدير العام فقط!"); window.location.href="/dashboard";</script>'

        start, end = month_range()
        emps = Employee.query.filter(Employee.username != 'admin').all()
        salaries = []
        for e in emps:
            h = db.session.query(func.coalesce(func.sum(Attendance.work_hours), 0.0)).filter(Attendance.user_id == e.id, Attendance.date >= start, Attendance.date < end).scalar()
            lv = LeaveRequest.query.filter(LeaveRequest.user_id == e.id, LeaveRequest.status == "Approved").count()
            ex = PayrollHistory.query.filter_by(user_id=e.id, month=datetime.now().strftime('%Y-%m')).first()
            salaries.append({
                'id': e.id, 'name': e.name, 'hourly_rate': e.hourly_rate, 'total_hours': h, 
                'approved_leaves': lv, 'expected_salary': h * e.hourly_rate, 
                'is_issued': True if ex else False, 'pid': ex.id if ex else 0
            })
            
        html_content = render_template('payroll.html', salaries=salaries)
        style = '<style>table th:nth-child(4), table td:nth-child(4) { display: none !important; }</style>'
        
        js_data = ",".join([f"{{id: {s['id']}, pid: {s['pid']}, issued: {'true' if s['is_issued'] else 'false'}}}" for s in salaries])
        script = f"""
        <script>
        document.addEventListener('DOMContentLoaded', function() {{
            let issued_data = [{js_data}];
            let rows = document.querySelectorAll('table tbody tr, table tr');
            let data_idx = 0;
            for(let i=0; i<rows.length; i++) {{
                if(rows[i].querySelector('th')) continue;
                if(data_idx < issued_data.length) {{
                    let s = issued_data[data_idx];
                    if(s.issued) {{
                        let action_td = rows[i].querySelector('td:last-child');
                        if(action_td) {{
                            action_td.innerHTML = '<a href="/admin/delete_payroll/' + s.pid + '" style="background:#dc3545; color:white; padding:8px 15px; border-radius:5px; text-decoration:none; font-weight:bold; font-size:14px; display:inline-block; border:none; cursor:pointer; box-shadow:0 2px 5px rgba(0,0,0,0.2);">حذف 🗑️</a>';
                        }}
                    }}
                    data_idx++;
                }}
            }}
        }});
        
        let origXHR = window.XMLHttpRequest.prototype.open;
        window.XMLHttpRequest.prototype.open = function() {{
            this.addEventListener('load', function() {{
                if(this.responseURL.includes('/admin/save_salary') && this.status === 200) {{
                    setTimeout(() => window.location.reload(), 1000);
                }}
            }});
            return origXHR.apply(this, arguments);
        }};
        let origFetch = window.fetch;
        window.fetch = async function() {{
            let res = await origFetch.apply(this, arguments);
            if(res.url.includes('/admin/save_salary') && res.ok) {{
                setTimeout(() => window.location.reload(), 1000);
            }}
            return res;
        }};
        </script>
        """
        final_html = html_content.replace('</head>', style + '</head>') if '</head>' in html_content else html_content + style
        return final_html + script

    @app.route('/admin/save_salary', methods=['POST'])
    def save_salary():
        current_user = db.session.get(Employee, session.get('user_id'))
        if current_user.username != 'admin':
            return Response('{"status":"error", "message":"غير مصرح لك"}', 403, mimetype='application/json')
            
        data = request.get_json(silent=True) or request.form
        eid, month = data.get('emp_id'), datetime.now().strftime('%Y-%m')
        try:
            def parse_val(v):
                nums = re.findall(r"[-+]?\d*\.\d+|\d+", str(v)) if v else []
                return float(nums[0]) if nums else 0.0

            total_h = parse_val(data.get('total_hours'))
            h_rate = parse_val(data.get('hourly_rate'))
            basic = parse_val(data.get('basic'))
            bonus = parse_val(data.get('bonus'))
            deduction = parse_val(data.get('deduction'))
            net = parse_val(data.get('net'))

            ex = PayrollHistory.query.filter_by(user_id=int(eid), month=month).first()
            if not ex: 
                db.session.add(PayrollHistory(user_id=int(eid), month=month, total_hours=total_h, hourly_rate=h_rate, basic_salary=basic, bonus=bonus, deduction=deduction, net_salary=net))
            db.session.commit()
            return Response('{"status":"success", "message":"تم إصدار المرتب بنجاح"}', 200, mimetype='application/json')
        except Exception as e: 
            return Response(f'{{"status":"error", "message":"{str(e)}"}}', 500, mimetype='application/json')

    @app.route('/admin/delete_payroll/<int:pid>')
    def delete_payroll(pid):
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        current_user = db.session.get(Employee, session.get('user_id'))
        if current_user.username != 'admin': abort(403)
        
        record = db.session.get(PayrollHistory, pid)
        if record:
            db.session.delete(record)
            db.session.commit()
        return redirect(url_for('admin_payroll'))

    @app.route('/set_zone', methods=['GET', 'POST'])
    @app.route('/admin/set_zone', methods=['GET', 'POST'])
    def set_zone():
        if request.method == 'POST':
            z = db.session.get(Settings, 1) or Settings(id=1)
            z.lat, z.lng, z.radius = float(request.form.get('lat')), float(request.form.get('lng')), int(request.form.get('radius'))
            db.session.add(z); db.session.commit()
            return redirect(url_for('set_zone'))
        return render_template('set_zone.html', zone=db.session.get(Settings, 1))

    @app.route('/admin/leaves')
    @app.route('/leaves')
    def admin_leaves():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        records = db.session.query(LeaveRequest, Employee).join(Employee, LeaveRequest.user_id == Employee.id).all()
        leaves_data = [{"id": r.id, "name": e.name, "leave_type": r.leave_type, "start_date": r.start_date, "end_date": r.end_date, "reason": r.reason, "status": r.status} for r, e in records]
        return render_template('admin_leaves.html', requests=leaves_data)

    @app.route('/admin/update_leave/<int:req_id>', methods=['POST'])
    def update_leave_status(req_id):
        if session.get('role') != 'Admin': abort(403)
        leave = db.session.get(LeaveRequest, req_id)
        if leave: leave.status = request.form.get('status'); db.session.commit()
        return redirect(url_for('admin_leaves'))

    @app.route('/admin/announcements', methods=['GET', 'POST'])
    def add_announcement():
        if request.method == 'POST':
            db.session.add(Announcement(title=request.form.get('title'), message=request.form.get('message'))); db.session.commit()
            return redirect(url_for('add_announcement'))
        return render_template('admin_announcements.html', news=Announcement.query.all())

    @app.route('/admin/delete_news/<int:id>')
    def delete_announcement(id):
        ann = db.session.get(Announcement, id)
        if ann: db.session.delete(ann); db.session.commit()
        return redirect(url_for('add_announcement'))

    @app.route('/admin/reset_notifications')
    def reset_notifications():
        all_waiting = Employee.query.filter(Employee.username.in_(RESET_REQUESTS)).all()
        return render_template_string('''<div dir="rtl" style="text-align:center; padding:50px;"><h2>🛠️ طلبات استعادة الحساب</h2><table border="1" style="margin:auto; width:60%;"><tr><th>الاسم</th><th>إجراء</th></tr>{% for emp in employees %}<tr><td>{{ emp.name }}</td><td><form action="/admin/confirm_reset/{{ emp.username }}" method="POST"><input type="text" name="new_password" required><button type="submit" style="background:#28a745; color:white; border:none; padding:5px 10px; border-radius:3px; cursor:pointer;">تحديث ✅</button></form></td></tr>{% endfor %}</table><br><a href="/dashboard" style="text-decoration:none; background:#6c757d; color:white; padding:10px 20px; border-radius:5px;">🔙 رجوع للرئيسية</a></div>''', employees=all_waiting)

    @app.route('/admin/confirm_reset/<username>', methods=['POST'])
    def confirm_reset(username):
        user = Employee.query.filter_by(username=username).first()
        if user:
            user.password = request.form.get('new_password'); db.session.commit()
            if username in RESET_REQUESTS: RESET_REQUESTS.remove(username)
        return redirect(url_for('reset_notifications'))