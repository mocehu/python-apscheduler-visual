"""
更新检查服务

使用 GitHub API 检查项目更新
"""
import logging
import urllib.request
import urllib.error
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.core.conf import VERSION, GITHUB_REPO, GITHUB_API_URL

logger = logging.getLogger(__name__)

_cache: Dict[str, Any] = {
    "last_check": None,
    "release_info": None,
    "cache_duration": 3600
}


def get_current_version() -> str:
    return VERSION


def parse_version(version: str) -> tuple:
    version = version.lstrip("v").strip()
    parts = version.split(".")
    return tuple(int(p) for p in parts if p.isdigit())


def compare_versions(current: str, latest: str) -> int:
    try:
        current_parts = parse_version(current)
        latest_parts = parse_version(latest)
        
        for c, l in zip(current_parts, latest_parts):
            if c < l:
                return -1
            elif c > l:
                return 1
        
        if len(current_parts) < len(latest_parts):
            return -1
        elif len(current_parts) > len(latest_parts):
            return 1
        
        return 0
    except Exception:
        return 0


def fetch_github_release() -> Optional[Dict[str, Any]]:
    """从 GitHub 获取最新 release 信息"""
    if not GITHUB_REPO:
        logger.warning("未配置 GitHub 仓库地址")
        return None
    
    url = f"{GITHUB_API_URL}/releases/latest"
    
    try:
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github.v3+json")
        req.add_header("User-Agent", f"python-apscheduler-visual/{VERSION}")
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return {
                "version": data.get("tag_name", "").lstrip("v"),
                "name": data.get("name", ""),
                "published_at": data.get("published_at", ""),
                "html_url": data.get("html_url", ""),
                "body": data.get("body", ""),
                "assets": [
                    {
                        "name": asset.get("name"),
                        "browser_download_url": asset.get("browser_download_url"),
                        "size": asset.get("size")
                    }
                    for asset in data.get("assets", [])
                ]
            }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.info("GitHub 仓库暂无 release")
        else:
            logger.error(f"GitHub API 请求失败: {e.code}")
        return None
    except urllib.error.URLError as e:
        logger.error(f"网络请求失败: {e.reason}")
        return None
    except Exception as e:
        logger.error(f"获取更新信息失败: {e}")
        return None


def fetch_github_releases(limit: int = 10) -> List[Dict[str, Any]]:
    """从 GitHub 获取所有 releases"""
    if not GITHUB_REPO:
        logger.warning("未配置 GitHub 仓库地址")
        return []
    
    url = f"{GITHUB_API_URL}/releases?per_page={limit}"
    
    try:
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github.v3+json")
        req.add_header("User-Agent", f"python-apscheduler-visual/{VERSION}")
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return [
                {
                    "version": item.get("tag_name", "").lstrip("v"),
                    "name": item.get("name", ""),
                    "published_at": item.get("published_at", ""),
                    "html_url": item.get("html_url", ""),
                    "body": item.get("body", ""),
                    "prerelease": item.get("prerelease", False),
                    "draft": item.get("draft", False)
                }
                for item in data
                if not item.get("draft", False)
            ]
    except urllib.error.HTTPError as e:
        logger.error(f"GitHub API 请求失败: {e.code}")
        return []
    except urllib.error.URLError as e:
        logger.error(f"网络请求失败: {e.reason}")
        return []
    except Exception as e:
        logger.error(f"获取更新信息失败: {e}")
        return []


def check_update(use_cache: bool = True) -> Dict[str, Any]:
    now = datetime.utcnow()
    
    if use_cache and _cache["release_info"] and _cache["last_check"]:
        elapsed = (now - _cache["last_check"]).total_seconds()
        if elapsed < _cache["cache_duration"]:
            return _cache["release_info"]
    
    release_info = fetch_github_release()
    
    result = {
        "current_version": VERSION,
        "latest_version": None,
        "has_update": False,
        "release": None,
        "checked_at": now.isoformat(),
        "error": None
    }
    
    if release_info:
        result["latest_version"] = release_info["version"]
        result["release"] = release_info
        result["has_update"] = compare_versions(VERSION, release_info["version"]) < 0
    else:
        result["error"] = "无法获取版本信息"
    
    _cache["last_check"] = now
    _cache["release_info"] = result
    
    return result


def get_all_releases(limit: int = 10) -> Dict[str, Any]:
    """获取所有 releases"""
    releases = fetch_github_releases(limit)
    
    return {
        "current_version": VERSION,
        "releases": releases,
        "error": None if releases or not GITHUB_REPO else "未配置 GitHub 仓库地址"
    }