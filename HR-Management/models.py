from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class TemplateAccessMixin:
    def __getitem__(self, key):
        value = getattr(self, key)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value


class Settings(TemplateAccessMixin, db.Model):
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True, default=1)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    radius = db.Column(db.Integer)


class Employee(TemplateAccessMixin, db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)
    dept = db.Column(db.String(100))
    role = db.Column(db.String(20), nullable=False, default="Employee")
    photo = db.Column(db.String(255))
    face_encoding = db.Column(db.Text)
    hourly_rate = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    attendance_records = db.relationship(
        "Attendance",
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    leave_requests = db.relationship(
        "LeaveRequest",
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    payroll_history = db.relationship(
        "PayrollHistory",
        back_populates="employee",
        cascade="all, delete-orphan",
    )

    @property
    def department(self):
        return self.dept


class Attendance(TemplateAccessMixin, db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"))
    date = db.Column(db.Date, nullable=False, index=True)
    time = db.Column(db.Time)
    check_out_time = db.Column(db.Time)
    work_hours = db.Column(db.Float, nullable=False, default=0.0)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    status = db.Column(db.String(100))
    photo = db.Column(db.String(255))

    employee = db.relationship("Employee", back_populates="attendance_records")


class LeaveRequest(TemplateAccessMixin, db.Model):
    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"))
    leave_type = db.Column(db.String(100))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="Pending")
    request_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    employee = db.relationship("Employee", back_populates="leave_requests")


class PayrollHistory(TemplateAccessMixin, db.Model):
    __tablename__ = "payroll_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("employees.id", ondelete="CASCADE"))
    month = db.Column(db.String(7), nullable=False, index=True)
    total_hours = db.Column(db.Float, nullable=False, default=0.0)
    hourly_rate = db.Column(db.Float, nullable=False, default=0.0)
    basic_salary = db.Column(db.Float, nullable=False, default=0.0)
    bonus = db.Column(db.Float, nullable=False, default=0.0)
    deduction = db.Column(db.Float, nullable=False, default=0.0)
    net_salary = db.Column(db.Float, nullable=False, default=0.0)
    issue_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    employee = db.relationship("Employee", back_populates="payroll_history")


class Announcement(TemplateAccessMixin, db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    comments = db.relationship(
        "AnnouncementComment",
        back_populates="announcement",
        cascade="all, delete-orphan",
    )


class AnnouncementComment(TemplateAccessMixin, db.Model):
    __tablename__ = "announcement_comments"

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(
        db.Integer,
        db.ForeignKey("announcements.id", ondelete="CASCADE"),
    )
    user_name = db.Column(db.String(150))
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    announcement = db.relationship("Announcement", back_populates="comments")
