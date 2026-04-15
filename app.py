"""
openmonitor 后端管理界面
运行: python app.py
访问: http://localhost:5000
"""
import json
import uuid
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

DATA_FILE = Path(__file__).parent / 'sites.json'

# 全局检测状态
check_state = {
    'running': False,
    'total': 0,
    'done': 0,
    'current': '',
}
check_lock = threading.Lock()


def load_sites():
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_sites(sites):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)


@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
