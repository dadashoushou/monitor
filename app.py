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


@app.route('/api/sites', methods=['GET'])
def get_sites():
    return jsonify(load_sites())


@app.route('/api/sites', methods=['POST'])
def add_site():
    data = request.get_json()
    if not data.get('name') or not data.get('url'):
        return jsonify({'error': '名称和URL不能为空'}), 400
    sites = load_sites()
    site = {
        'id': str(uuid.uuid4()),
        'name': data['name'].strip(),
        'url': data['url'].strip(),
        'note': data.get('note', '').strip(),
        'rss_url': None,
        'status': 'pending',
        'last_checked': None,
    }
    sites.append(site)
    save_sites(sites)
    return jsonify(site), 201


@app.route('/api/sites/<site_id>', methods=['PUT'])
def update_site(site_id):
    data = request.get_json()
    sites = load_sites()
    for site in sites:
        if site['id'] == site_id:
            if data.get('name'):
                site['name'] = data['name'].strip()
            if data.get('url'):
                site['url'] = data['url'].strip()
            site['note'] = data.get('note', site.get('note', '')).strip()
            save_sites(sites)
            return jsonify(site)
    return jsonify({'error': '未找到'}), 404


@app.route('/api/sites/<site_id>', methods=['DELETE'])
def delete_site(site_id):
    sites = load_sites()
    new_sites = [s for s in sites if s['id'] != site_id]
    if len(new_sites) == len(sites):
        return jsonify({'error': '未找到'}), 404
    save_sites(new_sites)
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
