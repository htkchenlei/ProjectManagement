# 项目管理系统

## 项目概述
本项目是一个基于 Flask 框架构建的项目管理系统，具备用户登录、项目管理、项目更新、用户管理等功能。系统通过与 MySQL 数据库交互，实现数据的存储和管理。

## 功能特性
1. **用户管理**
    - 用户登录和登出功能。
    - 管理员可以添加用户、管理用户权限和状态（启用/停用）。
2. **项目管理**
    - 新增项目，包括项目名称、客户名称、规模、开始日期等信息。
    - 查看项目列表，支持筛选已完成项目和分页显示。
    - 搜索项目名称，快速定位项目。
    - 查看项目详情，包括基本信息和历史更新记录。
    - 更新项目信息和添加项目更新内容。
    - 管理员可以删除项目。
3. **数据导出**
    - 支持将项目信息导出到 Excel 文件。
4. **日历功能**
    - 提供项目更新日历，可按日期查看项目更新信息。

## 技术栈
- **后端**：Flask 框架，使用 Python 编写。
- **前端**：HTML、CSS、JavaScript，结合 Bootstrap 框架实现页面布局和样式。
- **数据库**：MySQL，用于存储用户信息、项目信息和项目更新记录。

## 安装与部署

### 环境准备
- Python 3.13 或以上版本
- MySQL 数据库

### 安装依赖
克隆项目代码到本地：
```bash
git clone https://github.com/your-repo/ProjectManagement.git
cd ProjectManagement
```
创建并激活虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # 对于 Windows 用户使用 `venv\Scripts\activate`
```
安装项目依赖：
```bash
pip install -r requirements.txt
```

### 数据库配置
在 `app.py` 和 `add_user.py` 文件中，修改数据库配置信息：
```python
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'ProjectManagement'
}
```
确保 MySQL 数据库中已创建 `ProjectManagement` 数据库，并创建相应的表结构。

### 运行项目
启动 Flask 应用：
```bash
python app.py
```
在浏览器中访问 `http://127.0.0.1:5000` 即可打开项目管理系统。

## 代码结构
```
ProjectManagement/
├── .idea/                  # IDE 配置文件
├── static/                 # 静态文件，如 CSS
├── templates/              # HTML 模板文件
│   ├── admin.html          # 管理员管理面板页面
│   ├── add_project.html    # 新增项目页面
│   ├── add_user.html       # 新增用户页面
│   ├── base.html           # 基础 HTML 模板
│   ├── edit_project.html   # 编辑项目页面
│   ├── index.html          # 项目列表页面
│   ├── login.html          # 用户登录页面
│   ├── manage_users.html   # 用户管理页面
│   ├── project_details.html # 项目详情页面
│   ├── project_update.html # 项目更新页面
│   ├── search_by_date.html # 按日期搜索页面
│   ├── search_results.html # 搜索结果页面
└── app.py                  # Flask 应用主文件
└── add_user.py             # 添加用户脚本
```

## 使用说明
1. **登录**：访问系统首页，输入用户名和密码进行登录。
2. **项目管理**：登录后，普通用户可以查看和更新自己负责的项目，管理员可以管理所有项目。
3. **用户管理**：管理员可以在管理面板中添加、管理用户。
4. **数据导出**：在项目列表页面，点击“导出信息到 Excel”按钮，可将项目信息导出到 Excel 文件。
5. **日历功能**：在项目列表页面，点击“更新日历”按钮，可查看项目更新日历。

## 贡献
如果你想为这个项目做出贡献，请遵循以下步骤：
1. Fork 这个仓库。
2. 创建一个新的分支：`git checkout -b feature/your-feature`
3. 提交你的更改：`git commit -m 'Add some feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 打开一个 Pull Request。

## 许可证
本项目采用 [MIT 许可证](LICENSE)。
