import os
import sqlite3
from functools import wraps
from datetime import datetime, date
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, abort
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database.db"

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static")
)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")

DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
PAYMENT_STATUSES = ["Оплачено", "Не оплачено", "Частично"]
ATTENDANCE_STATUSES = ["Пришёл", "Не пришёл", "Опоздал", "Уважительная причина"]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=()):
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','teacher','student')),
            phone TEXT,
            email TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS groups_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            subject_id INTEGER,
            teacher_id INTEGER,
            price REAL DEFAULT 0,
            room TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL,
            FOREIGN KEY(teacher_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS group_students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            UNIQUE(group_id, student_id),
            FOREIGN KEY(group_id) REFERENCES groups_table(id) ON DELETE CASCADE,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            day_of_week TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            room TEXT,
            FOREIGN KEY(group_id) REFERENCES groups_table(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            amount REAL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Не оплачено',
            paid_at TEXT,
            comment TEXT,
            UNIQUE(student_id, month),
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            teacher_id INTEGER,
            date TEXT NOT NULL,
            status TEXT NOT NULL,
            comment TEXT,
            UNIQUE(group_id, student_id, date),
            FOREIGN KEY(group_id) REFERENCES groups_table(id) ON DELETE CASCADE,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(teacher_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            group_id INTEGER,
            subject_id INTEGER,
            teacher_id INTEGER,
            title TEXT NOT NULL,
            score REAL NOT NULL,
            max_score REAL DEFAULT 100,
            comment TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(group_id) REFERENCES groups_table(id) ON DELETE SET NULL,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL,
            FOREIGN KEY(teacher_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            subject_id INTEGER,
            teacher_id INTEGER,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            comment TEXT,
            FOREIGN KEY(group_id) REFERENCES groups_table(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL,
            FOREIGN KEY(teacher_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            group_id INTEGER,
            subject_id INTEGER,
            teacher_id INTEGER,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(group_id) REFERENCES groups_table(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL,
            FOREIGN KEY(teacher_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS test_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_option TEXT NOT NULL CHECK(correct_option IN ('A','B','C','D')),
            FOREIGN KEY(test_id) REFERENCES tests(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS test_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(test_id) REFERENCES tests(id) ON DELETE CASCADE,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS test_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            selected_option TEXT,
            is_correct INTEGER DEFAULT 0,
            FOREIGN KEY(attempt_id) REFERENCES test_attempts(id) ON DELETE CASCADE,
            FOREIGN KEY(question_id) REFERENCES test_questions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()

    user_count = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        users = [
            ("admin", generate_password_hash("admin123"), "Главный администратор", "admin", "+998901112233", "admin@center.uz"),
            ("TCH1001", generate_password_hash("123456"), "Karimova Dilnoza", "teacher", "+998901234567", "teacher@center.uz"),
            ("STU1001", generate_password_hash("123456"), "Aliyev Azizbek", "student", "+998909876543", "student@center.uz"),
            ("STU1002", generate_password_hash("123456"), "Rakhimova Malika", "student", "+998909876544", "malika@center.uz"),
        ]
        cur.executemany(
            "INSERT INTO users(username,password_hash,full_name,role,phone,email) VALUES(?,?,?,?,?,?)", users
        )
        conn.commit()
        cur.execute("INSERT INTO subjects(name,description) VALUES(?,?)", ("Математика", "Алгебра, статистика и подготовка к экзаменам"))
        cur.execute("INSERT INTO subjects(name,description) VALUES(?,?)", ("Английский язык", "Grammar, speaking and IELTS foundation"))
        conn.commit()
        teacher_id = cur.execute("SELECT id FROM users WHERE username='TCH1001'").fetchone()[0]
        subject_id = cur.execute("SELECT id FROM subjects WHERE name='Математика'").fetchone()[0]
        cur.execute("INSERT INTO groups_table(name,subject_id,teacher_id,price,room) VALUES(?,?,?,?,?)", ("MATH-A1", subject_id, teacher_id, 350000, "203"))
        group_id = cur.lastrowid
        student_ids = [row[0] for row in cur.execute("SELECT id FROM users WHERE role='student'").fetchall()]
        for sid in student_ids:
            cur.execute("INSERT OR IGNORE INTO group_students(group_id,student_id) VALUES(?,?)", (group_id, sid))
            cur.execute("INSERT OR IGNORE INTO payments(student_id,month,amount,status,paid_at,comment) VALUES(?,?,?,?,?,?)", (sid, date.today().strftime("%Y-%m"), 350000, "Не оплачено", "", "Демо запись"))
        cur.execute("INSERT INTO schedule(group_id,day_of_week,start_time,end_time,room) VALUES(?,?,?,?,?)", (group_id, "Понедельник", "14:00", "15:30", "203"))
        cur.execute("INSERT INTO schedule(group_id,day_of_week,start_time,end_time,room) VALUES(?,?,?,?,?)", (group_id, "Среда", "14:00", "15:30", "203"))
        cur.execute("INSERT INTO news(title,body,created_by) VALUES(?,?,?)", ("Добро пожаловать в IlmStart EDU", "IlmStart EDU готов для контроля учеников, оплат, результатов, расписания и тестов.", 1))
        cur.execute("INSERT INTO announcements(title,body,created_by) VALUES(?,?,?)", ("Оплата за месяц", "Пожалуйста, внесите месячную оплату до 10 числа.", 1))
        cur.execute("INSERT INTO tests(title,group_id,subject_id,teacher_id,description) VALUES(?,?,?,?,?)", ("Пробный тест по математике", group_id, subject_id, teacher_id, "Демо-тест для проверки системы"))
        test_id = cur.lastrowid
        cur.execute("INSERT INTO test_questions(test_id,question,option_a,option_b,option_c,option_d,correct_option) VALUES(?,?,?,?,?,?,?)", (test_id, "Сколько будет 2 + 2?", "4", "3", "5", "2", "A"))
        cur.execute("INSERT INTO test_questions(test_id,question,option_a,option_b,option_c,option_d,correct_option) VALUES(?,?,?,?,?,?,?)", (test_id, "Как называется результат умножения?", "Произведение", "Сумма", "Разность", "Частное", "A"))
        conn.commit()
    conn.close()


def current_user():
    if "user_id" not in session:
        return None
    return query_db("SELECT * FROM users WHERE id=? AND is_active=1", (session["user_id"],), one=True)


@app.context_processor
def inject_globals():
    user = current_user() if "user_id" in session else None
    unread_count = 0
    if user:
        unread_count = query_db("SELECT COUNT(*) AS c FROM notifications WHERE user_id=? AND is_read=0", (user["id"],), one=True)["c"]
    return {"current_user": user, "unread_count": unread_count, "current_year": datetime.now().year}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login"))
            if user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def generate_username(role):
    prefix = {"student": "STU", "teacher": "TCH", "admin": "ADM"}[role]
    row = query_db("SELECT COUNT(*) AS c FROM users WHERE role=?", (role,), one=True)
    return f"{prefix}{1001 + row['c']}"


def add_notification(user_id, title, body):
    execute_db("INSERT INTO notifications(user_id,title,body) VALUES(?,?,?)", (user_id, title, body))


def get_role_dashboard(role):
    if role == "admin":
        return "admin_dashboard"
    if role == "teacher":
        return "teacher_dashboard"
    return "student_dashboard"


@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403, message="У вас нет доступа к этой странице."), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="Страница не найдена."), 404


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = query_db("SELECT * FROM users WHERE username=? AND is_active=1", (username,), one=True)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Добро пожаловать, {user['full_name']}!", "success")
            return redirect(url_for("dashboard"))
        flash("Неверный логин или пароль.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Вы вышли из аккаунта.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    return redirect(url_for(get_role_dashboard(user["role"])))


# ------------------------- ADMIN -------------------------
@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    stats = {
        "students": query_db("SELECT COUNT(*) AS c FROM users WHERE role='student' AND is_active=1", one=True)["c"],
        "teachers": query_db("SELECT COUNT(*) AS c FROM users WHERE role='teacher' AND is_active=1", one=True)["c"],
        "groups": query_db("SELECT COUNT(*) AS c FROM groups_table", one=True)["c"],
        "unpaid": query_db("SELECT COUNT(*) AS c FROM payments WHERE status!='Оплачено'", one=True)["c"],
    }
    news = query_db("SELECT * FROM news ORDER BY created_at DESC LIMIT 6")
    announcements = query_db("SELECT * FROM announcements ORDER BY created_at DESC LIMIT 6")
    payments = query_db(
        """
        SELECT p.*, u.full_name FROM payments p
        JOIN users u ON u.id=p.student_id
        ORDER BY p.month DESC, p.id DESC LIMIT 8
        """
    )
    return render_template("admin_dashboard.html", stats=stats, news=news, announcements=announcements, payments=payments)


@app.route("/admin/students", methods=["GET", "POST"])
@role_required("admin")
def admin_students():
    generated = None
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "123456").strip() or "123456"
        username = request.form.get("username", "").strip() or generate_username("student")
        if not full_name:
            flash("Введите ФИО ученика.", "danger")
        else:
            try:
                execute_db(
                    "INSERT INTO users(username,password_hash,full_name,role,phone,email) VALUES(?,?,?,?,?,?)",
                    (username, generate_password_hash(password), full_name, "student", phone, email),
                )
                generated = {"username": username, "password": password}
                flash(f"Ученик добавлен. Логин: {username}, пароль: {password}", "success")
            except sqlite3.IntegrityError:
                flash("Такой логин уже существует.", "danger")
    students = query_db("SELECT * FROM users WHERE role='student' AND is_active=1 ORDER BY id DESC")
    groups = query_db("SELECT * FROM groups_table ORDER BY name")
    return render_template("manage_users.html", title="Ученики", role="student", users=students, groups=groups, generated=generated)


@app.route("/admin/teachers", methods=["GET", "POST"])
@role_required("admin")
def admin_teachers():
    generated = None
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "123456").strip() or "123456"
        username = request.form.get("username", "").strip() or generate_username("teacher")
        if not full_name:
            flash("Введите ФИО учителя.", "danger")
        else:
            try:
                execute_db(
                    "INSERT INTO users(username,password_hash,full_name,role,phone,email) VALUES(?,?,?,?,?,?)",
                    (username, generate_password_hash(password), full_name, "teacher", phone, email),
                )
                generated = {"username": username, "password": password}
                flash(f"Учитель добавлен. Логин: {username}, пароль: {password}", "success")
            except sqlite3.IntegrityError:
                flash("Такой логин уже существует.", "danger")
    teachers = query_db("SELECT * FROM users WHERE role='teacher' AND is_active=1 ORDER BY id DESC")
    return render_template("manage_users.html", title="Учителя", role="teacher", users=teachers, generated=generated)


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@role_required("admin")
def delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("Нельзя удалить свой аккаунт.", "danger")
    else:
        execute_db("UPDATE users SET is_active=0 WHERE id=?", (user_id,))
        flash("Пользователь отключён.", "success")
    return redirect(request.referrer or url_for("admin_dashboard"))


@app.route("/admin/users/<int:user_id>/reset", methods=["POST"])
@role_required("admin")
def reset_user_password(user_id):
    new_password = request.form.get("new_password", "123456").strip() or "123456"
    execute_db("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_password), user_id))
    flash(f"Новый пароль: {new_password}", "success")
    return redirect(request.referrer or url_for("admin_dashboard"))


@app.route("/admin/subjects", methods=["GET", "POST"])
@role_required("admin")
def admin_subjects():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if name:
            try:
                execute_db("INSERT INTO subjects(name,description) VALUES(?,?)", (name, description))
                flash("Предмет добавлен.", "success")
            except sqlite3.IntegrityError:
                flash("Такой предмет уже есть.", "danger")
    subjects = query_db("SELECT * FROM subjects ORDER BY name")
    return render_template("subjects.html", subjects=subjects)


@app.route("/admin/subjects/<int:subject_id>/delete", methods=["POST"])
@role_required("admin")
def delete_subject(subject_id):
    execute_db("DELETE FROM subjects WHERE id=?", (subject_id,))
    flash("Предмет удалён.", "success")
    return redirect(url_for("admin_subjects"))


@app.route("/admin/groups", methods=["GET", "POST"])
@role_required("admin")
def admin_groups():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create_group":
            name = request.form.get("name", "").strip()
            subject_id = request.form.get("subject_id") or None
            teacher_id = request.form.get("teacher_id") or None
            price = request.form.get("price") or 0
            room = request.form.get("room", "").strip()
            if name:
                try:
                    execute_db("INSERT INTO groups_table(name,subject_id,teacher_id,price,room) VALUES(?,?,?,?,?)", (name, subject_id, teacher_id, price, room))
                    flash("Группа добавлена.", "success")
                except sqlite3.IntegrityError:
                    flash("Такая группа уже существует.", "danger")
        elif action == "add_student":
            group_id = request.form.get("group_id")
            student_id = request.form.get("student_id")
            if group_id and student_id:
                try:
                    execute_db("INSERT INTO group_students(group_id,student_id) VALUES(?,?)", (group_id, student_id))
                    flash("Ученик добавлен в группу.", "success")
                except sqlite3.IntegrityError:
                    flash("Этот ученик уже есть в группе.", "info")
    groups = query_db(
        """
        SELECT g.*, s.name AS subject_name, t.full_name AS teacher_name,
               (SELECT COUNT(*) FROM group_students gs WHERE gs.group_id=g.id) AS student_count
        FROM groups_table g
        LEFT JOIN subjects s ON s.id=g.subject_id
        LEFT JOIN users t ON t.id=g.teacher_id
        ORDER BY g.id DESC
        """
    )
    subjects = query_db("SELECT * FROM subjects ORDER BY name")
    teachers = query_db("SELECT * FROM users WHERE role='teacher' AND is_active=1 ORDER BY full_name")
    students = query_db("SELECT * FROM users WHERE role='student' AND is_active=1 ORDER BY full_name")
    members = query_db(
        """
        SELECT gs.id, gs.group_id, u.full_name, u.username
        FROM group_students gs JOIN users u ON u.id=gs.student_id
        ORDER BY u.full_name
        """
    )
    return render_template("groups.html", groups=groups, subjects=subjects, teachers=teachers, students=students, members=members)


@app.route("/admin/group-student/<int:membership_id>/delete", methods=["POST"])
@role_required("admin")
def delete_group_student(membership_id):
    execute_db("DELETE FROM group_students WHERE id=?", (membership_id,))
    flash("Ученик удалён из группы.", "success")
    return redirect(url_for("admin_groups"))


@app.route("/admin/schedule", methods=["GET", "POST"])
@role_required("admin")
def admin_schedule():
    if request.method == "POST":
        group_id = request.form.get("group_id")
        day = request.form.get("day_of_week")
        start = request.form.get("start_time")
        end = request.form.get("end_time")
        room = request.form.get("room", "").strip()
        if group_id and day and start and end:
            execute_db("INSERT INTO schedule(group_id,day_of_week,start_time,end_time,room) VALUES(?,?,?,?,?)", (group_id, day, start, end, room))
            flash("Расписание добавлено.", "success")
    schedule = query_db(
        """
        SELECT sc.*, g.name AS group_name, s.name AS subject_name, t.full_name AS teacher_name
        FROM schedule sc
        JOIN groups_table g ON g.id=sc.group_id
        LEFT JOIN subjects s ON s.id=g.subject_id
        LEFT JOIN users t ON t.id=g.teacher_id
        ORDER BY sc.id DESC
        """
    )
    groups = query_db("SELECT * FROM groups_table ORDER BY name")
    return render_template("schedule.html", schedule=schedule, groups=groups, days=DAYS)


@app.route("/admin/schedule/<int:schedule_id>/delete", methods=["POST"])
@role_required("admin")
def delete_schedule(schedule_id):
    execute_db("DELETE FROM schedule WHERE id=?", (schedule_id,))
    flash("Запись расписания удалена.", "success")
    return redirect(url_for("admin_schedule"))


@app.route("/admin/payments", methods=["GET", "POST"])
@role_required("admin")
def admin_payments():
    if request.method == "POST":
        student_id = request.form.get("student_id")
        month = request.form.get("month")
        amount = request.form.get("amount") or 0
        status = request.form.get("status")
        comment = request.form.get("comment", "").strip()
        paid_at = datetime.now().strftime("%Y-%m-%d") if status == "Оплачено" else ""
        if student_id and month and status:
            execute_db(
                """
                INSERT INTO payments(student_id,month,amount,status,paid_at,comment)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(student_id, month) DO UPDATE SET
                  amount=excluded.amount, status=excluded.status, paid_at=excluded.paid_at, comment=excluded.comment
                """,
                (student_id, month, amount, status, paid_at, comment),
            )
            add_notification(student_id, "Статус оплаты обновлён", f"Оплата за {month}: {status}.")
            flash("Оплата сохранена.", "success")
    students = query_db("SELECT * FROM users WHERE role='student' AND is_active=1 ORDER BY full_name")
    payments = query_db(
        """
        SELECT p.*, u.full_name, u.username FROM payments p
        JOIN users u ON u.id=p.student_id
        ORDER BY p.month DESC, p.id DESC
        """
    )
    return render_template("payments.html", payments=payments, students=students, statuses=PAYMENT_STATUSES, current_month=date.today().strftime("%Y-%m"))


@app.route("/admin/news", methods=["GET", "POST"])
@role_required("admin")
def admin_news():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if title and body:
            execute_db("INSERT INTO news(title,body,created_by) VALUES(?,?,?)", (title, body, session["user_id"]))
            flash("Новость добавлена.", "success")
    items = query_db("SELECT * FROM news ORDER BY created_at DESC")
    return render_template("content_items.html", title="Новости", endpoint="admin_news", delete_endpoint="delete_news", items=items)


@app.route("/admin/news/<int:item_id>/delete", methods=["POST"])
@role_required("admin")
def delete_news(item_id):
    execute_db("DELETE FROM news WHERE id=?", (item_id,))
    flash("Новость удалена.", "success")
    return redirect(url_for("admin_news"))


@app.route("/admin/announcements", methods=["GET", "POST"])
@role_required("admin")
def admin_announcements():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if title and body:
            execute_db("INSERT INTO announcements(title,body,created_by) VALUES(?,?,?)", (title, body, session["user_id"]))
            flash("Объявление добавлено.", "success")
    items = query_db("SELECT * FROM announcements ORDER BY created_at DESC")
    return render_template("content_items.html", title="Объявления", endpoint="admin_announcements", delete_endpoint="delete_announcement", items=items)


@app.route("/admin/announcements/<int:item_id>/delete", methods=["POST"])
@role_required("admin")
def delete_announcement(item_id):
    execute_db("DELETE FROM announcements WHERE id=?", (item_id,))
    flash("Объявление удалено.", "success")
    return redirect(url_for("admin_announcements"))


@app.route("/admin/results")
@role_required("admin")
def admin_results():
    results = query_db(
        """
        SELECT r.*, st.full_name AS student_name, g.name AS group_name, s.name AS subject_name, t.full_name AS teacher_name
        FROM results r
        JOIN users st ON st.id=r.student_id
        LEFT JOIN groups_table g ON g.id=r.group_id
        LEFT JOIN subjects s ON s.id=r.subject_id
        LEFT JOIN users t ON t.id=r.teacher_id
        ORDER BY r.created_at DESC
        """
    )
    return render_template("results_list.html", title="Все результаты", results=results)


# ------------------------- TEACHER -------------------------
@app.route("/teacher/dashboard")
@role_required("teacher")
def teacher_dashboard():
    uid = session["user_id"]
    stats = {
        "groups": query_db("SELECT COUNT(*) AS c FROM groups_table WHERE teacher_id=?", (uid,), one=True)["c"],
        "students": query_db(
            """
            SELECT COUNT(DISTINCT gs.student_id) AS c FROM group_students gs
            JOIN groups_table g ON g.id=gs.group_id WHERE g.teacher_id=?
            """, (uid,), one=True
        )["c"],
        "results": query_db("SELECT COUNT(*) AS c FROM results WHERE teacher_id=?", (uid,), one=True)["c"],
        "tests": query_db("SELECT COUNT(*) AS c FROM tests WHERE teacher_id=?", (uid,), one=True)["c"],
    }
    groups = query_db(
        """
        SELECT g.*, s.name AS subject_name,
        (SELECT COUNT(*) FROM group_students gs WHERE gs.group_id=g.id) AS student_count
        FROM groups_table g LEFT JOIN subjects s ON s.id=g.subject_id
        WHERE g.teacher_id=? ORDER BY g.name
        """, (uid,)
    )
    news = query_db("SELECT * FROM news ORDER BY created_at DESC LIMIT 4")
    return render_template("teacher_dashboard.html", stats=stats, groups=groups, news=news)


def teacher_groups():
    return query_db("SELECT * FROM groups_table WHERE teacher_id=? ORDER BY name", (session["user_id"],))


@app.route("/teacher/attendance", methods=["GET", "POST"])
@role_required("teacher")
def teacher_attendance():
    groups = teacher_groups()
    selected_group_id = request.values.get("group_id") or (groups[0]["id"] if groups else None)
    selected_date = request.values.get("date") or date.today().strftime("%Y-%m-%d")
    if request.method == "POST" and selected_group_id:
        students = query_db(
            """
            SELECT u.* FROM users u JOIN group_students gs ON gs.student_id=u.id
            WHERE gs.group_id=? AND u.is_active=1 ORDER BY u.full_name
            """, (selected_group_id,)
        )
        for student in students:
            status = request.form.get(f"status_{student['id']}")
            comment = request.form.get(f"comment_{student['id']}", "").strip()
            if status:
                execute_db(
                    """
                    INSERT INTO attendance(group_id,student_id,teacher_id,date,status,comment)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(group_id, student_id, date) DO UPDATE SET
                      teacher_id=excluded.teacher_id, status=excluded.status, comment=excluded.comment
                    """, (selected_group_id, student["id"], session["user_id"], selected_date, status, comment)
                )
        flash("Перекличка сохранена.", "success")
        return redirect(url_for("teacher_attendance", group_id=selected_group_id, date=selected_date))
    students = []
    existing = {}
    if selected_group_id:
        students = query_db(
            """
            SELECT u.* FROM users u JOIN group_students gs ON gs.student_id=u.id
            WHERE gs.group_id=? AND u.is_active=1 ORDER BY u.full_name
            """, (selected_group_id,)
        )
        rows = query_db("SELECT * FROM attendance WHERE group_id=? AND date=?", (selected_group_id, selected_date))
        existing = {row["student_id"]: row for row in rows}
    return render_template("teacher_attendance.html", groups=groups, students=students, existing=existing, selected_group_id=int(selected_group_id) if selected_group_id else None, selected_date=selected_date, statuses=ATTENDANCE_STATUSES)


@app.route("/teacher/results", methods=["GET", "POST"])
@role_required("teacher")
def teacher_results():
    groups = teacher_groups()
    if request.method == "POST":
        student_id = request.form.get("student_id")
        group_id = request.form.get("group_id")
        title = request.form.get("title", "").strip()
        score = request.form.get("score") or 0
        max_score = request.form.get("max_score") or 100
        comment = request.form.get("comment", "").strip()
        group = query_db("SELECT * FROM groups_table WHERE id=? AND teacher_id=?", (group_id, session["user_id"]), one=True)
        if student_id and group and title:
            execute_db(
                "INSERT INTO results(student_id,group_id,subject_id,teacher_id,title,score,max_score,comment) VALUES(?,?,?,?,?,?,?,?)",
                (student_id, group_id, group["subject_id"], session["user_id"], title, score, max_score, comment),
            )
            add_notification(student_id, "Добавлен новый результат", f"{title}: {score}/{max_score}")
            flash("Результат сохранён.", "success")
    students = query_db(
        """
        SELECT DISTINCT u.*, g.id AS group_id, g.name AS group_name FROM users u
        JOIN group_students gs ON gs.student_id=u.id
        JOIN groups_table g ON g.id=gs.group_id
        WHERE g.teacher_id=? AND u.is_active=1 ORDER BY u.full_name
        """, (session["user_id"],)
    )
    results = query_db(
        """
        SELECT r.*, st.full_name AS student_name, g.name AS group_name, s.name AS subject_name
        FROM results r
        JOIN users st ON st.id=r.student_id
        LEFT JOIN groups_table g ON g.id=r.group_id
        LEFT JOIN subjects s ON s.id=r.subject_id
        WHERE r.teacher_id=? ORDER BY r.created_at DESC
        """, (session["user_id"],)
    )
    return render_template("teacher_results.html", groups=groups, students=students, results=results)


@app.route("/teacher/topics", methods=["GET", "POST"])
@role_required("teacher")
def teacher_topics():
    groups = teacher_groups()
    if request.method == "POST":
        group_id = request.form.get("group_id")
        title = request.form.get("title", "").strip()
        topic_date = request.form.get("date") or date.today().strftime("%Y-%m-%d")
        comment = request.form.get("comment", "").strip()
        group = query_db("SELECT * FROM groups_table WHERE id=? AND teacher_id=?", (group_id, session["user_id"]), one=True)
        if group and title:
            execute_db("INSERT INTO topics(group_id,subject_id,teacher_id,title,date,comment) VALUES(?,?,?,?,?,?)", (group_id, group["subject_id"], session["user_id"], title, topic_date, comment))
            flash("Тема урока сохранена.", "success")
    topics = query_db(
        """
        SELECT tp.*, g.name AS group_name, s.name AS subject_name
        FROM topics tp JOIN groups_table g ON g.id=tp.group_id
        LEFT JOIN subjects s ON s.id=tp.subject_id
        WHERE tp.teacher_id=? ORDER BY tp.date DESC
        """, (session["user_id"],)
    )
    return render_template("teacher_topics.html", groups=groups, topics=topics, today=date.today().strftime("%Y-%m-%d"))


@app.route("/teacher/tests", methods=["GET", "POST"])
@role_required("teacher")
def teacher_tests():
    groups = teacher_groups()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        group_id = request.form.get("group_id")
        description = request.form.get("description", "").strip()
        group = query_db("SELECT * FROM groups_table WHERE id=? AND teacher_id=?", (group_id, session["user_id"]), one=True)
        if title and group:
            test_id = execute_db("INSERT INTO tests(title,group_id,subject_id,teacher_id,description) VALUES(?,?,?,?,?)", (title, group_id, group["subject_id"], session["user_id"], description))
            flash("Тест создан. Теперь добавьте вопросы.", "success")
            return redirect(url_for("teacher_test_questions", test_id=test_id))
    tests = query_db(
        """
        SELECT t.*, g.name AS group_name, s.name AS subject_name,
        (SELECT COUNT(*) FROM test_questions q WHERE q.test_id=t.id) AS questions_count
        FROM tests t LEFT JOIN groups_table g ON g.id=t.group_id
        LEFT JOIN subjects s ON s.id=t.subject_id
        WHERE t.teacher_id=? ORDER BY t.created_at DESC
        """, (session["user_id"],)
    )
    return render_template("teacher_tests.html", groups=groups, tests=tests)


@app.route("/teacher/tests/<int:test_id>/questions", methods=["GET", "POST"])
@role_required("teacher")
def teacher_test_questions(test_id):
    test = query_db("SELECT * FROM tests WHERE id=? AND teacher_id=?", (test_id, session["user_id"]), one=True)
    if not test:
        abort(404)
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        a = request.form.get("option_a", "").strip()
        b = request.form.get("option_b", "").strip()
        c = request.form.get("option_c", "").strip()
        d = request.form.get("option_d", "").strip()
        correct = request.form.get("correct_option", "A")
        if question and a and b and c and d:
            execute_db("INSERT INTO test_questions(test_id,question,option_a,option_b,option_c,option_d,correct_option) VALUES(?,?,?,?,?,?,?)", (test_id, question, a, b, c, d, correct))
            flash("Вопрос добавлен.", "success")
    questions = query_db("SELECT * FROM test_questions WHERE test_id=? ORDER BY id", (test_id,))
    return render_template("test_questions.html", test=test, questions=questions)


@app.route("/teacher/questions/<int:question_id>/delete", methods=["POST"])
@role_required("teacher")
def delete_question(question_id):
    q = query_db("SELECT q.*, t.teacher_id FROM test_questions q JOIN tests t ON t.id=q.test_id WHERE q.id=?", (question_id,), one=True)
    if not q or q["teacher_id"] != session["user_id"]:
        abort(404)
    test_id = q["test_id"]
    execute_db("DELETE FROM test_questions WHERE id=?", (question_id,))
    flash("Вопрос удалён.", "success")
    return redirect(url_for("teacher_test_questions", test_id=test_id))


# ------------------------- STUDENT -------------------------
@app.route("/student/dashboard")
@role_required("student")
def student_dashboard():
    uid = session["user_id"]
    payments = query_db("SELECT * FROM payments WHERE student_id=? ORDER BY month DESC LIMIT 4", (uid,))
    results = query_db(
        """
        SELECT r.*, g.name AS group_name, s.name AS subject_name FROM results r
        LEFT JOIN groups_table g ON g.id=r.group_id
        LEFT JOIN subjects s ON s.id=r.subject_id
        WHERE r.student_id=? ORDER BY r.created_at DESC LIMIT 5
        """, (uid,)
    )
    schedule = query_db(
        """
        SELECT sc.*, g.name AS group_name, s.name AS subject_name, t.full_name AS teacher_name
        FROM schedule sc JOIN groups_table g ON g.id=sc.group_id
        JOIN group_students gs ON gs.group_id=g.id
        LEFT JOIN subjects s ON s.id=g.subject_id
        LEFT JOIN users t ON t.id=g.teacher_id
        WHERE gs.student_id=? ORDER BY sc.id DESC LIMIT 5
        """, (uid,)
    )
    news = query_db("SELECT * FROM news ORDER BY created_at DESC LIMIT 4")
    announcements = query_db("SELECT * FROM announcements ORDER BY created_at DESC LIMIT 4")
    return render_template("student_dashboard.html", payments=payments, results=results, schedule=schedule, news=news, announcements=announcements)


@app.route("/student/subjects")
@role_required("student")
def student_subjects():
    subjects = query_db(
        """
        SELECT g.name AS group_name, g.price, g.room, s.name AS subject_name, s.description, t.full_name AS teacher_name
        FROM group_students gs
        JOIN groups_table g ON g.id=gs.group_id
        LEFT JOIN subjects s ON s.id=g.subject_id
        LEFT JOIN users t ON t.id=g.teacher_id
        WHERE gs.student_id=? ORDER BY s.name
        """, (session["user_id"],)
    )
    return render_template("student_subjects.html", subjects=subjects)


@app.route("/student/schedule")
@role_required("student")
def student_schedule():
    schedule = query_db(
        """
        SELECT sc.*, g.name AS group_name, s.name AS subject_name, t.full_name AS teacher_name
        FROM schedule sc JOIN groups_table g ON g.id=sc.group_id
        JOIN group_students gs ON gs.group_id=g.id
        LEFT JOIN subjects s ON s.id=g.subject_id
        LEFT JOIN users t ON t.id=g.teacher_id
        WHERE gs.student_id=? ORDER BY sc.id DESC
        """, (session["user_id"],)
    )
    return render_template("student_schedule.html", schedule=schedule)


@app.route("/student/results")
@role_required("student")
def student_results():
    results = query_db(
        """
        SELECT r.*, g.name AS group_name, s.name AS subject_name, t.full_name AS teacher_name
        FROM results r
        LEFT JOIN groups_table g ON g.id=r.group_id
        LEFT JOIN subjects s ON s.id=r.subject_id
        LEFT JOIN users t ON t.id=r.teacher_id
        WHERE r.student_id=? ORDER BY r.created_at DESC
        """, (session["user_id"],)
    )
    return render_template("student_results.html", results=results)


@app.route("/student/payments")
@role_required("student")
def student_payments():
    payments = query_db("SELECT * FROM payments WHERE student_id=? ORDER BY month DESC", (session["user_id"],))
    return render_template("student_payments.html", payments=payments)


@app.route("/student/tests")
@role_required("student")
def student_tests():
    tests = query_db(
        """
        SELECT t.*, g.name AS group_name, s.name AS subject_name,
        (SELECT COUNT(*) FROM test_questions q WHERE q.test_id=t.id) AS questions_count,
        (SELECT MAX(score || '/' || total) FROM test_attempts a WHERE a.test_id=t.id AND a.student_id=?) AS last_score
        FROM tests t
        JOIN groups_table g ON g.id=t.group_id
        JOIN group_students gs ON gs.group_id=g.id
        LEFT JOIN subjects s ON s.id=t.subject_id
        WHERE gs.student_id=? AND t.is_active=1 ORDER BY t.created_at DESC
        """, (session["user_id"], session["user_id"])
    )
    return render_template("student_tests.html", tests=tests)


@app.route("/student/tests/<int:test_id>/take", methods=["GET", "POST"])
@role_required("student")
def take_test(test_id):
    test = query_db(
        """
        SELECT t.*, g.name AS group_name, s.name AS subject_name FROM tests t
        JOIN groups_table g ON g.id=t.group_id
        JOIN group_students gs ON gs.group_id=g.id
        LEFT JOIN subjects s ON s.id=t.subject_id
        WHERE t.id=? AND gs.student_id=? AND t.is_active=1
        """, (test_id, session["user_id"]), one=True
    )
    if not test:
        abort(404)
    questions = query_db("SELECT * FROM test_questions WHERE test_id=? ORDER BY id", (test_id,))
    if request.method == "POST":
        score = 0
        total = len(questions)
        attempt_id = execute_db("INSERT INTO test_attempts(test_id,student_id,score,total) VALUES(?,?,?,?)", (test_id, session["user_id"], 0, total))
        for q in questions:
            selected = request.form.get(f"q_{q['id']}", "")
            is_correct = 1 if selected == q["correct_option"] else 0
            score += is_correct
            execute_db("INSERT INTO test_answers(attempt_id,question_id,selected_option,is_correct) VALUES(?,?,?,?)", (attempt_id, q["id"], selected, is_correct))
        execute_db("UPDATE test_attempts SET score=? WHERE id=?", (score, attempt_id))
        flash(f"Тест завершён. Ваш результат: {score}/{total}", "success")
        return redirect(url_for("student_tests"))
    return render_template("take_test.html", test=test, questions=questions)


@app.route("/notifications")
@login_required
def notifications():
    rows = query_db("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC", (session["user_id"],))
    execute_db("UPDATE notifications SET is_read=1 WHERE user_id=?", (session["user_id"],))
    return render_template("notifications.html", notifications=rows)


# Initialize DB at startup
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
