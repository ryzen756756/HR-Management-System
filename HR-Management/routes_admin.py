from flask import redirect, render_template, request, session, url_for, flash, abort, render_template_string
import os
from datetime import date, datetime
import numpy as np
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from utils import month_range, get_face_encoding
from routes_auth import RESET_REQUESTS

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
        
        if current_user and current_user.username != 'admin':
            my_salary_btn = f'''
            <div style="position: fixed; bottom: 20px; left: 20px; z-index: 9999;">
                <a href="/my_payslips" style="background: #17a2b8; color: white; padding: 12px 20px; text-decoration: none; border-radius: 50px; font-weight: bold; font-family: sans-serif; box-shadow: 0px 4px 10px rgba(0,0,0,0.2);">💰 عرض مرتبي الشخصي</a>
            </div>
            '''
            if '</body>' in html_content:
                html_content = html_content.replace('</body>', my_salary_btn + '</body>')
            else:
                html_content += my_salary_btn
                
        if RESET_REQUESTS:
            bar = f'''
            <div style="background:#ff4d4d; color:white; padding:15px; text-align:center; font-weight:bold; position:relative; z-index:9999; direction:rtl;">
                ⚠️ يوجد {len(RESET_REQUESTS)} طلبات لتغيير كلمة المرور! 
                <a href="/admin/reset_notifications" style="color:yellow; margin-left:10px; text-decoration:underline;">[ عرض الطلبات ]</a>
            </div>
            '''
            return bar + html_content
        return html_content

    @app.route('/admin/reset_notifications')
    def reset_notifications():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        waiting = Employee.query.filter(Employee.username.in_(RESET_REQUESTS)).all()
        return render_template_string('''
            <div dir="rtl" style="font-family:sans-serif; text-align:center; padding:40px; background:#f4f7f6; min-height:100vh;">
                <div style="background:white; display:inline-block; padding:30px; border-radius:15px; box-shadow:0 5px 15px rgba(0,0,0,0.1); width:80%;">
                    <h2 style="color:#6f42c1;">🛠️ طلبات تغيير كلمة المرور</h2>
                    <table style="width:100%; border-collapse:collapse; background:white; margin-top:20px;">
                        <thead>
                            <tr style="background:#6f42c1; color:white;">
                                <th style="padding:15px; border:1px solid #ddd;">اسم الموظف</th>
                                <th style="padding:15px; border:1px solid #ddd;">كلمة المرور الجديدة</th>
                                <th style="padding:15px; border:1px solid #ddd;">إجراء</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for emp in employees %}
                            <tr>
                                <form action="/admin/confirm_reset/{{ emp.username }}" method="POST">
                                    <td style="padding:15px; border:1px solid #ddd; font-weight:bold;">{{ emp.name }}</td>
                                    <td style="padding:15px; border:1px solid #ddd;">
                                        <input type="text" name="new_password" required style="padding:10px; width:90%; border-radius:5px; border:1px solid #ccc; text-align:center;">
                                    </td>
                                    <td style="padding:15px; border:1px solid #ddd;">
                                        <button type="submit" style="background:#28a745; color:white; border:none; padding:10px 25px; border-radius:5px; cursor:pointer;">تحديث ✅</button>
                                    </td>
                                </form>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                    {% if not employees %} <p style="margin-top:20px;">لا توجد طلبات معلقة.</p> {% endif %}
                    <br><a href="/dashboard" style="text-decoration:none; color:#6f42c1; font-weight:bold;">🔙 العودة للوحة التحكم</a>
                </div>
            </div>
        ''', employees=waiting)

    @app.route('/admin/confirm_reset/<username>', methods=['POST'])
    def confirm_reset(username):
        user = Employee.query.filter_by(username=username).first()
        if user:
            user.password = request.form.get('new_password'); db.session.commit()
            if username in RESET_REQUESTS: RESET_REQUESTS.remove(username)
        return redirect(url_for('reset_notifications'))

    @app.route('/employees')
    def employees():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        all_emp = Employee.query.order_by(Employee.id).all()
        return render_template('employees.html', employees=all_emp)

    @app.route('/add_employee', methods=['GET', 'POST'])
    def add_employee():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        if request.method == 'POST':
            name, username, password = request.form.get('name'), request.form.get('username'), request.form.get('password')
            dept, role, hourly_rate = request.form.get('dept'), request.form.get('role'), request.form.get('hourly_rate') or 0
            photo = request.files.get('photo')
            
            if not photo or photo.filename == '': 
                return '''<script>alert("يجب رفع صورة الموظف لتعريف البصمة!"); window.history.back();</script>'''
                
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{photo.filename}"
            filepath = os.path.join(UPLOAD_FOLDER, filename); photo.save(filepath)
            encoding = get_face_encoding(filepath)
            
            if encoding is None:
                if os.path.exists(filepath): os.remove(filepath)
                return '''<script>alert("لم يتم التعرف على الوجه في الصورة!"); window.history.back();</script>'''
                
            encoding_str = ",".join(str(x) for x in encoding.tolist()) if encoding is not None else None
            
            try:
                db.session.add(Employee(name=name, username=username, password=password, dept=dept, role=role, photo=filename, face_encoding=encoding_str, hourly_rate=float(hourly_rate)))
                db.session.commit()
                return redirect(url_for('employees'))
            except IntegrityError:
                db.session.rollback()
                return '''<script>alert("اسم المستخدم موجود بالفعل!"); window.history.back();</script>'''
            except Exception as e:
                db.session.rollback()
                return f'''<script>alert("حدث خطأ: {str(e)}"); window.history.back();</script>'''
                
        return render_template('add_employee.html')

    @app.route('/delete_employee/<int:id>', methods=['GET', 'POST'])
    @app.route('/admin/delete_employee/<int:id>', methods=['GET', 'POST'])
    @app.route('/delete/<int:id>', methods=['GET', 'POST'])
    def delete_employee(id):
        if session.get('role') != 'Admin': abort(403)
        emp = db.session.get(Employee, id)
        
        if emp and emp.id == session.get('user_id'):
            return '''<script>alert("لا يمكنك حذف حسابك الشخصي!"); window.history.back();</script>'''
            
        if emp and emp.username == 'admin':
            return '''<script>alert("لا يمكن حذف المدير الأساسي للنظام."); window.history.back();</script>'''

        if emp and emp.photo:
            photo_path = os.path.join(UPLOAD_FOLDER, emp.photo)
            if os.path.exists(photo_path):
                try: os.remove(photo_path)
                except: pass
                
        if emp: 
            db.session.delete(emp); db.session.commit()
            
        return redirect(url_for('employees'))

    @app.route('/set_zone', methods=['GET', 'POST'])
    def set_zone():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        if request.method == 'POST':
            lat, lng, radius = request.form.get('lat'), request.form.get('lng'), request.form.get('radius')
            zone = db.session.get(Settings, 1) or Settings(id=1)
            zone.lat, zone.lng, zone.radius = float(lat), float(lng), int(radius)
            db.session.add(zone); db.session.commit()
            return redirect(url_for('set_zone'))
        return render_template('set_zone.html', zone=db.session.get(Settings, 1))

    @app.route('/attendance')
    @app.route('/admin_attendance')
    @app.route('/admin/attendance_logs')
    def attendance_logs():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        records = db.session.query(Attendance, Employee).join(Employee, Attendance.user_id == Employee.id).order_by(Attendance.date.desc(), Attendance.time.desc()).all()
        
        logs_data = []
        for att, emp in records:
            logs_data.append({
                "name": emp.name,
                "date": att.date,
                "time": att.time,
                "check_out_time": att.check_out_time,
                "work_hours": att.work_hours,
                "status": att.status,
                "photo": att.photo
            })
            
        return render_template('admin_attendance.html', logs=logs_data)

    @app.route('/add_announcement', methods=['GET', 'POST'])
    @app.route('/admin_announcements', methods=['GET', 'POST'])
    @app.route('/admin/announcements', methods=['GET', 'POST'])
    def add_announcement():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        if request.method == 'POST':
            db.session.add(Announcement(title=request.form.get('title'), message=request.form.get('message'))); db.session.commit()
            return redirect(url_for('add_announcement'))
        all_news = Announcement.query.order_by(Announcement.created_at.desc()).all()
        original_html = render_template('admin_announcements.html', announcements=all_news, news=all_news)
        back_btn = f'''<div style="position: absolute; top: 20px; left: 20px; z-index: 9999;"><a href="{url_for('dashboard')}" style="background: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">🔙 العودة للرئيسية</a></div>'''
        return original_html + back_btn

    @app.route('/delete_announcement/<int:id>', methods=['GET', 'POST'])
    @app.route('/admin/delete_news/<int:id>', methods=['GET', 'POST'])
    def delete_announcement(id):
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        try:
            announcement = db.session.get(Announcement, id)
            if announcement: 
                AnnouncementComment.query.filter_by(announcement_id=id).delete()
                db.session.delete(announcement); db.session.commit()
        except: db.session.rollback()
        return redirect(url_for('add_announcement'))

    @app.route('/admin/leaves')
    def admin_leaves():
        if not session.get('logged_in') or session.get('role') != 'Admin': return redirect(url_for('login'))
        records = db.session.query(LeaveRequest, Employee).join(Employee, LeaveRequest.user_id == Employee.id).order_by(LeaveRequest.request_date.desc()).all()
        
        requests_data = []
        for req, emp in records:
            requests_data.append({
                "id": req.id,
                "name": emp.name,
                "leave_type": req.leave_type,
                "start_date": req.start_date,
                "end_date": req.end_date,
                "reason": req.reason,
                "status": req.status
            })
            
        original_html = render_template('admin_leaves.html', requests=requests_data)
        back_btn = f'''<div style="position: absolute; top: 20px; left: 20px; z-index: 9999;"><a href="{url_for('dashboard')}" style="background: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">🔙 العودة للرئيسية</a></div>'''
        return original_html + back_btn

    @app.route('/admin/update_leave/<int:req_id>', methods=['POST'])
    def update_leave_status(req_id):
        if not session.get('logged_in') or session.get('role') != 'Admin': abort(403)
        try:
            leave_request = db.session.get(LeaveRequest, req_id)
            if leave_request: leave_request.status = request.form.get('status'); db.session.commit()
            return redirect(url_for('admin_leaves'))
        except: db.session.rollback(); return "Error", 500

    @app.route('/admin/payroll')
    @app.route('/payroll')
    def admin_payroll():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        
        current_user = db.session.get(Employee, session.get('user_id'))
        if not current_user or current_user.username != 'admin':
            return '''<script>alert("صلاحية مرفوضة: المدير العام فقط هو من يمكنه إدارة الرواتب!"); window.history.back();</script>'''

        month_start, next_month_start = month_range()
        employees = Employee.query.filter(Employee.username != 'admin').order_by(Employee.id).all()
        salaries = []
        for emp in employees:
            total_hours = db.session.query(func.coalesce(func.sum(Attendance.work_hours), 0.0)).filter(Attendance.user_id == emp.id, Attendance.date >= month_start, Attendance.date < next_month_start).scalar()
            approved_leaves = LeaveRequest.query.filter(LeaveRequest.user_id == emp.id, LeaveRequest.status == "Approved", LeaveRequest.start_date >= month_start, LeaveRequest.start_date < next_month_start).count()
            existing = PayrollHistory.query.filter_by(user_id=emp.id, month=datetime.now().strftime('%Y-%m')).first()
            salaries.append({'id': emp.id, 'name': emp.name, 'hourly_rate': emp.hourly_rate, 'total_hours': total_hours, 'approved_leaves': approved_leaves, 'expected_salary': total_hours * emp.hourly_rate, 'is_issued': True if existing else False})
        
        original_html = render_template('payroll.html', salaries=salaries)
        logs_btn = f'<a href="{url_for("admin_payroll_logs")}" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px;">عرض السجلات الصادرة 📋</a>'
        if 'العودة للرئيسية' in original_html: return original_html.replace('العودة للرئيسية</a>', 'العودة للرئيسية</a> ' + logs_btn)
        return original_html + logs_btn

    @app.route('/admin/save_salary', methods=['POST'])
    def save_salary():
        if session.get('role') != 'Admin': return '{"status": "error", "message": "غير مصرح لك"}', 403
        
        current_user = db.session.get(Employee, session.get('user_id'))
        if not current_user or current_user.username != 'admin':
            return '{"status": "error", "message": "المدير العام فقط هو من يحدد الرواتب!"}', 403

        data = request.get_json(silent=True) or request.form
        emp_id, month = data.get('emp_id'), datetime.now().strftime('%Y-%m')
        try:
            existing = PayrollHistory.query.filter_by(user_id=int(emp_id), month=month).first()
            if existing:
                existing.total_hours = float(data.get('total_hours', 0))
                existing.hourly_rate = float(data.get('hourly_rate', 0))
                existing.basic_salary = float(data.get('basic', 0))
                existing.bonus = float(data.get('bonus', 0))
                existing.deduction = float(data.get('deduction', 0))
                existing.net_salary = float(data.get('net', 0))
                msg = "تم التحديث بنجاح"
            else:
                db.session.add(PayrollHistory(user_id=int(emp_id), month=month, total_hours=float(data.get('total_hours', 0)), hourly_rate=float(data.get('hourly_rate', 0)), basic_salary=float(data.get('basic', 0)), bonus=float(data.get('bonus', 0)), deduction=float(data.get('deduction', 0)), net_salary=float(data.get('net', 0))))
                msg = "تم الإصدار بنجاح"
            db.session.commit()
            return '{"status": "success", "message": "' + msg + '"}'
        except Exception as e:
            db.session.rollback()
            return '{"status": "error", "message": "حدث خطأ أثناء حفظ المرتب"}'

    @app.route('/admin/payroll_logs')
    def admin_payroll_logs():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        
        current_user = db.session.get(Employee, session.get('user_id'))
        if not current_user or current_user.username != 'admin':
            return '''<script>alert("صلاحية مرفوضة: المدير العام فقط هو من يمكنه عرض السجلات!"); window.history.back();</script>'''

        history = db.session.query(PayrollHistory, Employee).join(Employee, PayrollHistory.user_id == Employee.id).order_by(PayrollHistory.issue_date.desc()).all()
        html_content = """
        <!DOCTYPE html>
        <html lang="ar" dir="rtl"><head><meta charset="UTF-8"><title>سجل الرواتب الصادرة</title></head>
        <body style="font-family: Arial; text-align: center; background: #f4f4f4; padding: 20px;">
            <div style="background: white; padding: 20px; border-radius: 10px; max-width: 800px; margin: auto; box-shadow: 0 0 10px rgba(0,0,0,0.1);">
                <h2>📋 سجل الرواتب الصادرة</h2>
                <table border="1" style="width: 100%; border-collapse: collapse; margin-top: 20px; border: 1px solid #ddd;">
                    <tr style="background: #333; color: white;"><th style="padding: 10px;">الموظف</th><th>الشهر</th><th>الصافي</th><th>تاريخ الإصدار</th><th>إجراء</th></tr>
                    {% for rec, emp in history %}
                    <tr><td style="padding: 10px;">{{ emp.name }}</td><td>{{ rec.month }}</td><td>{{ rec.net_salary }} ج</td><td>{{ rec.issue_date.strftime('%Y-%m-%d') }}</td><td><a href="/admin/delete_payroll/{{ rec.id }}" style="color: red; text-decoration: none; font-weight: bold;" onclick="return confirm('حذف؟')">🗑️ حذف</a></td></tr>
                    {% endfor %}
                </table><br><a href="/admin/payroll" style="background: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">العودة</a>
            </div>
        </body></html>"""
        return render_template_string(html_content, history=history)

    @app.route('/admin/delete_payroll/<int:pid>')
    def delete_payroll(pid):
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        
        current_user = db.session.get(Employee, session.get('user_id'))
        if not current_user or current_user.username != 'admin':
            return '''<script>alert("صلاحية مرفوضة: المدير العام فقط هو من يمكنه الحذف!"); window.history.back();</script>'''

        record = db.session.get(PayrollHistory, pid)
        if record: db.session.delete(record); db.session.commit()
        return redirect(url_for('admin_payroll_logs'))