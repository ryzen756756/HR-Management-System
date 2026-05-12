from flask import Flask
from config import Config
from models import db, Settings, Employee, Attendance, Announcement, AnnouncementComment, LeaveRequest, PayrollHistory
import os

from routes_auth import setup_auth_routes
from routes_admin import setup_admin_routes
from routes_employee import setup_employee_routes

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config.from_object(Config)
db.init_app(app)

UPLOAD_FOLDER = os.path.join(app.static_folder, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

setup_auth_routes(app, db, Employee, UPLOAD_FOLDER)
setup_admin_routes(app, db, Employee, Attendance, Settings, LeaveRequest, PayrollHistory, Announcement, AnnouncementComment, UPLOAD_FOLDER)
setup_employee_routes(app, db, Employee, Attendance, Settings, LeaveRequest, PayrollHistory, Announcement, AnnouncementComment, UPLOAD_FOLDER)

def init_db():
    db.create_all()
    if db.session.get(Settings, 1) is None:
        db.session.add(Settings(id=1, lat=30.0444, lng=31.2357, radius=20000))
    if Employee.query.filter_by(username="admin").first() is None:
        db.session.add(Employee(username="admin", password="123", name="المدير العام", role="Admin", dept="الإدارة", hourly_rate=0.0))
    db.session.commit()

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True)