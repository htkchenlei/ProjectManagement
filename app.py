from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'ProjectManagement'
}


def get_db_connection():
    conn = mysql.connector.connect(**db_config)
    return conn


@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember_me = request.form.get('remember_me')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            if remember_me:
                session.permanent = True
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('is_admin', False)
    return redirect(url_for('login'))


@app.route('/index')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    show_completed = request.args.get('show_completed', 'true') == 'true'

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
    SELECT p.id, p.name, p.client_name, p.scale, p.stage, pp.update_content, pp.update_date, u.username AS owner_username
    FROM Projects p
    LEFT JOIN (
        SELECT project_id, MAX(update_date) AS max_date
        FROM Project_progress
        GROUP BY project_id
    ) latest_updates ON p.id = latest_updates.project_id
    LEFT JOIN Project_progress pp ON p.id = pp.project_id AND latest_updates.max_date = pp.update_date
    LEFT JOIN Users u ON p.owner = u.id
    WHERE p.is_deleted = FALSE AND (p.stage != 'Completed' OR %s)
    """

    params = [show_completed]

    if not session['is_admin']:
        query += " AND (p.sales_person = %s OR p.owner = %s)"
        params.extend([session['user_id'], session['user_id']])

    query += " ORDER BY p.start_date DESC LIMIT 15;"

    cursor.execute(query, params)
    projects = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('index.html', projects=projects, show_completed=show_completed)


@app.route('/add_project', methods=['GET', 'POST'])
def add_project():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    today = date.today().isoformat()

    if request.method == 'POST':
        name = request.form['name']
        client_name = request.form['client_name']
        scale = int(request.form['scale'])
        start_date = request.form['start_date']
        location = request.form['location']
        sales_person = request.form['sales_person']
        stage = request.form['stage']
        owner = request.form['owner']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
        INSERT INTO Projects (name, client_name, scale, start_date, location, sales_person, stage, owner)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, client_name, scale, start_date, location, sales_person, stage, owner))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('index'))

    users = []
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, username FROM Users")
    users = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('add_project.html', users=users, today=today)


@app.route('/update_project/<int:project_id>', methods=['GET', 'POST'])
def update_project(project_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        update_content = request.form['update_content']

        cursor.execute("""
        INSERT INTO Project_progress (project_id, update_content, update_date, updated_by)
        VALUES (%s, %s, CURDATE(), %s)
        """, (project_id, update_content, session['user_id']))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('index'))

    cursor.execute("SELECT * FROM Projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template('project_update.html', project=project)


@app.route('/project_details/<int:project_id>')
def project_details(project_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT p.*, pp.update_content, pp.update_date, u.username AS updated_by_username
    FROM Projects p
    LEFT JOIN Project_progress pp ON p.id = pp.project_id
    LEFT JOIN Users u ON pp.updated_by = u.id
    WHERE p.id = %s
    ORDER BY pp.update_date DESC
    """, (project_id,))
    project_details = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('project_details.html', project_details=project_details)


@app.route('/manage_projects')
def manage_projects():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT p.id, p.name, p.client_name, p.scale, p.start_date, p.location, p.sales_person, p.stage, pp.update_content, pp.update_date, u.username AS owner_username
    FROM Projects p
    LEFT JOIN (
        SELECT project_id, MAX(update_date) AS max_date
        FROM Project_progress
        GROUP BY project_id
    ) latest_updates ON p.id = latest_updates.project_id
    LEFT JOIN Project_progress pp ON p.id = pp.project_id AND latest_updates.max_date = pp.update_date
    LEFT JOIN Users u ON p.owner = u.id
    WHERE p.is_deleted = FALSE
    ORDER BY p.start_date DESC
    LIMIT 15;
    """)

    projects = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('admin.html', projects=projects)


@app.route('/edit_project/<int:project_id>', methods=['GET', 'POST'])
def edit_project(project_id):
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        name = request.form['name']
        client_name = request.form['client_name']
        scale = int(request.form['scale'])
        start_date = request.form['start_date']
        location = request.form['location']
        sales_person = request.form['sales_person']
        stage = request.form['stage']
        owner = request.form['owner']

        cursor.execute("""
        UPDATE Projects SET name = %s, client_name = %s, scale = %s, start_date = %s, location = %s, sales_person = %s, stage = %s, owner = %s
        WHERE id = %s
        """, (name, client_name, scale, start_date, location, sales_person, stage, owner, project_id))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('manage_projects'))

    cursor.execute("SELECT * FROM Projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()

    users = []
    cursor.execute("SELECT id, username FROM Users")
    users = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('edit_project.html', project=project, users=users)


@app.route('/delete_project/<int:project_id>', methods=['POST'])
def delete_project(project_id):
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("UPDATE Projects SET is_deleted = TRUE WHERE id = %s", (project_id,))
    conn.commit()

    cursor.close()
    conn.close()

    return redirect(url_for('manage_projects'))


@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        default_password = 'tianyu.123'
        hashed_password = generate_password_hash(default_password)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            cursor.execute("""
            INSERT INTO Users (username, password, is_admin)
            VALUES (%s, %s, FALSE)
            """, (username, hashed_password))

            conn.commit()
            flash(f"User {username} added successfully with default password 'tianyu.123'.")
        except mysql.connector.IntegrityError as err:
            flash(f"Failed to add user: {err}")
        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('add_user'))

    return render_template('add_user.html')


if __name__ == '__main__':
    app.run(debug=True)