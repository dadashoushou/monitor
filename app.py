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
import re
import requests
import feedparser
from urllib.parse import urljoin
from apscheduler.schedulers.background import BackgroundScheduler
from crawler import crawl_site as _crawl_site, crawl_all as _crawl_all

app = Flask(__name__)

DATA_FILE = Path(__file__).parent / 'sites.json'
CONFIG_FILE = Path(__file__).parent / 'config.json'
DATA_DIR = Path(__file__).parent / 'data'

# 抓取状态
crawl_state = {
    'running': False,
    'total': 0,
    'done': 0,
    'current': '',
    'last_run': None,
}
crawl_lock = threading.Lock()


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {'crawl_interval_hours': 6}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(cfg: dict):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def run_crawl_all():
    global crawl_state
    sites = load_sites()
    with crawl_lock:
        if crawl_state['running']:
            return
        crawl_state = {
            'running': True,
            'total': len(sites),
            'done': 0,
            'current': '',
            'last_run': crawl_state.get('last_run'),
        }
    for i, site in enumerate(sites):
        with crawl_lock:
            crawl_state['current'] = site['name']
        _crawl_site(site)
        with crawl_lock:
            crawl_state['done'] = i + 1
    with crawl_lock:
        crawl_state['running'] = False
        crawl_state['last_run'] = datetime.now().isoformat(timespec='seconds')


scheduler = BackgroundScheduler()


def _start_scheduler():
    cfg = load_config()
    hours = cfg.get('crawl_interval_hours', 6)
    scheduler.add_job(run_crawl_all, 'interval', hours=hours, id='crawl_job')
    scheduler.start()


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


HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; RSS-checker/1.0)'}
RSS_PATHS = ['feed', 'feed/', 'rss', 'rss/', 'rss.xml', 'feed.xml', 'atom.xml', 'index.xml']


def _is_valid_feed(url, timeout=5):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            return False
        ct = r.headers.get('Content-Type', '')
        if any(x in ct for x in ['rss', 'atom', 'xml', 'feed']):
            return len(feedparser.parse(r.content).entries) > 0
        if '<rss' in r.text[:500] or '<feed' in r.text[:500]:
            return len(feedparser.parse(r.content).entries) > 0
    except Exception:
        pass
    return False


def _detect_rss(root_url, timeout=5):
    """返回 (rss_url_or_None, status_string)"""
    try:
        r = requests.get(root_url, headers=HEADERS, timeout=timeout)
        for pattern in [
            r'<link[^>]+(?:application/rss\+xml|application/atom\+xml)[^>]+href=["\']([^"\']+)["\']',
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]+(?:application/rss\+xml|application/atom\+xml)',
        ]:
            matches = re.findall(pattern, r.text, re.IGNORECASE)
            if matches:
                feed_url = matches[0]
                if not feed_url.startswith('http'):
                    feed_url = urljoin(root_url, feed_url)
                if _is_valid_feed(feed_url, timeout):
                    return feed_url, 'rss'
    except Exception:
        pass

    for path in RSS_PATHS:
        candidate = urljoin(root_url, path)
        if _is_valid_feed(candidate, timeout):
            return candidate, 'rss'

    return None, 'no_rss'


def _check_one(site):
    try:
        rss_url, status = _detect_rss(site['url'])
        site['rss_url'] = rss_url
        site['status'] = status
    except requests.Timeout:
        site['status'] = 'timeout'
    except Exception:
        site['status'] = 'error'
    site['last_checked'] = datetime.now().isoformat(timespec='seconds')
    return site


def _run_check_all():
    global check_state
    sites = load_sites()
    with check_lock:
        check_state = {'running': True, 'total': len(sites), 'done': 0, 'current': ''}

    for i, site in enumerate(sites):
        with check_lock:
            check_state['current'] = site['name']
        _check_one(site)
        sites_data = load_sites()
        for j, s in enumerate(sites_data):
            if s['id'] == site['id']:
                sites_data[j] = site
                break
        save_sites(sites_data)
        with check_lock:
            check_state['done'] = i + 1

    with check_lock:
        check_state['running'] = False


@app.route('/api/check', methods=['POST'])
def check_all():
    with check_lock:
        if check_state['running']:
            return jsonify({'error': '检测正在进行中'}), 409
    t = threading.Thread(target=_run_check_all, daemon=True)
    t.start()
    return jsonify({'ok': True})


@app.route('/api/check/status', methods=['GET'])
def check_status():
    with check_lock:
        return jsonify(dict(check_state))


@app.route('/api/check/<site_id>', methods=['POST'])
def check_one_route(site_id):
    sites = load_sites()
    for i, site in enumerate(sites):
        if site['id'] == site_id:
            _check_one(site)
            sites[i] = site
            save_sites(sites)
            return jsonify(site)
    return jsonify({'error': '未找到'}), 404


@app.route('/api/crawl', methods=['POST'])
def crawl_all_route():
    with crawl_lock:
        if crawl_state['running']:
            return jsonify({'error': '抓取正在进行中'}), 409
    t = threading.Thread(target=run_crawl_all, daemon=True)
    t.start()
    return jsonify({'ok': True})


@app.route('/api/crawl/<site_id>', methods=['POST'])
def crawl_one_route(site_id):
    sites = load_sites()
    site = next((s for s in sites if s['id'] == site_id), None)
    if not site:
        return jsonify({'error': '未找到'}), 404
    result = _crawl_site(site)
    return jsonify(result if result else {'count': 0})


@app.route('/api/crawl/status', methods=['GET'])
def crawl_status():
    with crawl_lock:
        return jsonify(dict(crawl_state))


@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(load_config())


@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.get_json()
    cfg = load_config()
    if 'crawl_interval_hours' in data:
        hours = int(data['crawl_interval_hours'])
        cfg['crawl_interval_hours'] = hours
        save_config(cfg)
        if scheduler.get_job('crawl_job'):
            scheduler.reschedule_job('crawl_job', trigger='interval', hours=hours)
    return jsonify(cfg)


@app.route('/api/results/<site_id>', methods=['GET'])
def get_results(site_id):
    if not DATA_DIR.exists():
        return jsonify([])
    files = sorted(DATA_DIR.glob(f'*_{site_id}.json'), reverse=True)
    result = []
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            result.append({
                'filename': f.name,
                'crawled_at': data.get('crawled_at', ''),
                'count': data.get('count', 0),
                'method': data.get('method', ''),
            })
        except Exception:
            pass
    return jsonify(result)


@app.route('/api/results/<site_id>/<filename>', methods=['GET'])
def get_result_file(site_id, filename):
    if not re.match(r'^[\w\-\.]+$', filename):
        return jsonify({'error': '非法文件名'}), 400
    filepath = DATA_DIR / filename
    if not filepath.exists():
        return jsonify({'error': '未找到'}), 404
    with open(filepath, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))


if __name__ == '__main__':
    _start_scheduler()
    app.run(debug=True, port=5000)
