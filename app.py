from datetime import date, datetime, timedelta
from io import BytesIO

import mysql.connector
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask import send_file
from werkzeug.security import generate_password_hash, check_password_hash

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
        print(user.get('is_enable'))
        cursor.close()
        conn.close()

        if user and check_password_hash(user['password'], password):
            if user.get('is_enable') == 0:
                flash('用户已禁用，请联系管理员')
                return redirect(url_for('login'))
            else:
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
        return redirect(url_for('admin'))

    show_completed = request.args.get('show_completed', 'true') == 'true'
    page = request.args.get('page', 1, type=int)  # 获取当前页码，默认第一页
    per_page = 15  # 每页显示条数

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 查询总项目数用于分页
    count_query = """
    SELECT COUNT(*) as total
    FROM Projects p
    WHERE p.is_deleted = FALSE AND (p.stage != '12' OR %s)
    """

    count_params = [show_completed]
    if not session['is_admin']:
        count_query += " AND (p.sales_person = %s OR p.owner = %s)"
        count_params.extend([session['user_id'], session['user_id']])

    cursor.execute(count_query, count_params)
    total = cursor.fetchone()['total']

    # 计算总页数
    total_pages = (total + per_page - 1) // per_page

    query = """
    SELECT p.id, p.name, p.client_name, p.scale, p.stage, pp.update_content, pp.update_date, pp.update_time, u.username AS owner_username
    FROM Projects p
    LEFT JOIN (
        SELECT project_id, MAX(CONCAT(update_date, ' ', update_time)) AS max_datetime, MAX(id) AS max_id
        FROM Project_progress
        GROUP BY project_id
    ) latest_updates ON p.id = latest_updates.project_id
    LEFT JOIN Project_progress pp ON pp.id = latest_updates.max_id
    LEFT JOIN Users u ON p.owner = u.id
    WHERE p.is_deleted = FALSE AND (p.stage != '12' OR %s)
    """

    params = [show_completed]

    if not session['is_admin']:
        query += " AND (p.sales_person = %s OR p.owner = %s)"
        params.extend([session['user_id'], session['user_id']])

    query += " ORDER BY latest_updates.max_datetime DESC"

    # 添加分页条件
    query += " LIMIT %s OFFSET %s"
    params.append(per_page)
    params.append((page - 1) * per_page)

    cursor.execute(query, params)
    projects = cursor.fetchall()

    for i, project in enumerate(projects, start=(page - 1) * per_page + 1):
        project['serial_number'] = i
        project['stage'] = get_stage_name(project['stage'])

        # 只对非"已完成|转入项目实施"阶段的项目计算未更新天数
        if project['stage'] != '已完成|转入项目实施':
            # 计算距离上次更新的天数
            if project['update_date']:
                if isinstance(project['update_date'], datetime):
                    project['days_since_update'] = (datetime.now().date() - project['update_date'].date()).days
                else:  # 如果是 date 类型
                    project['days_since_update'] = (date.today() - project['update_date']).days
            else:
                project['days_since_update'] = None
        else:
            # 对于已完成的项目，不需要计算未更新天数
            project['days_since_update'] = None

    cursor.close()
    conn.close()

    # 模拟分页对象
    class Pagination:
        def __init__(self, page, per_page, total, items):
            self.page = page
            self.per_page = per_page
            self.total = total
            self.items = items
            self.pages = (total + per_page - 1) // per_page

        def iter_pages(self):
            return range(1, self.pages + 1)

    pagination = Pagination(page, per_page, total, projects)

    return render_template(
        'index.html',
        projects=projects,
        show_completed=show_completed,
        page=page,
        total_pages=total_pages,
        pagination=pagination
    )


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
        sales_person = request.form['sales_person']
        stage = request.form['stage']
        owner = request.form['owner']

        # 获取地区信息
        province = request.form.get('province', '')
        city = request.form.get('city', '')
        district = request.form.get('district', '')

        # 获取location 字段值
        if province:
            if city:
                if district:
                    location = f"{province} {city} {district}"
                else:
                    location = f"{province} {city}"
            else:
                location = province
        else:
            location = ''

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
        INSERT INTO Projects (name, client_name, scale, start_date, location, sales_person, stage, owner, province, city, district)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, client_name, scale, start_date, location, sales_person, stage, owner, province, city, district))

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
        is_important = 'is_important' in request.form
        current_time = datetime.now().strftime('%H:%M:%S')

        cursor.execute("""
            INSERT INTO Project_progress (
                project_id, update_content, update_date, update_time, updated_by, is_important
                )
          VALUES (%s, %s, CURDATE(), %s, %s, %s)""",
       (project_id, update_content, current_time, session['user_id'], is_important))

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
        SELECT pp.update_content, pp.update_date, pp.update_time, pp.is_important, u.username
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
    SELECT p.*, pp.update_content, pp.update_date, pp.update_time, u.username AS updated_by_username
    FROM Projects p
    LEFT JOIN Project_progress pp ON p.id = pp.project_id
    LEFT JOIN Users u ON pp.updated_by = u.id
    WHERE p.id = %s
    ORDER BY pp.update_date DESC, pp.update_time DESC
    """, (project_id,))
    project_details = cursor.fetchall()
    project_details[0]['stage'] = get_stage_name(project_details[0]['stage'])

    # 查询项目的更新历史
    cursor.execute("""
            SELECT pp.update_content, pp.update_date, pp.update_time, u.username
            FROM Project_progress pp
            LEFT JOIN Users u ON pp.updated_by = u.id
            WHERE pp.project_id = %s
            ORDER BY pp.id DESC
        """, (project_id,))
    updates = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('project_details.html', project_details=project_details, updates=updates)


@app.route('/admin')
def admin():
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT p.id, p.name, p.client_name, p.scale, p.stage, pp.update_content, pp.update_date, pp.update_time, u.username AS owner_username
    FROM Projects p
    LEFT JOIN (
        SELECT project_id, MAX(CONCAT(update_date, ' ', update_time)) AS max_datetime, MAX(id) AS max_id
        FROM Project_progress
        GROUP BY project_id
    ) latest_updates ON p.id = latest_updates.project_id
    LEFT JOIN Project_progress pp ON pp.id = latest_updates.max_id
    LEFT JOIN Users u ON p.owner = u.id
    WHERE p.is_deleted = FALSE AND (p.stage != '12' OR 1.0)
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

    # 检查用户是否有权限编辑该项目
    cursor.execute("SELECT owner FROM Projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()

    if not project:
        flash("项目不存在")
        cursor.close()
        conn.close()
        return redirect(url_for('manage_projects'))

    # 只有项目负责人或管理员可以编辑项目
    if session['user_id'] != project['owner'] and not session.get('is_admin', False):
        flash("您没有权限编辑此项目")
        cursor.close()
        conn.close()
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form['name']
        client_name = request.form['client_name']
        scale = int(request.form['scale'])
        start_date = request.form['start_date']
        sales_person = request.form['sales_person']
        stage = request.form['stage']
        owner_username = request.form['owner']  # 获取输入的用户名

        # 获取地区信息
        province = request.form.get('province', '')
        city = request.form.get('city', '')
        district = request.form.get('district', '')

        # 根据用户名查找用户ID
        cursor.execute("SELECT id FROM Users WHERE username = %s", (owner_username,))
        owner_user = cursor.fetchone()
        if owner_user:
            owner = owner_user['id']
        else:
            # 如果找不到对应的用户，可以抛出错误或使用默认值
            flash(f"找不到用户 '{owner_username}'，请检查用户名是否正确")
            cursor.close()
            conn.close()
            return redirect(url_for('edit_project', project_id=project_id))

        # 获取项目的旧信息
        cursor.execute("SELECT * FROM Projects WHERE id = %s", (project_id,))
        old_project = cursor.fetchone()

        # 获取旧项目负责人的用户名
        old_owner_name = ''
        if old_project['owner']:
            cursor.execute("SELECT username FROM Users WHERE id = %s", (old_project['owner'],))
            owner_user = cursor.fetchone()
            if owner_user:
                old_owner_name = owner_user['username']

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
        if old_project['sales_person'] != sales_person:
            update_content.append(f"销售从 {old_project['sales_person']} 改为 {sales_person}")
        if old_project['owner'] != owner:
            # 获取新项目负责人的用户名
            update_content.append(f"项目负责人从 {old_owner_name} 改为 {owner_username}")
        if old_project['stage'] != stage:
            update_content.append(f"项目阶段从 {get_stage_name(old_project['stage'])} 改为 {get_stage_name(stage)}")
        if old_project['province'] != province:
            update_content.append(f"省份从 {old_project['province']} 改为 {province}")
        if old_project['city'] != city:
            update_content.append(f"城市从 {old_project['city']} 改为 {city}")
        if old_project['district'] != district:
            update_content.append(f"行政区从 {old_project['district']} 改为 {district}")

        # 将更新内容拼接成字符串
        update_content_str = "; ".join(update_content)

        # 更新 Projects 表
        cursor.execute("""
        UPDATE Projects 
        SET name = %s, client_name = %s, scale = %s, start_date = %s, sales_person = %s, stage = %s, owner = %s, province = %s, city = %s, district = %s
        WHERE id = %s
        """, (name, client_name, scale, start_date, sales_person, stage, owner, province, city, district, project_id))

        # 如果有更新内容，插入到 Project_progress 表
        current_time = datetime.now().strftime('%H:%M:%S')
        if update_content_str:
            cursor.execute("""INSERT INTO Project_progress (project_id, update_content, update_date, update_time, updated_by)
                              VALUES (%s, %s, CURDATE(), %s, %s)""",
                           (project_id, update_content_str, current_time, session['user_id']))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('manage_projects'))

    cursor.execute("SELECT * FROM Projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()

    # 获取项目负责人的用户名
    if project['owner']:
        cursor.execute("SELECT username FROM Users WHERE id = %s", (project['owner'],))
        owner_user = cursor.fetchone()
        if owner_user:
            project['owner_username'] = owner_user['username']

    cursor.close()
    conn.close()

    return render_template('edit_project.html', project=project)


@app.route('/delete_project/<int:project_id>', methods=['POST'])
def delete_project(project_id):
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 获取项目名称用于确认提示
    cursor.execute("SELECT name FROM Projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()

    if project:
        cursor.execute("UPDATE Projects SET is_deleted = TRUE WHERE id = %s", (project_id,))
        conn.commit()
        flash(f"项目 '{project['name']}' 已删除")

    cursor.close()
    conn.close()

    return redirect(url_for('manage_projects'))


@app.route('/deleted_projects')
def deleted_projects():
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
    SELECT p.id, p.name, p.scale, p.stage
    FROM Projects p
    WHERE p.is_deleted = TRUE
    """)
    projects = cursor.fetchall()

    for i, project in enumerate(projects, start=1):
        project['serial_number'] = i
        project['stage'] = get_stage_name(project['stage'])

    cursor.close()
    conn.close()

    return render_template('deleted_projects.html', projects=projects)


@app.route('/restore_project/<int:project_id>', methods=['POST'])
def restore_project(project_id):
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 获取项目名称
    cursor.execute("SELECT name FROM Projects WHERE id = %s", (project_id,))
    project = cursor.fetchone()

    if project:
        cursor.execute("UPDATE Projects SET is_deleted = FALSE WHERE id = %s", (project_id,))
        conn.commit()
        flash(f"项目 '{project['name']}' 已恢复")

    cursor.close()
    conn.close()

    return redirect(url_for('deleted_projects'))


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


@app.route('/manage_user')
def manage_user():
    if 'user_id' not in session or not session['is_admin']:
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 获取参数
    user_id = request.args.get('user_id')
    action = request.args.get('action')

    try:
        if user_id and action:
            cursor.execute("SELECT * FROM Users WHERE id = %s", (user_id,))
            user = cursor.fetchone()

            if not user:
                flash("用户不存在")
            else:
                if action == 'reset':
                    hashed_password = generate_password_hash('tianyu.123')
                    cursor.execute("UPDATE Users SET password = %s WHERE id = %s", (hashed_password, user_id))
                    flash("密码已重置为默认密码")

                elif action == 'disable':
                    cursor.execute("UPDATE Users SET is_enable = FALSE WHERE id = %s", (user_id,))
                    flash("账号已停用")

                elif action == 'enable':
                    cursor.execute("UPDATE Users SET is_enable = TRUE WHERE id = %s", (user_id,))
                    flash("账号已启用")

                elif action == 'promote':
                    cursor.execute("UPDATE Users SET is_admin = TRUE WHERE id = %s", (user_id,))
                    flash("用户已设为管理员")

                elif action == 'demote':
                    if user['id'] == session['user_id']:
                        flash("不能取消自己的管理员权限")
                    else:
                        cursor.execute("UPDATE Users SET is_admin = FALSE WHERE id = %s", (user_id,))
                        flash("用户已取消管理员权限")

                conn.commit()

        # 查询所有用户
        cursor.execute("SELECT * FROM Users")
        users = cursor.fetchall()

        for user in users:
            if user['is_enable'] == 0:
                user['is_enable'] = '停用'
            else:
                user['is_enable'] = '启用'

            if user['is_admin'] == 1:
                user['is_admin'] = '是'
            else:
                user['is_admin'] = '否'

    except mysql.connector.Error as err:
        flash(f"数据库错误: {err}")
        users = []

    finally:
        cursor.close()
        conn.close()

    return render_template('manage_users.html', users=users)


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


@app.route('/search_by_conditions', methods=['GET', 'POST'])
def search_by_conditions():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # 获取所有用户和阶段信息用于下拉列表
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id, username FROM Users")
    users = cursor.fetchall()

    # 获取销售人员列表
    cursor.execute("""
    SELECT DISTINCT sales_person FROM Projects WHERE sales_person IS NOT NULL AND sales_person != ''AND sales_person != '天喻同事'
    """)
    sales_persons_result = cursor.fetchall()
    sales_persons = [person['sales_person'] for person in sales_persons_result]

    # 定义阶段字典，用于前端下拉列表显示
    stages = {
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

    search_results = []

    if request.method == 'POST':
        # 获取搜索类型
        search_type = request.form.get('search_type', 'keyword')

        if search_type == 'keyword':
            # 关键字搜索
            query = """
            SELECT DISTINCT p.id as project_id, p.name as project_name, p.client_name, 
                   p.stage, p.scale, p.sales_person as sales_person_id, pp.update_content, 
                   pp.update_date, pp.update_time, u.username AS owner_username
            FROM Projects p
            LEFT JOIN Project_progress pp ON p.id = pp.project_id
            LEFT JOIN Users u ON p.owner = u.id
            WHERE p.is_deleted = FALSE
            """

            params = []

            # 关键字搜索
            keywords = request.form.get('keywords', '').strip()
            date_from = request.form.get('date_from', '')
            date_to = request.form.get('date_to', '')

            # 处理关键字搜索
            if keywords:
                keyword_list = keywords.split()
                keyword_conditions = []

                for keyword in keyword_list:
                    field_conditions = []
                    keyword_param = f"%{keyword}%"

                    field_conditions.append("p.name LIKE %s")
                    params.append(keyword_param)

                    field_conditions.append("p.client_name LIKE %s")
                    params.append(keyword_param)

                    field_conditions.append("pp.update_content LIKE %s")
                    params.append(keyword_param)

                    if field_conditions:
                        keyword_conditions.append("(" + " OR ".join(field_conditions) + ")")

                if keyword_conditions:
                    query += " AND (" + " AND ".join(keyword_conditions) + ")"

            # 处理日期范围
            if date_from:
                query += " AND pp.update_date >= %s"
                params.append(date_from)

            if date_to:
                query += " AND pp.update_date <= %s"
                params.append(date_to)

            # 普通用户只能看到自己的项目
            if not session['is_admin']:
                query += " AND (p.sales_person = %s OR p.owner = %s)"
                params.extend([session['user_id'], session['user_id']])

            query += " ORDER BY pp.update_date DESC, pp.update_time DESC"


        else:

            # 条件搜索 - 修改查询以避免重复项目
            query = """
            SELECT p.id as project_id, p.name as project_name, p.client_name, 
                   p.stage, p.scale, p.sales_person, 
                   latest_pp.update_content, latest_pp.update_date, latest_pp.update_time,
                   u.username AS owner_username
            FROM Projects p
            LEFT JOIN (
                SELECT project_id, update_content, update_date, update_time,
                       ROW_NUMBER() OVER (PARTITION BY project_id ORDER BY update_date DESC, update_time DESC) as rn
                FROM Project_progress
            ) latest_pp ON p.id = latest_pp.project_id AND latest_pp.rn = 1
            LEFT JOIN Users u ON p.owner = u.id
            WHERE p.is_deleted = FALSE
            """

            params = []

            # 条件搜索
            owner = request.form.get('owner', '')
            stage = request.form.get('stage', '')
            sales_person = request.form.get('sales_person', '')
            amount_range = request.form.get('amount_range', '')

            # 处理项目负责人
            if owner:
                query += " AND p.owner = %s"
                params.append(owner)

            # 处理销售人员
            if sales_person:
                query += " AND p.sales_person = %s"
                params.append(sales_person)

            # 处理项目阶段
            if stage:
                if stage == '1':
                    # 立项中相关的阶段ID: 1, 2
                    query += " AND p.stage IN (1, 2)"
                elif stage == '2':
                    # 已立项相关的阶段ID: 3, 4, 5
                    query += " AND p.stage IN (3, 4, 5)"
                elif stage == '3':
                    # 招投标相关的阶段ID: 6, 7, 8
                    query += " AND p.stage IN (6, 7, 8)"
                elif stage == '4':
                    # 已中标相关的阶段ID: 9, 10, 11
                    query += " AND p.stage IN (9, 10, 11)"
                elif stage == '5':
                    # 已完成相关的阶段ID: 12
                    query += " AND p.stage = 12"
                else:
                    # 如果是具体的阶段ID，则直接匹配
                    query += " AND p.stage = %s"
                    params.append(stage)

            # 处理金额范围 (单位: 万元)
            if amount_range:
                if amount_range == '0-100':
                    query += " AND p.scale >= %s AND p.scale < %s"
                    params.extend([0, 100])

                elif amount_range == '100-500':
                    query += " AND p.scale >= %s AND p.scale < %s"
                    params.extend([100, 500])

                elif amount_range == '500-1000':
                    query += " AND p.scale >= %s AND p.scale < %s"
                    params.extend([500, 1000])

                elif amount_range == '1000-':
                    query += " AND p.scale >= %s"
                    params.append(1000)

            # 普通用户只能看到自己的项目
            if not session['is_admin']:
                query += " AND (p.sales_person = %s OR p.owner = %s)"
                params.extend([session['user_id'], session['user_id']])

            query += " ORDER BY latest_pp.update_date DESC, latest_pp.update_time DESC"

        try:
            cursor.execute(query, params)
            results = cursor.fetchall()

            # 处理阶段名称
            for result in results:
                result['stage_name'] = get_stage_name(result['stage'])

            search_results = results

        except mysql.connector.Error as err:
            flash(f"搜索出错: {err}")

    cursor.close()
    conn.close()

    return render_template('search_by_conditions.html',
                           users=users,
                           sales_persons=sales_persons,
                           stages=stages,
                           search_results=search_results)



@app.route('/search_by_date', methods=['GET', 'POST'])
def search_by_date():
    if 'user_id' not in session:
        return redirect(url_for('login'))

        # 获取当前日期作为默认值
    today = date.today().strftime('%Y-%m-%d')
    selected_date_str = request.args.get('date', today)

    # 解析日期参数
    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d')
    except ValueError:
        selected_date = datetime.today()
        selected_date_str = selected_date.strftime('%Y-%m-%d')

    # 计算前一个月和后一个月的日期
    prev_month_date = selected_date.replace(day=1) - timedelta(days=1)
    next_month_date = (selected_date.replace(day=28) + timedelta(days=4)).replace(day=1)

    # 获取当前月份的第一天和最后一天
    first_day = selected_date.replace(day=1)
    last_day = (first_day.replace(month=first_day.month + 1) if first_day.month < 12
                else first_day.replace(year=first_day.year + 1, month=1)).replace(day=1) - timedelta(days=1)

    # 查询指定日期的项目更新
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
            SELECT p.name, pp.update_content, pp.update_date, pp.update_time
            FROM Projects p
            JOIN Project_progress pp ON p.id = pp.project_id
            WHERE pp.update_date = %s
        """, (selected_date_str,))
    updates = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('search_by_date.html',
                           selected_date=selected_date_str,
                           selected_year=selected_date.year,
                           selected_month=selected_date.month,
                           first_day=first_day,
                           last_day=last_day,
                           updates=updates,
                           prev_month=prev_month_date.strftime('%Y-%m-%d'),
                           next_month=next_month_date.strftime('%Y-%m-%d'),
                           today=today)


@app.route('/statistics')
def statistics():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 查询各省份项目金额统计 (使用province字段)
    cursor.execute("""
        SELECT province, SUM(scale) as total_scale
        FROM Projects 
        WHERE is_deleted = FALSE AND province IS NOT NULL AND province != ''
        GROUP BY province
        ORDER BY total_scale DESC
    """)
    province_data = cursor.fetchall()

    # 查询各阶段项目数量统计（按新分类）
    stage_categories = {
        '立项中': [1, 2],
        '已立项': [3, 4, 5],
        '招投标': [6, 7, 8],
        '已中标': [9, 10, 11],
        '已完成': [12]
    }

    stage_data = []
    for category, stage_ids in stage_categories.items():
        format_strings = ','.join(['%s'] * len(stage_ids))
        query = f"""
            SELECT COUNT(*) as project_count
            FROM Projects 
            WHERE is_deleted = FALSE AND stage IN ({format_strings})
        """
        cursor.execute(query, tuple(stage_ids))
        result = cursor.fetchone()
        stage_data.append({
            'stage_name': category,
            'project_count': result['project_count']
        })

    # 查询每月新增项目数量
    cursor.execute("""
        SELECT 
            DATE_FORMAT(start_date, '%Y-%m') as month,
            COUNT(*) as project_count
        FROM Projects 
        WHERE is_deleted = FALSE
        GROUP BY DATE_FORMAT(start_date, '%Y-%m')
        ORDER BY month
    """)
    monthly_data = cursor.fetchall()

    # 查询项目规模分布
    cursor.execute("""
        SELECT 
            CASE 
                WHEN scale < 100 THEN '小型项目 (<100万)'
                WHEN scale BETWEEN 100 AND 500 THEN '中型项目 (100-500万)'
                WHEN scale BETWEEN 501 AND 1000 THEN '大型项目 (501-1000万)'
                ELSE '超大型项目 (>1000万)'
            END as scale_range,
            COUNT(*) as project_count
        FROM Projects 
        WHERE is_deleted = FALSE
        GROUP BY 
            CASE 
                WHEN scale < 100 THEN '小型项目 (小雨100万)'
                WHEN scale BETWEEN 100 AND 500 THEN '中型项目 (100-500万)'
                WHEN scale BETWEEN 501 AND 1000 THEN '大型项目 (501-1000万)'
                ELSE '超大型项目 (>1000万)'
            END
        ORDER BY MIN(scale)
    """)
    scale_distribution = cursor.fetchall()

    # 新增：查询各省份项目数量统计 (使用province字段)
    cursor.execute("""
        SELECT province, COUNT(*) as project_count
        FROM Projects 
        WHERE is_deleted = FALSE AND province IS NOT NULL AND province != ''
        GROUP BY province
        ORDER BY project_count DESC
    """)
    province_count_data = cursor.fetchall()

    # 新增：查询每周更新数量
    cursor.execute("""
        SELECT 
            YEAR(update_date) as year,
            WEEK(update_date, 1) as week,
            COUNT(*) as update_count
        FROM Project_progress 
        WHERE update_date IS NOT NULL
        GROUP BY YEAR(update_date), WEEK(update_date, 1)
        ORDER BY year, week
        LIMIT 20
    """)
    weekly_update_data = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('statistics.html',
                           province_data=province_data,
                           stage_data=stage_data,
                           monthly_data=monthly_data,
                           scale_distribution=scale_distribution,
                           province_count_data=province_count_data,
                           weekly_update_data=weekly_update_data)


if __name__ == '__main__':
    app.run(debug=True)