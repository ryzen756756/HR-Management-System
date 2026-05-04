from flask import redirect, render_template, request, session, url_for, jsonify, flash, abort, render_template_string
import os
from datetime import date, datetime
import json
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from utils import month_range, get_face_encoding

def setup_admin_routes(app, db, Employee, Attendance, Settings, LeaveRequest, PayrollHistory, Announcement, AnnouncementComment, UPLOAD_FOLDER):
    @app.route('/dashboard')
    def dashboard():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        today = date.today()
        total = Employee.query.filter(Employee.role != 'Admin').count()
        present = db.session.query(Attendance).join(Employee).filter(Attendance.date == today, Employee.role != 'Admin').count()
        absent = max(total - present, 0)
        return render_template('dashboard.html', total=total, present=present, absent=absent, today=today.isoformat())

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
            if not photo or photo.filename == '': return "يجب رفع صورة الموظف لتعريف البصمة ❌"
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{photo.filename}"
            filepath = os.path.join(UPLOAD_FOLDER, filename); photo.save(filepath)
            encoding = get_face_encoding(filepath)
            if get_face_encoding.__module__ != 'utils' and encoding is None:
                if os.path.exists(filepath): os.remove(filepath)
                return "لم يتم التعرف على الوجه في الصورة. ❌"
            try:
                db.session.add(Employee(name=name, username=username, password=password, dept=dept, role=role, photo=filename, face_encoding=json.dumps(encoding.tolist()) if encoding is not None else None, hourly_rate=float(hourly_rate)))
                db.session.commit(); return redirect(url_for('employees'))
            except IntegrityError:
                db.session.rollback(); return "اسم المستخدم هذا موجود مسبقاً! ❌"
            except Exception as e:
                db.session.rollback(); return f"حدث خطأ غير متوقع: {str(e)}"
        return render_template('add_employee.html')

    @app.route('/delete_employee/<int:id>', methods=['GET', 'POST'])
    @app.route('/admin/delete_employee/<int:id>', methods=['GET', 'POST'])
    @app.route('/delete/<int:id>', methods=['GET', 'POST'])
    def delete_employee(id):
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        emp = db.session.get(Employee, id)
        if emp and emp.photo:
            photo_path = os.path.join(UPLOAD_FOLDER, emp.photo)
            if os.path.exists(photo_path):
                try: os.remove(photo_path)
                except: pass
        if emp: db.session.delete(emp); db.session.commit()
        return redirect(url_for('employees'))

    @app.route('/set_zone', methods=['GET', 'POST'])
    def set_zone():
        if session.get('role') != 'Admin': flash("❌ غير مسموح", "danger"); return redirect(url_for('login'))
        try:
            if request.method == 'POST':
                lat, lng, radius = request.form.get('lat'), request.form.get('lng'), request.form.get('radius')
                if not lat or not lng or not radius: flash("❌ كل الحقول مطلوبة", "danger"); return redirect(url_for('set_zone'))
                zone = db.session.get(Settings, 1) or Settings(id=1)
                zone.lat, zone.lng, zone.radius = float(lat), float(lng), int(radius)
                db.session.add(zone); db.session.commit()
                flash("✅ تم حفظ النطاق بنجاح", "success"); return redirect(url_for('set_zone'))
            zone = db.session.get(Settings, 1); return render_template('set_zone.html', zone=zone)
        except Exception as e: flash("❌ إيرور بالسيرفر", "danger"); return redirect(url_for('set_zone'))

    @app.route('/attendance')
    @app.route('/admin_attendance')
    @app.route('/admin/attendance_logs')
    def attendance_logs():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        records = db.session.query(Attendance, Employee).join(Employee, Attendance.user_id == Employee.id).order_by(Attendance.date.desc(), Attendance.time.desc()).all()
        logs = [{"name": emp.name, "date": att.date, "time": att.time, "check_out_time": att.check_out_time, "work_hours": att.work_hours, "status": att.status, "lat": att.lat, "lng": att.lng, "photo": att.photo, "emp_photo": emp.photo} for att, emp in records]
        return render_template('admin_attendance.html', logs=logs)

    @app.route('/add_announcement', methods=['GET', 'POST'])
    @app.route('/admin_announcements', methods=['GET', 'POST'])
    @app.route('/admin/announcements', methods=['GET', 'POST'])
    def add_announcement():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        if request.method == 'POST':
            db.session.add(Announcement(title=request.form.get('title'), message=request.form.get('message'))); db.session.commit()
            return redirect(url_for('add_announcement'))
        all_news = Announcement.query.order_by(Announcement.created_at.desc()).all()
        return render_template('admin_announcements.html', announcements=all_news, news=all_news)

    @app.route('/delete_announcement/<int:id>', methods=['GET', 'POST'])
    @app.route('/admin/delete_news/<int:id>', methods=['GET', 'POST'])
    def delete_announcement(id):
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        try:
            announcement = db.session.get(Announcement, id)
            if announcement: AnnouncementComment.query.filter_by(announcement_id=id).delete(); db.session.delete(announcement); db.session.commit()
        except: db.session.rollback()
        return redirect(url_for('add_announcement'))

    @app.route('/admin/leaves')
    def admin_leaves():
        if not session.get('logged_in') or session.get('role') != 'Admin': return redirect(url_for('login'))
        rows = db.session.query(LeaveRequest, Employee).join(Employee, LeaveRequest.user_id == Employee.id).order_by(LeaveRequest.request_date.desc()).all()
        requests = [{"id": req.id, "leave_type": req.leave_type, "start_date": req.start_date, "end_date": req.end_date, "reason": req.reason, "status": req.status, "name": emp.name} for req, emp in rows]
        
        original_html = render_template('admin_leaves.html', requests=requests)
        
        # حقن زرار العودة للرئيسية فوق على الشمال
        back_btn = f'''
        <div style="position: absolute; top: 20px; left: 20px; z-index: 9999;">
            <a href="{url_for('dashboard')}" style="background: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-weight: bold; box-shadow: 0px 4px 6px rgba(0,0,0,0.1);">🔙 العودة للرئيسية</a>
        </div>
        '''
        return original_html + back_btn

    @app.route('/admin/update_leave/<int:req_id>', methods=['POST'])
    def update_leave_status(req_id):
        if not session.get('logged_in') or session.get('role') != 'Admin': abort(403)
        try:
            leave_request = db.session.get(LeaveRequest, req_id)
            if leave_request: leave_request.status = request.form.get('status'); db.session.commit()
            return redirect(url_for('admin_leaves'))
        except: db.session.rollback(); return " خطأ", 500

    @app.route('/admin/payroll')
    @app.route('/payroll')
    def admin_payroll():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
        month_start, next_month_start = month_range()
        employees = Employee.query.filter_by(role="Employee").order_by(Employee.id).all()
        salaries = []
        for emp in employees:
            total_hours = db.session.query(func.coalesce(func.sum(Attendance.work_hours), 0.0)).filter(Attendance.user_id == emp.id, Attendance.date >= month_start, Attendance.date < next_month_start).scalar()
            approved_leaves = LeaveRequest.query.filter(LeaveRequest.user_id == emp.id, LeaveRequest.status == "Approved", LeaveRequest.start_date >= month_start, LeaveRequest.start_date < next_month_start).count()
            existing = PayrollHistory.query.filter_by(user_id=emp.id, month=datetime.now().strftime('%Y-%m')).first()
            salaries.append({'id': emp.id, 'name': emp.name, 'hourly_rate': emp.hourly_rate, 'total_hours': total_hours, 'approved_leaves': approved_leaves, 'expected_salary': total_hours * emp.hourly_rate, 'is_issued': True if existing else False})
        original_html = render_template('payroll.html', salaries=salaries)
        logs_btn = f'<a href="{url_for("admin_payroll_logs")}" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px; font-family: sans-serif; font-size: 14px;">عرض السجلات الصادرة 📋</a>'
        if 'العودة للرئيسية' in original_html: return original_html.replace('العودة للرئيسية</a>', 'العودة للرئيسية</a> ' + logs_btn)
        return original_html + logs_btn

    @app.route('/admin/save_salary', methods=['POST'])
    def save_salary():
        if session.get('role') != 'Admin': return jsonify({"status": "error"}), 403
        data = request.get_json(silent=True) or request.form
        emp_id, month = data.get('emp_id'), datetime.now().strftime('%Y-%m')
        try:
            existing = PayrollHistory.query.filter_by(user_id=int(emp_id), month=month).first()
            if existing:
                existing.total_hours, existing.hourly_rate = float(data.get('total_hours')), float(data.get('hourly_rate'))
                existing.basic_salary, existing.bonus = float(data.get('basic')), float(data.get('bonus'))
                existing.deduction, existing.net_salary = float(data.get('deduction')), float(data.get('net'))
                msg = "✅ تم التحديث بنجاح"
            else:
                db.session.add(PayrollHistory(user_id=int(emp_id), month=month, total_hours=float(data.get('total_hours')), hourly_rate=float(data.get('hourly_rate')), basic_salary=float(data.get('basic')), bonus=float(data.get('bonus')), deduction=float(data.get('deduction')), net_salary=float(data.get('net'))))
                msg = "✅ تم الإصدار بنجاح"
            db.session.commit(); return jsonify({"status": "success", "message": msg})
        except Exception as e: db.session.rollback(); return jsonify({"status": "error", "message": str(e)})

    @app.route('/admin/payroll_logs')
    def admin_payroll_logs():
        if session.get('role') != 'Admin': return redirect(url_for('login'))
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
        record = db.session.get(PayrollHistory, pid)
        if record: db.session.delete(record); db.session.commit()
        return redirect(url_for('admin_payroll_logs'))