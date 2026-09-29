"""Manage the optional local FlareSolverr sidecar process.

The executable is deliberately kept outside the Python package.  A portable
copy can live in ``<project>/flaresolverr/flaresolverr.exe``; an explicit path
or the FLARESOLVERR_PATH environment variable can override that location.
"""
from __future__ import annotations

import atexit
import os
import subprocess
import time
from pathlib import Path

import requests
from scrapling import Selector


class FlareSolverrManager:
    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir).resolve()
        self.process: subprocess.Popen | None = None
        self.executable: Path | None = None
        self.url = 'http://127.0.0.1:8191/v1'
        self.last_error = ''
        self.started_by_us = False
        self.enabled = True
        self.log_file = None

    def _candidates(self, configured: str = '') -> list[Path]:
        values = [configured, os.environ.get('FLARESOLVERR_PATH', '')]
        values += [
            str(self.project_dir / 'flaresolverr' / 'flaresolverr.exe'),
            str(self.project_dir / 'flaresolverr.exe'),
            str(self.project_dir.parent / 'flaresolverr' / 'flaresolverr.exe'),
        ]
        result = []
        for value in values:
            if not value:
                continue
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = self.project_dir / path
            path = path.resolve()
            if path not in result:
                result.append(path)
        return result

    def _healthy(self, timeout: float = 1.5) -> bool:
        try:
            response = requests.post(
                self.url, json={'cmd': 'sessions.list'}, timeout=timeout
            )
            return response.ok
        except requests.RequestException:
            return False

    def start(self, config: dict | None = None) -> dict:
        cfg = config or {}
        sidecar = cfg.get('flaresolverr') or {}
        self.url = str(sidecar.get('url') or self.url).rstrip('/')
        enabled = bool(sidecar.get('enabled', True))
        self.enabled = enabled
        if not enabled:
            return self.status()
        if self._healthy():
            return self.status()

        configured = str(sidecar.get('executable_path') or '')
        executable = next((p for p in self._candidates(configured) if p.is_file()), None)
        if executable is None:
            self.last_error = (
                '未找到 FlareSolverr。请将 flaresolverr 文件夹放到项目目录，'
                '或在 config.json 的 flaresolverr.executable_path 中指定路径。'
            )
            return self.status()

        log_path = self.project_dir / 'flaresolverr.log'
        try:
            log_file = open(log_path, 'a', encoding='utf-8')
            self.log_file = log_file
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            self.process = subprocess.Popen(
                [str(executable)], cwd=str(executable.parent),
                stdout=log_file, stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            self.executable = executable
            self.started_by_us = True
            deadline = time.monotonic() + float(sidecar.get('startup_timeout_seconds', 30))
            while time.monotonic() < deadline:
                if self._healthy():
                    self.last_error = ''
                    return self.status()
                if self.process.poll() is not None:
                    break
                time.sleep(0.5)
            self.last_error = 'FlareSolverr 进程已启动，但 API 在规定时间内未就绪，请查看 flaresolverr.log。'
        except OSError as exc:
            self.last_error = f'启动 FlareSolverr 失败：{exc}'
        return self.status()

    def stop(self) -> None:
        if self.process is not None and self.started_by_us and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        if self.log_file is not None:
            self.log_file.close()
            self.log_file = None

    def solve(self, target_url: str, timeout_seconds: int = 60):
        """Return a Scrapling-compatible page after solving a browser challenge."""
        if not self.enabled:
            return None
        try:
            response = requests.post(
                self.url,
                json={'cmd': 'request.get', 'url': target_url,
                      'maxTimeout': int(timeout_seconds * 1000)},
                timeout=timeout_seconds + 10,
            )
            response.raise_for_status()
            payload = response.json()
            solution = payload.get('solution') or {}
            html = solution.get('response') or ''
            if not html:
                self.last_error = payload.get('message') or 'FlareSolverr 未返回页面内容'
                return None
            return Selector(html, url=target_url)
        except (requests.RequestException, ValueError) as exc:
            self.last_error = f'FlareSolverr 请求失败：{exc}'
            return None

    def status(self) -> dict:
        return {
            'enabled': self.enabled,
            'running': self._healthy(),
            'url': self.url,
            'executable': str(self.executable) if self.executable else '',
            'error': self.last_error,
        }


manager = FlareSolverrManager(Path(__file__).parent)
atexit.register(manager.stop)
