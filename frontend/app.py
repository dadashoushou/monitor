"""
OpenMonitor 前端阅读器
运行: python app.py
访问: http://localhost:5001
"""
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, render_template
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / 'config.json'
STATE_FILE = BASE_DIR / 'state.json'

state_lock = threading.Lock()

# ── 配置 / 状态 持久化 ─────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {'data_dir': '', 'scan_interval_minutes': 5, 'port': 5001}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(cfg: dict):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {'read_files': [], 'articles': [], 'next_seq': 1,
                'last_scan': None, 'last_new_count': 0}
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_state(st: dict):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(st, f, ensure_ascii=False, indent=2)

# ── JSON 文件扫描 ──────────────────────────────────────────

def _parse_json_file(filepath: Path) -> list[dict]:
    """解析后端输出的 JSON 文件，返回统一格式的 article 列表"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    articles = []
    if 'sites' in data:
        for site in data['sites']:
            for item in site.get('items', []):
                articles.append({
                    'title': item.get('title', ''),
                    'url': item.get('url', ''),
                    'published': item.get('published'),
                    'crawled_at': item.get('crawled_at', ''),
                    'source_site': site.get('site_name', ''),
                    'source_url': site.get('site_url', ''),
                })
    elif 'items' in data:
        for item in data['items']:
            articles.append({
                'title': item.get('title', ''),
                'url': item.get('url', ''),
                'published': item.get('published'),
                'crawled_at': item.get('crawled_at', ''),
                'source_site': data.get('site_name', ''),
                'source_url': data.get('site_url', ''),
            })
    return articles


def scan_data_dir():
    """扫描 data_dir，处理新 JSON 文件"""
    cfg = load_config()
    data_dir = cfg.get('data_dir', '').strip()
    if not data_dir:
        return
    data_path = Path(data_dir)
    if not data_path.exists():
        return

    with state_lock:
        st = load_state()

    read_set = set(st['read_files'])
    json_files = sorted(data_path.glob('*.json'))
    new_files = [f for f in json_files if f.name not in read_set]

    if not new_files:
        with state_lock:
            st['last_scan'] = datetime.now().isoformat(timespec='seconds')
            save_state(st)
        return

    new_count = 0
    next_seq = st['next_seq']
    for filepath in new_files:
        try:
            items = _parse_json_file(filepath)
        except Exception:
            continue
        for item in items:
            item['seq'] = next_seq
            item['deleted'] = False
            item['deleted_at'] = None
            st['articles'].append(item)
            next_seq += 1
            new_count += 1
        read_set.add(filepath.name)

    with state_lock:
        st['read_files'] = sorted(read_set)
        st['next_seq'] = next_seq
        st['last_scan'] = datetime.now().isoformat(timespec='seconds')
        st['last_new_count'] = new_count
        save_state(st)


# ── 回收站清理 ─────────────────────────────────────────────

def cleanup_trash():
    """每周一清理上周一至周五的回收站数据"""
    today = datetime.now()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_friday = last_monday + timedelta(days=4, hours=23, minutes=59, seconds=59)

    with state_lock:
        st = load_state()
        before = len(st['articles'])
        st['articles'] = [
            a for a in st['articles']
            if not (a.get('deleted') and a.get('deleted_at')
                    and last_monday.isoformat() <= a['deleted_at'] <= last_friday.isoformat())
        ]
        save_state(st)


# ── API 路由 ───────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/articles')
def get_articles():
    page = request.args.get('page', 1, type=int)
    size = request.args.get('size', 50, type=int)
    q = request.args.get('q', '').strip()

    with state_lock:
        st = load_state()

    active = [a for a in st['articles'] if not a.get('deleted')]
    if q:
        active = [a for a in active if q in a.get('title', '')]
    active.sort(key=lambda a: a.get('crawled_at') or '', reverse=True)

    total = len(active)
    start = (page - 1) * size
    items = active[start:start + size]

    return jsonify({'items': items, 'total': total, 'page': page, 'size': size})


@app.route('/api/trash')
def get_trash():
    page = request.args.get('page', 1, type=int)
    size = request.args.get('size', 50, type=int)
    q = request.args.get('q', '').strip()

    with state_lock:
        st = load_state()

    deleted = [a for a in st['articles'] if a.get('deleted')]
    if q:
        deleted = [a for a in deleted if q in a.get('title', '')]
    deleted.sort(key=lambda a: a.get('deleted_at') or '', reverse=True)

    total = len(deleted)
    start = (page - 1) * size
    items = deleted[start:start + size]

    return jsonify({'items': items, 'total': total, 'page': page, 'size': size})


@app.route('/api/articles/batch-delete', methods=['POST'])
def batch_delete():
    data = request.get_json()
    seqs = set(data.get('seqs', []))
    if not seqs:
        return jsonify({'error': '未选择'}), 400
    now = datetime.now().isoformat(timespec='seconds')
    with state_lock:
        st = load_state()
        count = 0
        for a in st['articles']:
            if a['seq'] in seqs and not a.get('deleted'):
                a['deleted'] = True
                a['deleted_at'] = now
                count += 1
        save_state(st)
    return jsonify({'ok': True, 'deleted': count})


@app.route('/api/articles/<int:seq>/delete', methods=['POST'])
def delete_article(seq):
    with state_lock:
        st = load_state()
        for a in st['articles']:
            if a['seq'] == seq and not a.get('deleted'):
                a['deleted'] = True
                a['deleted_at'] = datetime.now().isoformat(timespec='seconds')
                save_state(st)
                return jsonify({'ok': True})
    return jsonify({'error': '未找到'}), 404


@app.route('/api/trash/batch-restore', methods=['POST'])
def batch_restore():
    data = request.get_json()
    seqs = set(data.get('seqs', []))
    if not seqs:
        return jsonify({'error': '未选择'}), 400
    with state_lock:
        st = load_state()
        count = 0
        for a in st['articles']:
            if a['seq'] in seqs and a.get('deleted'):
                a['deleted'] = False
                a['deleted_at'] = None
                count += 1
        save_state(st)
    return jsonify({'ok': True, 'restored': count})


@app.route('/api/trash/<int:seq>/restore', methods=['POST'])
def restore_article(seq):
    with state_lock:
        st = load_state()
        for a in st['articles']:
            if a['seq'] == seq and a.get('deleted'):
                a['deleted'] = False
                a['deleted_at'] = None
                save_state(st)
                return jsonify({'ok': True})
    return jsonify({'error': '未找到'}), 404


@app.route('/api/trash/cleanup', methods=['POST'])
def manual_cleanup():
    cleanup_trash()
    return jsonify({'ok': True})


@app.route('/api/status')
def get_status():
    with state_lock:
        st = load_state()
    cfg = load_config()
    active_count = sum(1 for a in st['articles'] if not a.get('deleted'))
    trash_count = sum(1 for a in st['articles'] if a.get('deleted'))
    return jsonify({
        'last_scan': st.get('last_scan'),
        'last_new_count': st.get('last_new_count', 0),
        'total_articles': active_count,
        'trash_count': trash_count,
        'data_dir': cfg.get('data_dir', ''),
    })


@app.route('/api/scan', methods=['POST'])
def trigger_scan():
    scan_data_dir()
    return jsonify({'ok': True})


@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(load_config())


@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.get_json()
    cfg = load_config()
    if 'data_dir' in data:
        raw = str(data['data_dir']).strip()
        if raw and not Path(raw).exists():
            return jsonify({'error': '路径不存在'}), 400
        cfg['data_dir'] = raw
    save_config(cfg)
    return jsonify(cfg)


# ── 启动 ───────────────────────────────────────────────────

scheduler = BackgroundScheduler()


def _start_scheduler():
    cfg = load_config()
    minutes = cfg.get('scan_interval_minutes', 5)
    scheduler.add_job(scan_data_dir, 'interval', minutes=minutes, id='scan_job')
    scheduler.add_job(cleanup_trash, 'cron', day_of_week='mon', hour=0, minute=0, id='cleanup_job')
    scheduler.start()


if __name__ == '__main__':
    import os
    scan_data_dir()
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        _start_scheduler()
    cfg = load_config()
    app.run(debug=True, port=cfg.get('port', 5001))
