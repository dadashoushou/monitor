import json
import re
from pathlib import Path


_SPACE_RE = re.compile(r'\s+')


def normalize_title(title: str) -> str:
    return _SPACE_RE.sub(' ', (title or '').strip())


def iter_site_payloads(snapshot: dict):
    sites = snapshot.get('sites')
    if isinstance(sites, list):
        for site_data in sites:
            if isinstance(site_data, dict):
                yield site_data
        return
    if snapshot.get('site_id'):
        yield snapshot


def _site_index_path(index_dir: Path, site_id: str) -> Path:
    safe_site_id = re.sub(r'[^\w\-]', '_', site_id)
    return index_dir / f'{safe_site_id}.json'


def load_site_index(index_dir: Path, site_id: str) -> dict:
    filepath = _site_index_path(index_dir, site_id)
    if not filepath.exists():
        return {
            'site_id': site_id,
            'site_url': '',
            'updated_at': None,
            'titles': [],
        }
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {
            'site_id': site_id,
            'site_url': '',
            'updated_at': None,
            'titles': [],
        }
    return {
        'site_id': data.get('site_id') or site_id,
        'site_url': data.get('site_url', ''),
        'updated_at': data.get('updated_at'),
        'titles': list(data.get('titles', [])),
    }


def save_site_index(index_dir: Path, site_id: str, site_url: str, titles: list[str],
                    updated_at: str | None = None):
    index_dir.mkdir(parents=True, exist_ok=True)
    filepath = _site_index_path(index_dir, site_id)
    payload = {
        'site_id': site_id,
        'site_url': site_url,
        'updated_at': updated_at,
        'titles': titles,
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def update_site_index(index_dir: Path, site_id: str, items: list[dict],
                      updated_at: str | None = None, site_url: str = ''):
    existing = load_site_index(index_dir, site_id)
    title_map: dict[str, str] = {}

    for title in existing.get('titles', []):
        normalized = normalize_title(title)
        if normalized and normalized not in title_map:
            title_map[normalized] = title

    for item in items:
        raw_title = (item.get('title') or '').strip()
        normalized = normalize_title(raw_title)
        if normalized and normalized not in title_map:
            title_map[normalized] = raw_title

    save_site_index(
        index_dir,
        site_id,
        site_url or existing.get('site_url', ''),
        list(title_map.values()),
        updated_at=updated_at,
    )


def filter_new_items(index_dir: Path, site_id: str, items: list[dict]) -> list[dict]:
    existing = load_site_index(index_dir, site_id)
    historical_titles = {
        normalized
        for normalized in (normalize_title(title) for title in existing.get('titles', []))
        if normalized
    }

    filtered = []
    batch_titles: set[str] = set()
    for item in items:
        normalized = normalize_title(item.get('title', ''))
        if normalized and (normalized in historical_titles or normalized in batch_titles):
            continue
        filtered.append(item)
        if normalized:
            batch_titles.add(normalized)
    return filtered


def ingest_snapshot(index_dir: Path, snapshot: dict):
    updated_at = snapshot.get('crawled_at')
    for site_data in iter_site_payloads(snapshot):
        site_id = site_data.get('site_id')
        if not site_id:
            continue
        update_site_index(
            index_dir,
            site_id,
            site_data.get('items', []),
            updated_at=updated_at,
            site_url=site_data.get('site_url', ''),
        )
