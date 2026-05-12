from flask import redirect, render_template, request, session, url_for, render_template_string
import os
from datetime import datetime

RESET_REQUESTS = set()

def setup_auth_routes(app, db, Employee, UPLOAD_FOLDER):
    
    @app.route('/', methods=['GET', 'POST'])
    def login():
        error_html = ""
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            user = Employee.query.filter_by(username=username, password=password).first()
            if user:
                session.update({'logged_in': True, 'user_id': user.id, 'user_name': user.name, 'role': user.role})
                if user.role == 'Admin': return redirect(url_for('dashboard'))
                else: return redirect(url_for('employee_dashboard'))
            
            error_html = '<div style="color: #721c24; background-color: #f8d7da; border: 1px solid #f5c6cb; padding: 10px; margin-bottom: 15px; border-radius: 5px; text-align: center; font-weight: bold; font-family: Arial;">❌ خطأ في البيانات!</div>'
            
        original_html = render_template('login.html')
        magic_button = f'''<div style="text-align: center; margin-top: 10px;">
            <a href="{url_for('forgot_password')}" style="color: #666; font-size: 0.85em; text-decoration: none; font-family: Arial;">نسيت كلمة المرور؟ 🔐</a>
        </div>'''
        
        if error_html and '<form' in original_html:
            original_html = original_html.replace('<form', error_html + '<form')

        if '</form>' in original_html: return original_html.replace('</form>', magic_button + '</form>')
        return original_html + magic_button

    @app.route('/forgot_password', methods=['GET', 'POST'])
    def forgot_password():
        if request.method == 'POST':
            username = request.form.get('username')
            user = Employee.query.filter_by(username=username).first()
            
            if user:
                RESET_REQUESTS.add(username)
                return '<script>alert("✅ تم إرسال طلب للإدارة"); window.location.href="/";</script>'
            else:
                return '<script>alert("❌ حساب غير مسجل!"); window.history.back();</script>'

        html_content = """
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head><meta charset="UTF-8"><title>استرجاع كلمة المرور</title></head>
        <body style="font-family: Arial; text-align: center; margin-top: 50px; background-color: #f4f4f4;">
            <div style="background: white; width: 420px; margin: auto; padding: 30px; border-radius: 10px; box-shadow: 0px 0px 15px #ccc;">
                <h2 style="color: #6f42c1;">🛠️ طلب استعادة كلمة المرور</h2>
                <form method="POST" action="/forgot_password">
                    <input type="text" name="username" placeholder="اسم المستخدم (Username)" required style="width: 85%; margin-bottom: 20px; padding: 10px; border-radius: 5px; border: 1px solid #ccc;"><br>
                    <button type="submit" style="width: 90%; padding: 12px; background: #6f42c1; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold;">📩 إرسال الطلب</button>
                </form>
                <br><a href="/" style="display: inline-block; padding: 10px 20px; background: #6c757d; color: white; text-decoration: none; border-radius: 5px; font-size: 0.85em;">🔙 رجوع لتسجيل الدخول</a>
            </div>
        </body>
        </html>
        """
        return render_template_string(html_content)

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))