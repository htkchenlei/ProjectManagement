from contextlib import nullcontext

from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
import pandas as pd
from io import BytesIO
from flask import send_file, make_response

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'ProjectManagement'
}


def get_stage_name(stage_id):
    dict = {
        '1': '立项中|初步沟通',
        '2': '立项中|提交立项申请',
        '3': '已立项|编制解决方案',
        '4': '已立项|编制设计方案',
        '5': '已立项|编制招投标参数',
        '6': '招投标|编制参数',
        '7': '招投标|已挂网',
        '8': '招投标|等待结果',
        '9': '已中标|已公示',
        '10': '已中标|已获取中标通知书',
        '11': '已中标|签署合同',
        '12': '已完成|转入项目实施'
     }

    return dict.get(stage_id, '未知阶段')


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
    if session['is_admin']:
        return redirect(url_for('manage_projects'))

    # print(session['is_admin'])

    show_completed = request.args.get('show_completed', 'true') == 'true'
    print(show_completed)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
    SELECT p.id, p.name, p.client_name, p.scale, p.stage, pp.update_content, pp.update_date, u.username AS owner_username
    FROM Projects p
    LEFT JOIN (
        SELECT project_id, MAX(update_date) AS max_date, MAX(id) AS max_id
        FROM Project_progress
        GROUP BY project_id
    ) latest_updates ON p.id = latest_updates.project_id
    LEFT JOIN Project_progress pp ON pp.id = latest_updates.max_id
    LEFT JOIN Users u ON p.owner = u.id
    WHERE p.is_deleted = FALSE AND (p.stage != '12' OR %s)
    ORDER BY pp.update_date DESC
    LIMIT 15;

    """

    params = [show_completed]

    if not session['is_admin']:
        query += " AND (p.sales_person = %s OR p.owner = %s)"
        params.extend([session['user_id'], session['user_id']])

    query += " ORDER BY pp.update_date DESC LIMIT 15;"

    cursor.execute(query, params)
    projects = cursor.fetchall()

    for i, project in enumerate(projects, start=1):
        project['serial_number'] = i
        project['stage'] = get_stage_name(project['stage'])

    cursor.close()
    conn.close()

    return render_template('index.html', projects=projects, show_completed=show_completed)


@app.route('/add_project', methods=['GET', 'POST'])
def add_project():
    if 'user_id' not in session:
        # print("check user_id")
        return redirect(url_for('index'))
    # print("today")
    today = date.today().isoformat()
    # print("after today")

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

        cursor.execute("""INSERT INTO Project_progress (project_id, update_content, update_date, updated_by)
                          VALUES (%s, %s, CURDATE(), %s)""",
                       (project_id, update_content, session['user_id']))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('index'))

    # 查询项目的基本信息
    cursor.execute("SELECT * FROM Projects WHERE id = %s", (project_id,))

    project = cursor.fetchone()
    project['stage'] = get_stage_name(project['stage'])

    # 查询项目的更新历史
    cursor.execute("""
        SELECT pp.update_content, pp.update_date, u.username
        FROM Project_progress pp
        LEFT JOIN Users u ON pp.updated_by = u.id
        WHERE pp.project_id = %s
        ORDER BY pp.id DESC
    """, (project_id,))
    updates = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('project_update.html', project=project, updates=updates)



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
    project_details[0]['stage'] = get_stage_name(project_details[0]['stage'])

    # 查询项目的更新历史
    cursor.execute("""
            SELECT pp.update_content, pp.update_date, u.username
            FROM Project_progress pp
            LEFT JOIN Users u ON pp.updated_by = u.id
            WHERE pp.project_id = %s
            ORDER BY pp.id DESC
        """, (project_id,))
    updates = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('project_details.html', project_details=project_details, updates=updates)


@app.route('/manage_projects')
def manage_projects():
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT p.id, p.name, p.client_name, p.scale, p.stage, pp.update_content, pp.update_date, u.username AS owner_username
    FROM Projects p
    LEFT JOIN (
        SELECT project_id, MAX(update_date) AS max_date, MAX(id) AS max_id
        FROM Project_progress
        GROUP BY project_id
    ) latest_updates ON p.id = latest_updates.project_id
    LEFT JOIN Project_progress pp ON pp.id = latest_updates.max_id
    LEFT JOIN Users u ON p.owner = u.id
    WHERE p.is_deleted = FALSE AND (p.stage != '12' OR 1.0)
    ORDER BY pp.update_date DESC
    LIMIT 15;
    """)

    projects = cursor.fetchall()
    for i, project in enumerate(projects, start=1):
        project['serial_number'] = i
        project['stage'] = get_stage_name(project['stage'])

    cursor.close()
    conn.close()

    return render_template('admin.html', projects=projects)


@app.route('/edit_project/<int:project_id>', methods=['GET', 'POST'])
def edit_project(project_id):
    if 'user_id' not in session:
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

        # 获取项目的旧信息
        cursor.execute("SELECT * FROM Projects WHERE id = %s", (project_id,))
        old_project = cursor.fetchone()

        # 构建更新内容
        update_content = []
        if old_project['name'] != name:
            update_content.append(f"项目名称从 {old_project['name']} 改为 {name}")
        if old_project['client_name'] != client_name:
            update_content.append(f"客户名称从 {old_project['client_name']} 改为 {client_name}")
        if old_project['scale'] != scale:
            update_content.append(f"项目规模从 {old_project['scale']} 改为 {scale}")
        if str(old_project['start_date']) != start_date:
            update_content.append(f"开始日期从 {old_project['start_date']} 改为 {start_date}")
        if old_project['location'] != location:
            update_content.append(f"项目地点从 {old_project['location']} 改为 {location}")
        if old_project['sales_person'] != sales_person:
            update_content.append(f"销售从 {old_project['sales_person']} 改为 {sales_person}")
        if old_project['stage'] != stage:
            update_content.append(f"项目阶段从 {get_stage_name(old_project['stage'])} 改为 {get_stage_name(stage)}")

        # 将更新内容拼接成字符串
        update_content_str = "; ".join(update_content)

        # 更新 Projects 表
        cursor.execute("""
        UPDATE Projects SET name = %s, client_name = %s, scale = %s, start_date = %s, location = %s, sales_person = %s, stage = %s, owner = %s
        WHERE id = %s
        """, (name, client_name, scale, start_date, location, sales_person, stage, owner, project_id))

        # 如果有更新内容，插入到 Project_progress 表
        if update_content_str:
            cursor.execute("""INSERT INTO Project_progress (project_id, update_content, update_date, updated_by)
                              VALUES (%s, %s, CURDATE(), %s)""",
                           (project_id, update_content_str, session['user_id']))

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

@app.route('/export_projects_to_excel')
def export_projects_to_excel():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
    SELECT *
    FROM (
        SELECT 
            p.id AS project_id,
            p.name AS project_name,
            p.stage AS project_stage,
            pp.update_content,
            pp.update_date,
            ROW_NUMBER() OVER (PARTITION BY p.id ORDER BY pp.update_date DESC) AS rn,
            MAX(pp.update_date) OVER (PARTITION BY p.id) AS latest_update_date
        FROM Projects p
        LEFT JOIN Project_progress pp ON p.id = pp.project_id
    ) t
    WHERE rn <= 3
    ORDER BY project_id DESC
    """

    cursor.execute(query)
    projects = cursor.fetchall()
    for project in projects:
        project['project_stage'] = get_stage_name(project['project_stage'])

    cursor.close()
    conn.close()

    df = pd.DataFrame(projects)
    # 忽略 'project_id'、'rn' 和 'latest_update_date' 字段
    if 'project_id' in df.columns:
        df.drop(columns=['project_id'], inplace=True)
    if 'rn' in df.columns:
        df.drop(columns=['rn'], inplace=True)
    if 'latest_update_date' in df.columns:
        df.drop(columns=['latest_update_date'], inplace=True)
    # 添加序号列
    df.insert(0, '序号', range(1, len(df) + 1))

    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Projects', index=False)
    writer.close()
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='projects.xlsx'
    )


@app.route('/search_results')
def search_results():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    search_term = request.args.get('search_term', '').strip()
    if not search_term:
        flash('请输入搜索关键词')
        return redirect(url_for('index'))

    show_completed = request.args.get('show_completed', 'true') == 'true'

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 构建搜索查询 (使用LIKE模糊匹配)
    query = """
    SELECT p.id, p.name, p.client_name, p.scale, p.stage, pp.update_content, pp.update_date, u.username AS owner_username
    FROM Projects p
    LEFT JOIN (
        SELECT project_id, MAX(update_date) AS max_date, MAX(id) AS max_id
        FROM Project_progress
        GROUP BY project_id
    ) latest_updates ON p.id = latest_updates.project_id
    LEFT JOIN Project_progress pp ON pp.id = latest_updates.max_id
    LEFT JOIN Users u ON p.owner = u.id
    WHERE p.is_deleted = FALSE AND p.name LIKE %s
    """

    params = [f'%{search_term}%']

    # 如果不显示已完成项目
    if not show_completed:
        query += " AND p.stage != '12'"

    # 普通用户只能看到自己的项目
    if not session['is_admin']:
        query += " AND (p.sales_person = %s OR p.owner = %s)"
        params.extend([session['user_id'], session['user_id']])

    query += " ORDER BY pp.update_date DESC"

    cursor.execute(query, params)
    projects = cursor.fetchall()

    # 处理阶段名称和序号
    for i, project in enumerate(projects, start=1):
        project['serial_number'] = i
        project['stage'] = get_stage_name(project['stage'])

    cursor.close()
    conn.close()

    return render_template('search_results.html', projects=projects, search_term=search_term,
                           show_completed=show_completed)


if __name__ == '__main__':
    app.run(debug=True)