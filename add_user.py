from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash


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


def insert_admin_user(username):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    hashed_password = generate_password_hash('tianyu.123')
    cursor.execute("""
        INSERT INTO Users (username, password, is_admin)
        VALUES (%s, %s, TRUE)
        """, (username, hashed_password))

    conn.commit()

    cursor.close()
    conn.close()

insert_admin_user(username='Chenlei')