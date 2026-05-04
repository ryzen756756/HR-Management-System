from flask import redirect, render_template, request, session, url_for, jsonify, render_template_string
import os
import base64
from datetime import datetime
import json
import numpy as np

try:
    import face_recognition
except ImportError:
    face_recognition = None

def setup_auth_routes(app, db, Employee, UPLOAD_FOLDER):
    @app.route('/', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            user = Employee.query.filter_by(username=username, password=password).first()
            if user:
                session.update({'logged_in': True, 'user_id': user.id, 'user_name': user.name, 'role': user.role})
                if user.role == 'Admin': return redirect(url_for('dashboard'))
                else: return redirect(url_for('employee_dashboard'))
            return "خطأ في بيانات الدخول!"
            
        original_html = render_template('login.html')
        magic_button = f'''<div style="text-align: center; margin-top: 10px;">
            <a href="{url_for('forgot_password')}" style="color: #666; font-size: 0.85em; text-decoration: none; font-family: Arial;">نسيت كلمة المرور؟ 🔐</a>
        </div>'''
        if '</form>' in original_html: return original_html.replace('</form>', magic_button + '</form>')
        return original_html + magic_button

    @app.route('/forgot_password', methods=['GET', 'POST'])
    def forgot_password():
        if request.method == 'POST':
            data = request.get_json(silent=True)
            if not data: return jsonify({"message": "بيانات غير صالحة ❌"}), 400
            
            username = data.get('username')
            new_password = data.get('new_password')
            confirm_password = data.get('confirm_password')
            photo_data = data.get('photo')

            if not all([username, new_password, confirm_password, photo_data]):
                return jsonify({"message": "جميع البيانات والصورة مطلوبة! ❌"}), 400

            if new_password != confirm_password:
                return jsonify({"message": "كلمة السر الجديدة غير متطابقة! ❌"}), 400

            user = Employee.query.filter_by(username=username).first()
            if not user: return jsonify({"message": "اسم المستخدم هذا غير مسجل لدينا! ❌"}), 400
            if face_recognition is None or not user.face_encoding:
                return jsonify({"message": "بصمة الوجه غير مسجلة لهذا الموظف، راجع الإدارة! ❌"}), 400

            try:
                if ',' in photo_data: photo_data = photo_data.split(',')[1]
                filename = f"reset_{user.id}_{datetime.now().strftime('%H%M%S')}.jpg"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                
                with open(filepath, 'wb') as f: f.write(base64.b64decode(photo_data))

                known_encoding = np.array(json.loads(user.face_encoding))
                current_image = face_recognition.load_image_file(filepath)
                current_encodings = face_recognition.face_encodings(current_image)

                if len(current_encodings) == 0: return jsonify({"message": "لم يتم العثور على وجه واضح في الصورة! ❌"}), 400

                match = face_recognition.compare_faces([known_encoding], current_encodings[0], tolerance=0.6)
                if not match[0]: return jsonify({"message": "بصمة الوجه غير مطابقة! محاولة اختراق مرفوضة 🚨"}), 400

                user.password = new_password
                db.session.commit()
                return jsonify({"message": "✅ تم التحقق من هويتك وتغيير كلمة المرور بنجاح!"})

            except Exception as e:
                return jsonify({"message": f"حدث خطأ أثناء معالجة الصورة: {str(e)}"}), 500

        html_content = """
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head><meta charset="UTF-8"><title>استرجاع كلمة المرور</title></head>
        <body style="font-family: Arial; text-align: center; margin-top: 50px; background-color: #f4f4f4;">
            <div style="background: white; width: 420px; margin: auto; padding: 30px; border-radius: 10px; box-shadow: 0px 0px 15px #ccc;">
                <h2 style="color: #333;">إعادة تعيين بـ "بصمة الوجه" 🤖📸</h2>
                <p style="color: #666; font-size: 0.85em; font-weight: bold; margin-bottom: 20px;">السيستم هيفتح الكاميرا للتأكد إنك صاحب الحساب الحقيقي.</p>
                <form id="resetForm">
                    <input type="text" id="username" placeholder="اسم المستخدم (Username)" required style="width: 85%; margin-bottom: 10px; padding: 10px; border-radius: 5px; border: 1px solid #ccc;"><br>
                    <hr style="border: 0.5px solid #eee; width: 85%; margin: 15px auto;">
                    <input type="password" id="new_password" placeholder="كلمة المرور الجديدة" required style="width: 85%; margin-bottom: 10px; padding: 10px; border-radius: 5px; border: 1px solid #ccc;"><br>
                    <input type="password" id="confirm_password" placeholder="تأكيد كلمة المرور" required style="width: 85%; margin-bottom: 20px; padding: 10px; border-radius: 5px; border: 1px solid #ccc;"><br>
                    <button type="submit" style="width: 90%; padding: 12px; background: #28a745; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold;">📸 افتح الكاميرا وتأكد من هويتي</button>
                </form>
                <br><a href="{{ url_for('login') }}" style="display: inline-block; padding: 10px 20px; background: #6c757d; color: white; text-decoration: none; border-radius: 5px; font-size: 0.85em;">🔙 رجوع لتسجيل الدخول</a>
            </div>
            <script>
            document.getElementById('resetForm').onsubmit = async function(e) {
                e.preventDefault();
                const username = document.getElementById('username').value;
                const new_pass = document.getElementById('new_password').value;
                const conf_pass = document.getElementById('confirm_password').value;
                if(new_pass !== conf_pass) { alert("كلمة السر الجديدة غير متطابقة! ❌"); return; }
                alert("جاري فتح الكاميرا للتحقق من شخصيتك... يرجى النظر للكاميرا ⏳");
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
                    const video = document.createElement('video'); video.srcObject = stream;
                    await new Promise(resolve => video.onloadedmetadata = resolve); await video.play();
                    const canvas = document.createElement('canvas'); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
                    canvas.getContext('2d').drawImage(video, 0, 0); const photoData = canvas.toDataURL('image/jpeg');
                    stream.getTracks().forEach(track => track.stop());
                    const response = await fetch('/forgot_password', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username: username, new_password: new_pass, confirm_password: conf_pass, photo: photoData })
                    });
                    const result = await response.json(); alert(result.message);
                    if(response.ok) { window.location.href = '/'; }
                } catch (err) { alert("مش قادر أفتح الكاميرا ❌ اتأكد إنك إديت سماح (Allow) للمتصفح."); }
            };
            </script>
        </body>
        </html>
        """
        return render_template_string(html_content)

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))