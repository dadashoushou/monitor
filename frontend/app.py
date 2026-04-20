"""
OpenMonitor 前端阅读器
运行: python app.py
访问: http://localhost:5001
"""
import json
import threading
import requests as http_requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, render_template
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / 'config.json'
STATE_FILE = BASE_DIR / 'state.json'
TRANSLATIONS_DIR = BASE_DIR / 'translations'
MIN_SCAN_INTERVAL_MINUTES = 5
DEFAULT_CONFIG = {
    'data_dir': '',
    'scan_interval_minutes': MIN_SCAN_INTERVAL_MINUTES,
    'port': 5001,
}

state_lock = threading.Lock()

# ── 配置 / 状态 持久化 ─────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        cfg = dict(DEFAULT_CONFIG)
        cfg.update(json.load(f))
        return cfg


def save_config(cfg: dict):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _parse_scan_interval_minutes(raw_value) -> int:
    try:
        minutes = int(raw_value)
    except (TypeError, ValueError):
        raise ValueError('扫描间隔必须是整数分钟')
    if minutes < MIN_SCAN_INTERVAL_MINUTES:
        raise ValueError(f'扫描间隔不能小于 {MIN_SCAN_INTERVAL_MINUTES} 分钟')
    return minutes


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

def _parse_json_file(filepath: Path) -> List[Dict[str, Any]]:
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
            item['source_file'] = filepath.name
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

def _normalize_trash_scope(raw_scope: Optional[str]) -> str:
    scope = (raw_scope or 'today').strip().lower()
    return scope if scope in {'today', 'yesterday', 'earlier'} else 'today'


def _parse_deleted_at(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _filter_deleted_articles_by_scope(
    articles: List[Dict[str, Any]], scope: str
) -> List[Dict[str, Any]]:
    scope = _normalize_trash_scope(scope)
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    filtered = []

    for article in articles:
        if not article.get('deleted'):
            continue

        deleted_at = _parse_deleted_at(article.get('deleted_at'))
        if deleted_at is None:
            if scope == 'earlier':
                filtered.append(article)
            continue

        deleted_date = deleted_at.date()
        if scope == 'today' and deleted_date == today:
            filtered.append(article)
        elif scope == 'yesterday' and deleted_date == yesterday:
            filtered.append(article)
        elif scope == 'earlier' and deleted_date < yesterday:
            filtered.append(article)

    return filtered


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
    items = []
    for offset, article in enumerate(active[start:start + size], start=1):
        item = dict(article)
        item['display_seq'] = start + offset
        items.append(item)

    return jsonify({'items': items, 'total': total, 'page': page, 'size': size})


@app.route('/api/trash')
def get_trash():
    page = request.args.get('page', 1, type=int)
    size = request.args.get('size', 50, type=int)
    q = request.args.get('q', '').strip()
    scope = _normalize_trash_scope(request.args.get('scope', 'today'))

    with state_lock:
        st = load_state()

    deleted = _filter_deleted_articles_by_scope(st['articles'], scope)
    if q:
        deleted = [a for a in deleted if q in a.get('title', '')]
    deleted.sort(key=lambda a: a.get('deleted_at') or '', reverse=True)

    total = len(deleted)
    start = (page - 1) * size
    items = []
    for offset, article in enumerate(deleted[start:start + size], start=1):
        item = dict(article)
        item['display_seq'] = start + offset
        items.append(item)

    return jsonify({'items': items, 'total': total, 'page': page, 'size': size, 'scope': scope})


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
        'scan_interval_minutes': cfg.get('scan_interval_minutes', MIN_SCAN_INTERVAL_MINUTES),
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
    scan_interval_minutes = None
    if 'data_dir' in data:
        raw = str(data['data_dir']).strip()
        if raw and not Path(raw).exists():
            return jsonify({'error': '路径不存在'}), 400
        cfg['data_dir'] = raw
    if 'scan_interval_minutes' in data:
        try:
            scan_interval_minutes = _parse_scan_interval_minutes(data['scan_interval_minutes'])
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        cfg['scan_interval_minutes'] = scan_interval_minutes
    save_config(cfg)
    if scan_interval_minutes is not None:
        refresh_scan_schedule(scan_interval_minutes)
    return jsonify(cfg)


@app.route('/api/ai-config', methods=['GET'])
def get_ai_config():
    cfg = load_config()
    ai = cfg.get('ai', {})
    return jsonify({
        'api_url': ai.get('api_url', ''),
        'api_key': ai.get('api_key', ''),
        'model': ai.get('model', ''),
    })


@app.route('/api/ai-config', methods=['POST'])
def update_ai_config():
    data = request.get_json()
    api_url = str(data.get('api_url', '')).strip()
    api_key = str(data.get('api_key', '')).strip()
    model = str(data.get('model', '')).strip()
    if not api_url or not api_key or not model:
        return jsonify({'error': '请填写完整的 AI 配置'}), 400
    cfg = load_config()
    cfg['ai'] = {'api_url': api_url, 'api_key': api_key, 'model': model}
    save_config(cfg)
    return jsonify(cfg['ai'])


@app.route('/api/translate', methods=['POST'])
def translate():
    cfg = load_config()
    ai = cfg.get('ai', {})
    if not ai.get('api_url') or not ai.get('api_key') or not ai.get('model'):
        return jsonify({'error': '未配置 AI'}), 400

    data = request.get_json()
    titles = data.get('titles', [])
    if not titles:
        return jsonify({'results': []})

    api_url = ai['api_url'].rstrip('/')
    if not api_url.endswith('/chat/completions'):
        if api_url.endswith('/v1'):
            api_url += '/chat/completions'
        else:
            api_url += '/v1/chat/completions'

    results = []
    for title in titles:
        try:
            resp = http_requests.post(
                api_url,
                json={
                    'model': ai['model'],
                    'messages': [
                        {'role': 'system', 'content': '你是一个专业的翻译助手，请将用户提供的英文标题翻译成中文。只返回翻译结果，不要添加任何解释。'},
                        {'role': 'user', 'content': '请翻译以下标题：' + title},
                    ],
                    'temperature': 0.3,
                },
                headers={
                    'Authorization': f'Bearer {ai["api_key"]}',
                    'Content-Type': 'application/json',
                },
                timeout=30,
            )
            resp.raise_for_status()
            translated = resp.json()['choices'][0]['message']['content'].strip()
            results.append(translated)
        except Exception:
            results.append(title)

    return jsonify({'results': results})


# ── 翻译文件持久化 ───────────────────────────────────────────

@app.route('/api/translations/<path:filename>')
def get_translations(filename):
    safe_name = Path(filename).name
    trans_file = TRANSLATIONS_DIR / f'trans_{safe_name}'
    if not trans_file.exists():
        return jsonify({})
    with open(trans_file, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))


@app.route('/api/translations/<path:filename>', methods=['POST'])
def save_translations(filename):
    safe_name = Path(filename).name
    TRANSLATIONS_DIR.mkdir(exist_ok=True)
    trans_file = TRANSLATIONS_DIR / f'trans_{safe_name}'
    new_data = request.get_json() or {}
    existing = {}
    if trans_file.exists():
        with open(trans_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    existing.update(new_data)
    with open(trans_file, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    return jsonify({'ok': True, 'count': len(new_data)})


# ── 启动 ───────────────────────────────────────────────────

scheduler = BackgroundScheduler()


def refresh_scan_schedule(minutes: int):
    if scheduler.get_job('scan_job'):
        scheduler.reschedule_job('scan_job', trigger='interval', minutes=minutes)
    elif scheduler.running:
        scheduler.add_job(scan_data_dir, 'interval', minutes=minutes, id='scan_job')


def _start_scheduler():
    cfg = load_config()
    minutes = cfg.get('scan_interval_minutes', MIN_SCAN_INTERVAL_MINUTES)
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
