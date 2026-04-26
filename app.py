"""
openmonitor 后端管理界面
运行: python app.py
访问: http://localhost:5000
"""
import json
import uuid
import threading
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, request, render_template
import re
import requests
import urllib3
import feedparser
from urllib.parse import urljoin
from apscheduler.schedulers.background import BackgroundScheduler
from crawler import crawl_site as _crawl_site, crawl_all as _crawl_all
from ai_analyzer import analyze_page as _analyze_page
from mirror_store import filter_new_items, ingest_snapshot, update_site_index

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

DATA_FILE = Path(__file__).parent / 'sites.json'
CONFIG_FILE = Path(__file__).parent / 'config.json'

# 抓取状态
crawl_state = {
    'running': False,
    'total': 0,
    'done': 0,
    'current': '',
    'last_run': None,
}
crawl_lock = threading.Lock()

# AI 分析状态
analyze_state = {
    'running': False,
    'site_id': None,
    'site_name': '',
    'step': '',
    'message': '',
    'error': None,
    'result': None,
}
analyze_lock = threading.Lock()

crawl_state = {
    'running': False,
    'total': 0,
    'done': 0,
    'current': '',
    'last_run': None,
    'stopped': False,
}
crawl_stop_event = threading.Event()

analyze_state = {
    'running': False,
    'site_id': None,
    'site_name': '',
    'step': '',
    'message': '',
    'error': None,
    'result': None,
}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {'crawl_interval_hours': 1, 'scheduler_on': True}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(cfg: dict):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_crawl_interval_hours(cfg: dict | None = None) -> int:
    cfg = cfg or load_config()
    try:
        hours = int(cfg.get('crawl_interval_hours', 1))
    except (TypeError, ValueError):
        return 1
    return min(max(hours, 1), 12)


def is_scheduler_enabled(cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    return bool(cfg.get('scheduler_on', True))


_DEFAULT_DATA_DIR = Path(__file__).parent / 'data'
_DEFAULT_MIRROR_DATA_DIR = Path(__file__).parent / 'history_mirror'
_SNAPSHOT_FILENAME_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})_[\w\-]+\.json$')
_mirror_init_lock = threading.Lock()
_mirror_initialized = False


def get_data_dir() -> Path:
    """从 config 读取 data_dir，空则返回默认路径"""
    cfg = load_config()
    raw = cfg.get('data_dir', '').strip()
    return Path(raw) if raw else _DEFAULT_DATA_DIR


def get_mirror_data_dir() -> Path:
    cfg = load_config()
    raw = cfg.get('mirror_data_dir', '').strip()
    return Path(raw) if raw else _DEFAULT_MIRROR_DATA_DIR


def get_mirror_snapshots_dir() -> Path:
    return get_mirror_data_dir() / 'snapshots'


def get_mirror_index_dir() -> Path:
    return get_mirror_data_dir()


def _parse_snapshot_datetime(filename: str) -> datetime | None:
    match = _SNAPSHOT_FILENAME_RE.match(filename)
    if not match:
        return None
    date_part, hour, minute, second = match.groups()
    try:
        return datetime.strptime(
            f"{date_part} {hour}:{minute}:{second}",
            "%Y-%m-%d %H:%M:%S",
        )
    except ValueError:
        return None


def _snapshot_item_count(payload: dict) -> int:
    raw_count = payload.get('count')
    try:
        if raw_count is not None:
            return max(int(raw_count), 0)
    except (TypeError, ValueError):
        pass
    items = payload.get('items')
    return len(items) if isinstance(items, list) else 0


def _build_dashboard_stats() -> dict:
    data_dir = get_data_dir()
    if not data_dir.exists():
        return {'month_count': 0, 'week_count': 0, 'day_count': 0}

    now = datetime.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=day_start.weekday())
    month_start = day_start.replace(day=1)
    stats = {'month_count': 0, 'week_count': 0, 'day_count': 0}

    for filepath in data_dir.glob('*.json'):
        snapshot_dt = _parse_snapshot_datetime(filepath.name)
        if snapshot_dt is None or snapshot_dt > now:
            continue
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception:
            continue
        item_count = _snapshot_item_count(payload)
        if snapshot_dt >= month_start:
            stats['month_count'] += item_count
        if snapshot_dt >= week_start:
            stats['week_count'] += item_count
        if snapshot_dt >= day_start:
            stats['day_count'] += item_count

    return stats


def _read_json(filepath: Path) -> dict | None:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(filepath: Path, payload: dict):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _reset_mirror_bootstrap():
    global _mirror_initialized
    with _mirror_init_lock:
        _mirror_initialized = False


def _bootstrap_mirror_if_needed():
    global _mirror_initialized
    with _mirror_init_lock:
        if _mirror_initialized:
            return
        index_dir = get_mirror_index_dir()
        index_dir.mkdir(parents=True, exist_ok=True)
        _mirror_initialized = True


def _dedupe_items_with_mirror(site_id: str, items: list[dict]) -> list[dict]:
    if not items:
        return items
    _bootstrap_mirror_if_needed()
    return filter_new_items(get_mirror_index_dir(), site_id, items)


def _save_single_result(site_id: str, result: dict) -> dict:
    _bootstrap_mirror_if_needed()
    crawled_at = datetime.now().isoformat(timespec='seconds')
    ts = crawled_at.replace(':', '-').replace('T', '_')
    filename = f"{ts}_{re.sub(r'[^\w\-]', '_', site_id)}.json"
    result['crawled_at'] = crawled_at
    _write_json(get_data_dir() / filename, result)
    update_site_index(
        get_mirror_index_dir(),
        site_id,
        result.get('items', []),
        updated_at=crawled_at,
        site_url=result.get('site_url', ''),
    )
    return result


def _save_batch_snapshot_to_mirror(snapshot: dict, filename: str):
    _bootstrap_mirror_if_needed()
    ingest_snapshot(get_mirror_index_dir(), snapshot)


def run_crawl_all():
    global crawl_state
    sites = load_sites()
    cfg = load_config()
    global_max = cfg.get('max_items', 200)
    global_age = cfg.get('max_article_age_days', 0)
    sites = [s for s in sites if not s.get('crawl_paused')]
    for s in sites:
        s.setdefault('max_items', global_max)
        s.setdefault('max_article_age_days', global_age)
    crawl_stop_event.clear()
    previous_last_run = crawl_state.get('last_run')
    with crawl_lock:
        crawl_state = {
            'running': True,
            'total': len(sites),
            'done': 0,
            'current': '',
            'last_run': previous_last_run,
            'stopped': False,
        }
    if not sites:
        with crawl_lock:
            crawl_state['running'] = False
        return

    def _progress(site: dict, _result: dict | None):
        with crawl_lock:
            crawl_state['done'] += 1
            crawl_state['current'] = site.get('name', '')

    _crawl_all(
        sites,
        get_data_dir(),
        dedupe_cb=_dedupe_items_with_mirror,
        save_hook=_save_batch_snapshot_to_mirror,
        should_stop=crawl_stop_event.is_set,
        progress_cb=_progress,
    )
    with crawl_lock:
        crawl_state['running'] = False
        crawl_state['current'] = ''
        crawl_state['stopped'] = crawl_stop_event.is_set()
        crawl_state['last_run'] = datetime.now().isoformat(timespec='seconds')


scheduler = BackgroundScheduler()


def _start_scheduler():
    cfg = load_config()
    hours = get_crawl_interval_hours(cfg)
    if not scheduler.get_job('crawl_job'):
        scheduler.add_job(run_crawl_all, 'interval', hours=hours, id='crawl_job')
    else:
        scheduler.reschedule_job('crawl_job', trigger='interval', hours=hours)

    if not scheduler.running:
        scheduler.start(paused=not is_scheduler_enabled(cfg))
    elif is_scheduler_enabled(cfg):
        scheduler.resume()
    else:
        scheduler.pause()


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
        sites = json.load(f)
    for site in sites:
        site.setdefault('crawl_paused', False)
    return sites


def save_sites(sites):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/sites', methods=['GET'])
def get_sites():
    return jsonify(load_sites())


def _normalize_url(url: str) -> str:
    if url and not url.startswith(('http://', 'https://')):
        return 'https://' + url
    return url


@app.route('/api/sites', methods=['POST'])
def add_site():
    data = request.get_json()
    if not data.get('name') or not data.get('url'):
        return jsonify({'error': '名称和URL不能为空'}), 400

    crawl_mode = data.get('crawl_mode', 'auto')
    if crawl_mode not in ('auto', 'html', 'js', 'stealth'):
        crawl_mode = 'auto'

    sites = load_sites()
    next_seq = max((s.get('seq', 0) for s in sites), default=0) + 1
    site = {
        'seq': next_seq,
        'id': str(uuid.uuid4()),
        'name': data['name'].strip(),
        'url': _normalize_url(data['url'].strip()),
        'note': data.get('note', '').strip(),
        'rss_url': None,
        'status': 'pending',
        'last_checked': None,
        'crawl_mode': crawl_mode,
        'crawl_paused': False,
        'selectors': data.get('selectors'),
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
                site['url'] = _normalize_url(data['url'].strip())
            site['note'] = data.get('note', site.get('note', '')).strip()
            if 'crawl_mode' in data:
                mode = data['crawl_mode']
                if mode in ('auto', 'html', 'js', 'stealth'):
                    site['crawl_mode'] = mode
            if 'selectors' in data:
                site['selectors'] = data['selectors']
            if 'crawl_paused' in data:
                site['crawl_paused'] = bool(data['crawl_paused'])
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


@app.route('/api/sites/<site_id>/crawl-toggle', methods=['POST'])
def toggle_site_crawl(site_id):
    data = request.get_json(silent=True) or {}
    sites = load_sites()
    for site in sites:
        if site['id'] != site_id:
            continue
        if 'paused' in data:
            site['crawl_paused'] = bool(data['paused'])
        else:
            site['crawl_paused'] = not bool(site.get('crawl_paused'))
        save_sites(sites)
        return jsonify(site)
    return jsonify({'error': 'site not found'}), 404


HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; RSS-checker/1.0)'}
RSS_PATHS = ['feed', 'feed/', 'rss', 'rss/', 'rss.xml', 'feed.xml', 'atom.xml', 'index.xml']


def _is_valid_feed(url, timeout=5):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True, verify=False)
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
    html = None
    try:
        r = requests.get(root_url, headers=HEADERS, timeout=timeout, verify=False)
        html = r.text
        for pattern in [
            r'<link[^>]+(?:application/rss\+xml|application/atom\+xml)[^>]+href=["\']([^"\']+)["\']',
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]+(?:application/rss\+xml|application/atom\+xml)',
        ]:
            matches = re.findall(pattern, html, re.IGNORECASE)
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

    # 扫描页面 <a href> 中含 rss/feed/atom 关键词的链接
    if html:
        try:
            for href in re.findall(r'<a[^>]+href=["\']([^"\']*(?:rss|feed|atom)[^"\']*)["\']', html, re.IGNORECASE):
                candidate = href if href.startswith('http') else urljoin(root_url, href)
                if _is_valid_feed(candidate, timeout):
                    return candidate, 'rss'
        except Exception:
            pass

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
        crawl_state['running'] = True
        crawl_state['stopped'] = False
    t = threading.Thread(target=run_crawl_all, daemon=True)
    t.start()
    return jsonify({'ok': True})


@app.route('/api/crawl/stop', methods=['POST'])
def crawl_stop():
    crawl_stop_event.set()
    with crawl_lock:
        crawl_state['stopped'] = True
    return jsonify({'ok': True})


@app.route('/api/crawl/status', methods=['GET'])
def crawl_status():
    with crawl_lock:
        return jsonify(dict(crawl_state))


@app.route('/api/crawl/<site_id>', methods=['POST'])
def crawl_one_route(site_id):
    sites = load_sites()
    site = next((s for s in sites if s['id'] == site_id), None)
    if site and site.get('crawl_paused'):
        return jsonify({'error': 'site crawl paused'}), 409
    if not site:
        return jsonify({'error': '未找到'}), 404
    cfg = load_config()
    site.setdefault('max_items', cfg.get('max_items', 200))
    site.setdefault('max_article_age_days', cfg.get('max_article_age_days', 0))
    result = _crawl_site(site)
    if result and result.get('items'):
        result['items'] = _dedupe_items_with_mirror(site['id'], result['items'])
        result['count'] = len(result['items'])
    if result:
        _save_single_result(site['id'], result)
    return jsonify(result if result else {'count': 0})


@app.route('/api/config', methods=['GET'])
def get_config():
    cfg = load_config()
    cfg['crawl_interval_hours'] = get_crawl_interval_hours(cfg)
    return jsonify(cfg)


@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.get_json()
    cfg = load_config()
    if 'crawl_interval_hours' in data:
        try:
            hours = int(data['crawl_interval_hours'])
        except (TypeError, ValueError):
            return jsonify({'error': '抓取间隔必须是 1 到 12 小时之间的整数'}), 400
        if not 1 <= hours <= 12:
            return jsonify({'error': '抓取间隔必须是 1 到 12 小时之间的整数'}), 400
        cfg['crawl_interval_hours'] = hours
        if scheduler.get_job('crawl_job'):
            scheduler.reschedule_job('crawl_job', trigger='interval', hours=hours)
    if 'data_dir' in data:
        raw = str(data['data_dir']).strip()
        if raw:
            try:
                Path(raw).mkdir(parents=True, exist_ok=True)
            except Exception:
                return jsonify({'error': '路径无效或无权限'}), 400
        cfg['data_dir'] = raw
    if 'mirror_data_dir' in data:
        raw = str(data['mirror_data_dir']).strip()
        if raw:
            try:
                Path(raw).mkdir(parents=True, exist_ok=True)
            except Exception:
                return jsonify({'error': '镜像路径无效或无权限'}), 400
        cfg['mirror_data_dir'] = raw
        _reset_mirror_bootstrap()
    if 'max_article_age_days' in data:
        cfg['max_article_age_days'] = int(data['max_article_age_days'])
    save_config(cfg)
    return jsonify(cfg)


@app.route('/api/results/<site_id>', methods=['GET'])
def get_results(site_id):
    data_dir = get_data_dir()
    if not data_dir.exists():
        return jsonify([])
    files = sorted(data_dir.glob(f'*_{site_id}.json'), reverse=True)
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
    filepath = get_data_dir() / filename
    if not filepath.exists():
        return jsonify({'error': '未找到'}), 404
    with open(filepath, 'r', encoding='utf-8') as f:
        return jsonify(json.load(f))


# ── AI 分析相关 ──────────────────────────────────────────

_ANALYZE_STEPS = {
    'fetching_page': '正在抓取网页...',
    'stripping_html': '正在进行网页噪音过滤...',
    'calling_ai': '正在调用AI进行网页结构分析...',
    'parsing_result': '正在解析AI返回结果...',
    'saving': '分析成功，正在保存抓取配置...',
    'done': 'AI分析完成',
}


def _run_analyze(site_id: str, site_url: str, site_name: str, ai_config: dict):
    global analyze_state
    try:
        with analyze_lock:
            analyze_state.update(
                running=True, site_id=site_id, site_name=site_name,
                step='fetching_page', message=_ANALYZE_STEPS['fetching_page'],
                error=None, result=None,
            )

        from scrapling import Fetcher
        page = Fetcher.get(site_url, timeout=30)
        html = page.body.decode('utf-8', errors='ignore') if isinstance(page.body, bytes) else page.body

        def _progress(step):
            with analyze_lock:
                analyze_state['step'] = step
                analyze_state['message'] = _ANALYZE_STEPS.get(step, step)

        selectors = _analyze_page(html, site_url, ai_config, progress_cb=_progress)

        with analyze_lock:
            analyze_state['step'] = 'saving'
            analyze_state['message'] = _ANALYZE_STEPS['saving']

        sites = load_sites()
        for s in sites:
            if s['id'] == site_id:
                s['selectors'] = selectors
                break
        save_sites(sites)

        from crawler import _extract_articles
        preview = _extract_articles(page, site_url, selectors)

        with analyze_lock:
            analyze_state.update(
                running=False, step='done', message=_ANALYZE_STEPS['done'],
                result={
                    'selectors': selectors,
                    'preview': preview[:10],
                    'preview_count': len(preview),
                },
            )
    except Exception as e:
        with analyze_lock:
            analyze_state.update(
                running=False, step='error',
                message=f'AI分析失败: {e}', error=str(e), result=None,
            )


@app.route('/api/sites/<site_id>/analyze', methods=['POST'])
def analyze_site(site_id):
    with analyze_lock:
        if analyze_state['running']:
            return jsonify({'error': 'AI分析正在进行中'}), 409

    sites = load_sites()
    site = next((s for s in sites if s['id'] == site_id), None)
    if not site:
        return jsonify({'error': '未找到'}), 404

    cfg = load_config()
    ai = cfg.get('ai', {})
    if not ai.get('api_url') or not ai.get('api_key') or not ai.get('model'):
        return jsonify({'error': '请先在 config.json 中配置 ai 字段（api_url、api_key、model）'}), 400

    t = threading.Thread(
        target=_run_analyze,
        args=(site_id, site['url'], site['name'], ai),
        daemon=True,
    )
    t.start()
    return jsonify({'ok': True})


@app.route('/api/analyze/status', methods=['GET'])
def analyze_status():
    with analyze_lock:
        return jsonify(dict(analyze_state))


@app.route('/api/analyze/result', methods=['GET'])
def analyze_result():
    with analyze_lock:
        result = analyze_state.get('result')
        if result:
            analyze_state['result'] = None
        return jsonify(result if result else {'error': '无结果'})


@app.route('/api/system/stats', methods=['GET'])
def system_stats():
    return jsonify(_build_dashboard_stats())


@app.route('/api/system/status', methods=['GET'])
def system_status():
    cfg = load_config()
    hours = get_crawl_interval_hours(cfg)
    with crawl_lock:
        last_run = crawl_state.get('last_run')
        crawl_running = crawl_state.get('running')
        crawl_stopped = crawl_state.get('stopped')
    return jsonify({
        'scheduler_on': is_scheduler_enabled(cfg),
        'interval_hours': hours,
        'last_run': last_run,
        'crawl_running': crawl_running,
        'crawl_stopped': crawl_stopped,
    })


@app.route('/api/system/crawl-service', methods=['POST'])
def set_crawl_service():
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get('enabled'))
    cfg = load_config()
    cfg['scheduler_on'] = enabled
    save_config(cfg)
    _start_scheduler()
    if not enabled:
        crawl_stop_event.set()
        with crawl_lock:
            crawl_state['stopped'] = True
    return jsonify({
        'scheduler_on': is_scheduler_enabled(cfg),
        'interval_hours': get_crawl_interval_hours(cfg),
    })


if __name__ == '__main__':
    import os
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        _start_scheduler()
    app.run(debug=True, port=5000)
