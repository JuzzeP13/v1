"""
TISH SEARCH v4 — Multi-Agent Site Analyzer
Запуск: python -m modules.main.python.server → http://localhost:5000

Новое в v4:
  - Постоянная БД (SQLite) — уже проверенные домены не перепроверяются
  - Очередь городов — добавляй несколько и они обрабатываются по очереди
  - Настройки прямо в интерфейсе (MAX_LARGE, MAX_NICHE, PARALLEL_SHOTS)
  - Исправлены пустые оценки дизайна и UX
  - Один общий Excel-файл который пополняется
  - Аутентификация и профили пользователей
  - Поддержка светлой/тёмной темы
  - Мультиязычность (RU/EN)
  - Поиск по соцсетям (YouTube, Instagram, X)
"""

import asyncio
import base64
import json
import os
import platform
import random
import re
import sqlite3
import subprocess
import threading
import time
import uuid
import requests as req
import openpyxl
from functools import wraps
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from playwright.async_api import async_playwright
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, render_template, send_file, jsonify, session, request, flash, redirect, url_for
from flask_socketio import SocketIO

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

try:
    import psutil
except ImportError:
    psutil = None

# ──────────────────────────────────────────────
# ИМПОРТ НОВЫХ МОДУЛЕЙ
# ──────────────────────────────────────────────
from modules.common.python.config import Config
from modules.common.python.asyncio_compat import ensure_windows_proactor_event_loop
from modules.auth.python.models import User, get_db, init_extended_db
from modules.auth.python.auth import auth_bp, login_required, get_current_user, login_user, logout_user, init_auth
from modules.auth.python.security import security_middleware, add_security_headers, is_likely_bot
from modules.chat.python.social_search import search_social_media
from modules.common.python.i18n import get_i18n, set_language, _
from modules.common.python.full_diagnostics import (
    diagnostics_log_path,
    log_event,
    setup_full_diagnostics,
)

ensure_windows_proactor_event_loop()

# ──────────────────────────────────────────────
# ПУТИ
# ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCREENSHOT_DIR = PROJECT_ROOT / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
STATIC_DIR = PROJECT_ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)
(STATIC_DIR / "images").mkdir(exist_ok=True)
TEMPLATES_DIR = PROJECT_ROOT / "templates"
DB_PATH     = PROJECT_ROOT / "tish_data.db"
EXCEL_PATH  = REPORTS_DIR / "tish_results.xlsx"   # единый файл

setup_full_diagnostics(source="modules.main.python.core")
log_event("diagnostics_log_ready", log_path=str(diagnostics_log_path()))

# ──────────────────────────────────────────────
# ДЕФОЛТНЫЕ НАСТРОЙКИ (меняются через UI)
# ──────────────────────────────────────────────
settings = {
    "ollama_url":    os.environ.get("OLLAMA_URL") or "http://localhost:11434",
    "vision_model":  os.environ.get("VISION_MODEL") or "llava:latest",
    "max_large":     30,
    "max_niche":     30,
    "max_per_query": 3,
    "parallel":      5,  # Оптимизировано для 20+ пользователей (было 8)
    "page_timeout":  8000,
    "vision_timeout_sec": 180,
    "vision_num_predict": 800,
    "search_max_passes": 10,
    "screenshot_wait_min_ms": 300,
    "screenshot_wait_max_ms": 800,
    "screenshot_width": 1280,
    "screenshot_height": 800,
    "screenshot_format": "jpeg",
    "screenshot_quality": 70,
    "analysis_prompt_mode": "full",
    "use_examples_in_prompt": True,
    "auto_switch_vision_model": False,
    "vision_slow_threshold_ms": 120000,
    "debug_verbose": False,
}


HARDWARE_PROFILE = {
    "tier": "default",
    "auto_mode": "standard",
    "cpu_logical": 0,
    "cpu_physical": 0,
    "cpu_name": "",
    "is_laptop_class_cpu": False,
    "ram_total_gb": 0.0,
    "ram_available_gb": 0.0,
    "has_discrete_gpu": False,
    "gpu_names": [],
    "gpu_max_vram_gb": 0.0,
}

LOW_END_RUNTIME_CAPS = {
    "max_large": 6,
    "max_niche": 6,
    "max_per_query": 2,
    "parallel": 2,
    "page_timeout": 12000,
    "vision_timeout_sec": 220,
    "vision_num_predict": 180,
    "search_max_passes": 6,
    "screenshot_width": 1024,
    "screenshot_height": 640,
    "screenshot_quality": 60,
}

_OLLAMA_MODELS_CACHE = {"ts": 0.0, "names": []}
_OLLAMA_MODELS_TTL_SEC = 45
_VISION_RUNTIME_NOTICE_SENT = False

_VISION_MODEL_HINTS = (
    "llava",
    "vision",
    "vl",
    "moondream",
    "minicpm",
    "bakllava",
    "internvl",
    "gemma3",
    "phi3-vision",
    "phi4-multimodal",
)
_LOW_END_MODEL_PRIORITY = (
    "moondream",
    "llama3.2-vision:3b",
    "llama3.2-vision",
    "qwen2.5vl:3b",
    "qwen2.5-vl:3b",
    "qwen2.5vl:7b",
    "qwen2.5-vl:7b",
    "minicpm-v:2b",
    "minicpm-v:8b",
    "phi3-vision",
    "phi4-multimodal",
    "llava:7b",
    "llava",
    "bakllava",
)
_GENERAL_MODEL_PRIORITY = (
    "llava",
    "qwen",
    "vision",
    "vl",
    "moondream",
    "minicpm",
    "bakllava",
)
_HEAVY_MODEL_HINTS = (
    "72b",
    "70b",
    "67b",
    "57b",
    "34b",
    "32b",
    "27b",
    "24b",
    "22b",
    "20b",
    "14b",
    "13b",
)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _read_env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    return _safe_int(value, default)


def _read_env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _read_env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    value = str(value).strip()
    return value or default


def _is_low_end_mode(profile: dict | None = None) -> bool:
    p = profile or HARDWARE_PROFILE
    tier = str(p.get("tier", "")).lower()
    auto_mode = str(p.get("auto_mode", "")).lower()
    return tier in {"low", "laptop_safe"} or auto_mode == "laptop_safe"


def _looks_like_vision_model_name(model_name: str) -> bool:
    name = str(model_name or "").strip().lower()
    if not name:
        return False
    return any(token in name for token in _VISION_MODEL_HINTS)


def _is_heavy_model_name(model_name: str) -> bool:
    name = str(model_name or "").strip().lower()
    if not name:
        return False
    return any(token in name for token in _HEAVY_MODEL_HINTS)


def _fetch_ollama_model_names(force_refresh: bool = False) -> list[str]:
    now = time.time()
    if (
        not force_refresh
        and _OLLAMA_MODELS_CACHE["names"]
        and (now - _OLLAMA_MODELS_CACHE["ts"]) <= _OLLAMA_MODELS_TTL_SEC
    ):
        return list(_OLLAMA_MODELS_CACHE["names"])

    try:
        r = req.get(f"{settings['ollama_url']}/api/tags", timeout=4)
        r.raise_for_status()
        models = r.json().get("models", [])
        names = [
            str(m.get("name")).strip()
            for m in models
            if isinstance(m, dict) and m.get("name")
        ]
        _OLLAMA_MODELS_CACHE["ts"] = now
        _OLLAMA_MODELS_CACHE["names"] = names
        return list(names)
    except Exception as e:
        if settings.get("debug_verbose"):
            print(f"[DEBUG] Не удалось получить список моделей Ollama: {e}")
        return list(_OLLAMA_MODELS_CACHE["names"])


def _pick_model_by_priority(model_names: list[str], priorities: tuple[str, ...]) -> str:
    lowered = [(name, str(name).lower()) for name in model_names]
    for token in priorities:
        token_l = token.lower()
        for original, lower in lowered:
            if token_l in lower:
                return original
    return ""


def _select_best_vision_model(
    model_names: list[str],
    current_model: str,
    low_end: bool,
) -> str:
    if not model_names:
        return current_model

    vision_models = [m for m in model_names if _looks_like_vision_model_name(m)]
    if not vision_models:
        return current_model if current_model in model_names else model_names[0]

    if low_end:
        low_end_candidate = _pick_model_by_priority(vision_models, _LOW_END_MODEL_PRIORITY)
        if low_end_candidate:
            return low_end_candidate
        non_heavy = [m for m in vision_models if not _is_heavy_model_name(m)]
        if current_model in non_heavy:
            return current_model
        if non_heavy:
            return non_heavy[0]

    if current_model in vision_models:
        return current_model

    candidate = _pick_model_by_priority(vision_models, _GENERAL_MODEL_PRIORITY)
    if candidate:
        return candidate
    return vision_models[0]


def auto_select_vision_model(reason: str = "runtime", force_refresh: bool = False) -> str:
    fallback_model = "llava:latest"
    current_model = str(settings.get("vision_model") or "").strip() or fallback_model
    settings["vision_model"] = current_model

    if not bool(settings.get("auto_switch_vision_model", True)):
        return current_model

    model_names = _fetch_ollama_model_names(force_refresh=force_refresh)
    if not model_names:
        return current_model

    low_end = _is_low_end_mode()
    selected = _select_best_vision_model(model_names, current_model, low_end=low_end)
    if selected and selected != current_model:
        settings["vision_model"] = selected
        log_event(
            "vision_model_autoselected",
            reason=reason,
            low_end_mode=low_end,
            previous_model=current_model,
            selected_model=selected,
            available_models=model_names,
        )
        print(f"[AUTO-MODEL] {current_model or '-'} -> {selected} ({reason})")
    return str(settings.get("vision_model") or "").strip() or fallback_model


def apply_low_end_guardrails(source: str = "runtime") -> dict:
    if not _is_low_end_mode():
        return {}

    changed = {}
    for key, cap in LOW_END_RUNTIME_CAPS.items():
        old_value = _safe_int(settings.get(key), cap)
        new_value = min(old_value, cap)
        if new_value != old_value:
            settings[key] = new_value
            changed[key] = {"from": old_value, "to": new_value}

    if str(settings.get("analysis_prompt_mode", "full")).lower() != "turbo":
        changed["analysis_prompt_mode"] = {"from": settings.get("analysis_prompt_mode"), "to": "turbo"}
        settings["analysis_prompt_mode"] = "turbo"

    if bool(settings.get("use_examples_in_prompt", True)):
        changed["use_examples_in_prompt"] = {"from": True, "to": False}
        settings["use_examples_in_prompt"] = False

    if str(settings.get("screenshot_format", "jpeg")).lower() != "jpeg":
        changed["screenshot_format"] = {"from": settings.get("screenshot_format"), "to": "jpeg"}
        settings["screenshot_format"] = "jpeg"

    if changed:
        log_event(
            "low_end_guardrails_applied",
            source=source,
            mode=str(HARDWARE_PROFILE.get("auto_mode") or HARDWARE_PROFILE.get("tier")),
            changed=changed,
        )
    return changed


def _degrade_vision_runtime_after_slow_call(duration_ms: int, trigger: str, model_name: str):
    global _VISION_RUNTIME_NOTICE_SENT

    if not _is_low_end_mode():
        return

    if trigger not in {"slow_success", "timeout"}:
        return

    threshold_ms = max(20000, _safe_int(settings.get("vision_slow_threshold_ms"), 90000))
    if trigger == "slow_success" and duration_ms < threshold_ms:
        return

    changed = {}

    old_predict = _safe_int(settings.get("vision_num_predict"), 120)
    target_predict = 150 if trigger == "timeout" else 160
    new_predict = max(128, min(old_predict, target_predict))
    if new_predict != old_predict:
        settings["vision_num_predict"] = new_predict
        changed["vision_num_predict"] = {"from": old_predict, "to": new_predict}

    old_timeout = _safe_int(settings.get("vision_timeout_sec"), 180)
    new_timeout = max(120, min(old_timeout, 220))
    if new_timeout != old_timeout:
        settings["vision_timeout_sec"] = new_timeout
        changed["vision_timeout_sec"] = {"from": old_timeout, "to": new_timeout}

    old_threshold = _safe_int(settings.get("vision_slow_threshold_ms"), 90000)
    new_threshold = max(30000, min(old_threshold, 100000))
    if new_threshold != old_threshold:
        settings["vision_slow_threshold_ms"] = new_threshold
        changed["vision_slow_threshold_ms"] = {"from": old_threshold, "to": new_threshold}

    if changed:
        log_event(
            "vision_runtime_degraded",
            level="warn",
            trigger=trigger,
            duration_ms=duration_ms,
            slow_threshold_ms=threshold_ms,
            current_url=state.get("current_url"),
            changed=changed,
        )
        if not _VISION_RUNTIME_NOTICE_SENT:
            emit_status("⚙️ Включён эконом-режим AI для слабого ПК", "warn")
            _VISION_RUNTIME_NOTICE_SENT = True


def _looks_like_generic_cpu_name(value: str) -> bool:
    name = (value or "").lower()
    if not name:
        return True
    generic_patterns = (
        "family",
        "model",
        "stepping",
        "authenticamd",
        "genuineintel",
    )
    return all(token in name for token in generic_patterns[:3]) and any(
        token in name for token in generic_patterns[3:]
    )


def _detect_windows_cpu_name_from_registry() -> str:
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-ItemProperty 'HKLM:\\HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0' -Name ProcessorNameString).ProcessorNameString",
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode != 0:
            return ""
        return (res.stdout or "").strip()
    except Exception:
        return ""


def _detect_windows_cpu_name() -> str:
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Processor | Select-Object Name | ConvertTo-Json -Compress",
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode != 0:
            return ""
        raw = (res.stdout or "").strip()
        if not raw:
            return ""
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and item.get("Name"):
                    detected = str(item.get("Name")).strip()
                    if detected and not _looks_like_generic_cpu_name(detected):
                        return detected
                    fallback = _detect_windows_cpu_name_from_registry()
                    return fallback or detected
            return ""
        if isinstance(parsed, dict):
            detected = str(parsed.get("Name") or "").strip()
            if detected and not _looks_like_generic_cpu_name(detected):
                return detected
            fallback = _detect_windows_cpu_name_from_registry()
            return fallback or detected
        return ""
    except Exception as e:
        log_event("hardware_cpu_detect_failed", level="warn", error=str(e))
        return ""


def _is_laptop_class_cpu_name(cpu_name: str) -> bool:
    name = (cpu_name or "").lower().strip()
    if not name:
        return False
    laptop_tokens = (
        "mobile",
        "laptop",
        "notebook",
    )
    if any(token in name for token in laptop_tokens):
        return True

    suffix_patterns = (
        r"\b\d{4,5}u\b",
        r"\b\d{4,5}h\b",
        r"\b\d{4,5}hs\b",
        r"\b\d{4,5}hx\b",
        r"\b\d{4,5}g\d\b",
    )
    return any(re.search(pattern, name) for pattern in suffix_patterns)


def _detect_windows_gpu_info():
    names = []
    max_vram_gb = 0.0
    has_discrete = False
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress",
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode != 0:
            return names, max_vram_gb, has_discrete

        raw = (res.stdout or "").strip()
        if not raw:
            return names, max_vram_gb, has_discrete

        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list):
            return names, max_vram_gb, has_discrete

        discrete_keywords = (
            "geforce", "rtx", "gtx", "quadro", "tesla", "radeon rx", "radeon pro", "arc ",
        )
        integrated_keywords = (
            "intel", "uhd", "iris", "vega", "radeon graphics", "radeon(tm) graphics",
        )

        for item in parsed:
            if not isinstance(item, dict):
                continue
            name = str(item.get("Name") or "").strip()
            if not name:
                continue
            names.append(name)

            lname = name.lower()
            is_integrated = any(token in lname for token in integrated_keywords)
            is_discrete = any(token in lname for token in discrete_keywords) and not is_integrated
            if is_discrete:
                has_discrete = True

            adapter_ram = _safe_float(item.get("AdapterRAM"), 0.0)
            if adapter_ram > 0:
                max_vram_gb = max(max_vram_gb, round(adapter_ram / (1024 ** 3), 2))
    except Exception as e:
        log_event("hardware_gpu_detect_failed", level="warn", error=str(e))

    return names, max_vram_gb, has_discrete


def _detect_hardware_profile():
    if psutil is None:
        cpu_logical = _safe_int(os.cpu_count(), 2)
        cpu_physical = max(1, cpu_logical // 2)
        ram_total_gb = 8.0
        ram_available_gb = 4.0
        log_event("hardware_detect_psutil_missing", level="warn")
    else:
        cpu_logical = _safe_int(psutil.cpu_count(logical=True), _safe_int(os.cpu_count(), 2))
        cpu_physical = _safe_int(psutil.cpu_count(logical=False), max(1, cpu_logical // 2))
        vm = psutil.virtual_memory()
        ram_total_gb = round(vm.total / (1024 ** 3), 2)
        ram_available_gb = round(vm.available / (1024 ** 3), 2)

    cpu_name = platform.processor() or ""

    gpu_names = []
    gpu_max_vram_gb = 0.0
    has_discrete_gpu = False
    if os.name == "nt":
        detected_cpu_name = _detect_windows_cpu_name()
        if detected_cpu_name:
            cpu_name = detected_cpu_name
        gpu_names, gpu_max_vram_gb, has_discrete_gpu = _detect_windows_gpu_info()

    is_laptop_class_cpu = _is_laptop_class_cpu_name(cpu_name)

    profile = {
        "tier": "medium",
        "auto_mode": "standard",
        "cpu_logical": cpu_logical,
        "cpu_physical": cpu_physical,
        "cpu_name": cpu_name,
        "is_laptop_class_cpu": is_laptop_class_cpu,
        "ram_total_gb": ram_total_gb,
        "ram_available_gb": ram_available_gb,
        "has_discrete_gpu": has_discrete_gpu,
        "gpu_names": gpu_names,
        "gpu_max_vram_gb": gpu_max_vram_gb,
    }

    if ram_total_gb <= 8 or cpu_logical <= 4:
        profile["tier"] = "low"
        return profile

    score = 0
    if cpu_logical >= 12:
        score += 2
    elif cpu_logical >= 8:
        score += 1

    if ram_total_gb >= 24:
        score += 2
    elif ram_total_gb >= 16:
        score += 1

    if has_discrete_gpu:
        score += 2
    elif gpu_max_vram_gb >= 3:
        score += 1

    if score <= 1:
        tier = "low"
    elif score <= 3:
        tier = "medium"
    elif score <= 5:
        tier = "high"
    else:
        tier = "ultra"

    profile["tier"] = tier
    return profile


def get_runtime_settings_payload():
    return {
        "settings": {
            "max_large": settings.get("max_large"),
            "max_niche": settings.get("max_niche"),
            "max_per_query": settings.get("max_per_query"),
            "parallel": settings.get("parallel"),
            "page_timeout": settings.get("page_timeout"),
            "vision_model": settings.get("vision_model"),
            "vision_timeout_sec": settings.get("vision_timeout_sec"),
            "vision_num_predict": settings.get("vision_num_predict"),
            "search_max_passes": settings.get("search_max_passes"),
            "screenshot_wait_min_ms": settings.get("screenshot_wait_min_ms"),
            "screenshot_wait_max_ms": settings.get("screenshot_wait_max_ms"),
            "screenshot_width": settings.get("screenshot_width"),
            "screenshot_height": settings.get("screenshot_height"),
            "screenshot_format": settings.get("screenshot_format"),
            "screenshot_quality": settings.get("screenshot_quality"),
            "analysis_prompt_mode": settings.get("analysis_prompt_mode"),
            "vision_slow_threshold_ms": settings.get("vision_slow_threshold_ms"),
        },
        "hardware": dict(HARDWARE_PROFILE),
    }


def apply_hardware_auto_tune():
    global HARDWARE_PROFILE

    disabled = (os.environ.get("TISH_DISABLE_HW_AUTOTUNE", "0") or "").strip().lower()
    if disabled in {"1", "true", "yes"}:
        log_event("hardware_autotune_disabled", source="env", env_var="TISH_DISABLE_HW_AUTOTUNE")
        return

    profile = _detect_hardware_profile()
    tier = profile.get("tier", "medium")

    # Conservative defaults for slower CPUs/iGPU, aggressive for stronger systems.
    tier_defaults = {
        "low": {
            "max_large": 5,
            "max_niche": 5,
            "max_per_query": 2,
            "parallel": 2,
            "page_timeout": 12000,
            "vision_timeout_sec": 220,
            "vision_num_predict": 170,
            "search_max_passes": 5,
            "screenshot_wait_min_ms": 150,
            "screenshot_wait_max_ms": 350,
            "screenshot_width": 960,
            "screenshot_height": 600,
            "screenshot_format": "jpeg",
            "screenshot_quality": 55,
            "analysis_prompt_mode": "turbo",
            "use_examples_in_prompt": False,
            "auto_switch_vision_model": False,
            "vision_slow_threshold_ms": 120000,
        },
        "laptop_safe": {
            "max_large": 5,
            "max_niche": 5,
            "max_per_query": 2,
            "parallel": 2,
            "page_timeout": 12000,
            "vision_timeout_sec": 240,
            "vision_num_predict": 180,
            "search_max_passes": 6,
            "screenshot_wait_min_ms": 180,
            "screenshot_wait_max_ms": 420,
            "screenshot_width": 1024,
            "screenshot_height": 640,
            "screenshot_format": "jpeg",
            "screenshot_quality": 60,
            "analysis_prompt_mode": "turbo",
            "use_examples_in_prompt": False,
            "auto_switch_vision_model": False,
            "vision_slow_threshold_ms": 120000,
        },
        "medium": {
            "max_large": 20,
            "max_niche": 20,
            "max_per_query": 3,
            "parallel": 3,
            "page_timeout": 10000,
            "vision_timeout_sec": 360,
            "vision_num_predict": 520,
            "search_max_passes": 8,
            "screenshot_wait_min_ms": 220,
            "screenshot_wait_max_ms": 520,
            "screenshot_width": 1200,
            "screenshot_height": 760,
            "screenshot_format": "jpeg",
            "screenshot_quality": 65,
            "analysis_prompt_mode": "full",
            "use_examples_in_prompt": True,
            "auto_switch_vision_model": False,
            "vision_slow_threshold_ms": 120000,
        },
        "high": {
            "max_large": 30,
            "max_niche": 30,
            "max_per_query": 3,
            "parallel": 5,
            "page_timeout": 8000,
            "vision_timeout_sec": 300,
            "vision_num_predict": 760,
            "search_max_passes": 10,
            "screenshot_wait_min_ms": 250,
            "screenshot_wait_max_ms": 600,
            "screenshot_width": 1280,
            "screenshot_height": 800,
            "screenshot_format": "png",
            "screenshot_quality": 80,
            "analysis_prompt_mode": "full",
            "use_examples_in_prompt": True,
            "auto_switch_vision_model": False,
            "vision_slow_threshold_ms": 120000,
        },
        "ultra": {
            "max_large": 40,
            "max_niche": 40,
            "max_per_query": 4,
            "parallel": 7,
            "page_timeout": 7000,
            "vision_timeout_sec": 240,
            "vision_num_predict": 900,
            "search_max_passes": 10,
            "screenshot_wait_min_ms": 300,
            "screenshot_wait_max_ms": 700,
            "screenshot_width": 1366,
            "screenshot_height": 900,
            "screenshot_format": "png",
            "screenshot_quality": 85,
            "analysis_prompt_mode": "full",
            "use_examples_in_prompt": True,
            "auto_switch_vision_model": False,
            "vision_slow_threshold_ms": 150000,
        },
    }

    force_laptop_safe = _read_env_bool("TISH_FORCE_LAPTOP_SAFE", False)
    laptop_safe_reason = ""
    if force_laptop_safe:
        laptop_safe_reason = "forced_by_env"
    elif (
        profile.get("is_laptop_class_cpu")
        and not profile.get("has_discrete_gpu")
    ):
        laptop_safe_reason = "laptop_cpu_and_no_discrete_gpu"
    elif (
        not profile.get("has_discrete_gpu")
        and profile.get("ram_total_gb", 0) <= 16
        and profile.get("ram_available_gb", 0) < 4
    ):
        laptop_safe_reason = "no_discrete_gpu_and_low_available_ram"

    if laptop_safe_reason:
        profile["auto_mode"] = "laptop_safe"
        # Не понижаем, если уже выбран более безопасный "low".
        if tier != "low":
            tier = "laptop_safe"

    tuned = dict(tier_defaults.get(tier, tier_defaults["medium"]))
    tuned["parallel"] = max(1, min(10, _safe_int(tuned.get("parallel"), 3)))

    # Env overrides for edge cases without code change.
    tuned["vision_timeout_sec"] = _read_env_int("TISH_VISION_TIMEOUT_SEC", tuned["vision_timeout_sec"])
    tuned["vision_num_predict"] = _read_env_int("TISH_VISION_NUM_PREDICT", tuned["vision_num_predict"])
    tuned["parallel"] = _read_env_int("TISH_PARALLEL_SHOTS", tuned["parallel"])
    tuned["parallel"] = max(1, min(10, tuned["parallel"]))
    tuned["search_max_passes"] = max(2, min(10, _read_env_int("TISH_SEARCH_MAX_PASSES", tuned["search_max_passes"])))
    tuned["screenshot_wait_min_ms"] = max(50, _read_env_int("TISH_SCREENSHOT_WAIT_MIN_MS", tuned["screenshot_wait_min_ms"]))
    tuned["screenshot_wait_max_ms"] = max(
        tuned["screenshot_wait_min_ms"],
        _read_env_int("TISH_SCREENSHOT_WAIT_MAX_MS", tuned["screenshot_wait_max_ms"]),
    )
    tuned["screenshot_width"] = max(640, min(1920, _read_env_int("TISH_SCREENSHOT_WIDTH", tuned["screenshot_width"])))
    tuned["screenshot_height"] = max(400, min(1200, _read_env_int("TISH_SCREENSHOT_HEIGHT", tuned["screenshot_height"])))
    screenshot_format = _read_env_str("TISH_SCREENSHOT_FORMAT", str(tuned.get("screenshot_format", "jpeg"))).lower()
    tuned["screenshot_format"] = screenshot_format if screenshot_format in {"jpeg", "png"} else "jpeg"
    tuned["screenshot_quality"] = max(40, min(95, _read_env_int("TISH_SCREENSHOT_QUALITY", tuned["screenshot_quality"])))
    prompt_mode = _read_env_str("TISH_ANALYSIS_PROMPT_MODE", str(tuned.get("analysis_prompt_mode", "full"))).lower()
    tuned["analysis_prompt_mode"] = prompt_mode if prompt_mode in {"full", "turbo"} else "full"
    tuned["use_examples_in_prompt"] = _read_env_bool("TISH_USE_EXAMPLES_IN_PROMPT", bool(tuned.get("use_examples_in_prompt", True)))
    tuned["auto_switch_vision_model"] = _read_env_bool(
        "TISH_AUTO_SWITCH_VISION_MODEL",
        bool(tuned.get("auto_switch_vision_model", False)),
    )
    tuned["vision_slow_threshold_ms"] = max(
        15000,
        min(240000, _read_env_int("TISH_VISION_SLOW_THRESHOLD_MS", int(tuned.get("vision_slow_threshold_ms", 90000)))),
    )
    tuned["debug_verbose"] = _read_env_bool("TISH_DEBUG_VERBOSE", bool(settings.get("debug_verbose", False)))

    settings.update(tuned)
    profile["tier"] = tier
    HARDWARE_PROFILE = profile
    apply_low_end_guardrails(source="auto_tune")
    auto_select_vision_model(reason="auto_tune", force_refresh=True)
    tuned_snapshot = {
        "max_large": settings.get("max_large"),
        "max_niche": settings.get("max_niche"),
        "max_per_query": settings.get("max_per_query"),
        "parallel": settings.get("parallel"),
        "page_timeout": settings.get("page_timeout"),
        "vision_model": settings.get("vision_model"),
        "vision_timeout_sec": settings.get("vision_timeout_sec"),
        "vision_num_predict": settings.get("vision_num_predict"),
        "vision_slow_threshold_ms": settings.get("vision_slow_threshold_ms"),
        "search_max_passes": settings.get("search_max_passes"),
        "screenshot_wait_min_ms": settings.get("screenshot_wait_min_ms"),
        "screenshot_wait_max_ms": settings.get("screenshot_wait_max_ms"),
        "screenshot_width": settings.get("screenshot_width"),
        "screenshot_height": settings.get("screenshot_height"),
        "screenshot_format": settings.get("screenshot_format"),
        "screenshot_quality": settings.get("screenshot_quality"),
        "analysis_prompt_mode": settings.get("analysis_prompt_mode"),
        "use_examples_in_prompt": settings.get("use_examples_in_prompt"),
        "auto_switch_vision_model": settings.get("auto_switch_vision_model"),
    }
    log_event(
        "hardware_autotune_applied",
        tier=tier,
        auto_mode=profile.get("auto_mode", "standard"),
        laptop_safe_reason=laptop_safe_reason,
        hardware=profile,
        tuned=tuned_snapshot,
    )
    print(
        "[AUTO-TUNE] "
        f"mode={profile.get('auto_mode', 'standard')} | "
        f"tier={tier} | CPU={profile['cpu_logical']}t/{profile['cpu_physical']}c | "
        f"CPU_NAME={profile.get('cpu_name') or 'unknown'} | "
        f"RAM={profile['ram_total_gb']}GB | GPU={', '.join(profile['gpu_names']) or 'unknown'} | "
        f"parallel={settings['parallel']} | page_timeout={settings['page_timeout']} | "
        f"vision_timeout={settings['vision_timeout_sec']} | num_predict={settings['vision_num_predict']} | "
        f"model={settings['vision_model']} | slow_ms={settings['vision_slow_threshold_ms']} | "
        f"search_passes={settings['search_max_passes']} | "
        f"shot_wait={settings['screenshot_wait_min_ms']}-{settings['screenshot_wait_max_ms']}ms | "
        f"shot={settings['screenshot_width']}x{settings['screenshot_height']} {settings['screenshot_format']} q{settings['screenshot_quality']} | "
        f"prompt={settings['analysis_prompt_mode']}"
    )


apply_hardware_auto_tune()

CAPTCHA_SIGNALS = [
    "checkcaptcha","captcha","robot","blocked","access denied",
    "403 forbidden","cloudflare","just a moment","attention required",
    "verifying you","ddos-guard","checking your browser",
    "please verify", "security check", "are you human",
    "challenge", "reCAPTCHA", "hCaptcha",
    "protection", "denuvo", "suspicious activity",
    "ip banned", "too many requests", "429",
    "rate limit", "temporarily unavailable",
]
# ──────────────────────────────────────────────
# АДАПТИВНАЯ ФИЛЬТРАЦИЯ ПО ГОРОДУ
# ──────────────────────────────────────────────
# Крупные города - можно жесткую фильтрацию
BIG_CITIES = {"москва", "санкт-петербург", "спб", "св", "екатеринбург", "новосибирск", 
              "казань", "краснодар", "омск", "челябинск"}

# Режимы фильтрации
FILTER_MODES = {
    "STRICT": {  # Жесткая - для больших городов
        "search_multiplier": 5,  # Ищем результатов
        "check_spam_keywords": True,
        "check_suspicious_patterns": True,
        "check_domain_quality": True,
    },
    "NORMAL": {  # Обычная - для средних
        "search_multiplier": 10,
        "check_spam_keywords": False,  # Выключаем спам-ключворды
        "check_suspicious_patterns": False,  # Выключаем подозрительные паттерны
        "check_domain_quality": True,
    },
    "LENIENT": {  # Щадящая - для маленьких городов
        "search_multiplier": 20,
        "check_spam_keywords": False,
        "check_suspicious_patterns": False,
        "check_domain_quality": False,  # Берем почти всё
    },
}

def get_filter_mode(city: str) -> str:
    """Определяет режим фильтрации на основе города"""
    city_lower = city.lower().strip()
    
    # Проверяем крупный ли город
    if city_lower in BIG_CITIES or len(city_lower) < 4:
        return "STRICT"
    elif len(city_lower) > 15:
        return "NORMAL"  # Необычно длинное название
    else:
        return "NORMAL"  # По умолчанию нормальный

SKIP_DOMAINS = [
    # Wiki и словари
    "wiktionary.org","kartaslov.ru","wikipedia.org","support.google.com",
    
    # Видео и потоковое
    "youtube.com","rutube.ru","vimeo.com","dailymotion.com",
    
    # Социальные сети
    "vk.com","ok.ru","t.me","telegram.me","instagram.com",
    "facebook.com","twitter.com","x.com","tiktok.com","snapchat.com",
    
    # Облачные сервисы
    "digitalocean.ru","2gis.ru",
    
    # Маркетплейсы и магазины (кроме avito - он для услуг)
    "yandex.ru/maps","google.com/maps","zoom.earth",
    "amazon.com","ebay.com","aliexpress.com","ozon.ru","wildberries.ru",
    
    # Карты и навигация
    "yandex.ru/maps","google.com/maps","waze.com","tripadvisor.ru",
    
    # Агрегаторы отзывов
    "otzovik.com","2gis.ru","zoon.ru","flamp.ru","yell.ru",
    "market.yandex.ru","yandex.ru/internet",
    
    # Развлечение и досуг
    "kino.ru","kinopoisk.ru","imdb.com","letterboxd.com",
    "rotten tomatoes.com","metacritic.com",
    
    # Спортивные результаты
    "sports.ru","sport1.com","flashscore.com","espn.com",
    
    # Новостные агрегаторы
    "livejournal.com","blogger.com","wordpress.com","medium.com",
    
    # Форумы и обсуждения
    "forum","forums.","discuss","reddit.com","quora.com",
    "stack overflow.com","habr.com",
    
    # Блог-платформы
    "blogspot.com","tumblr.com","substack.com","patreon.com",
    
    # Тестирование и dev-сервисы
    "github.com","gitlab.com","bitbucket.org","npm.js.org",
    "pypi.org","crates.io","rubygems.org",
    
    # CDN и хостинг
    "cloudflare.com","akamai.com","fastly.com","cdn",
    
    # Платежные системы (опасные)
    "paypal.com","stripe.com","2checkout.com",
    
    # Казино и ставки (явные)
    "casino","betting","poker","slots","jackpot","forex",
]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

app = Flask(
    __name__,
    static_folder=str(STATIC_DIR),
    static_url_path="/static",
    template_folder=str(TEMPLATES_DIR),
)
app.config.from_object(Config)
app.config["JSON_AS_ASCII"] = False
if hasattr(app, "json"):
    app.json.ensure_ascii = False
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", ping_timeout=60, ping_interval=25, max_http_buffer_size=10*1024*1024)

# ─────────────────────────────────────
# ИНИЦИАЛИЗАЦИЯ МНОГОЯЗЫЧНОСТИ
# ─────────────────────────────────────
i18n = get_i18n()
set_language('ru')  # Язык по умолчанию

# Добавляем функцию перевода в контекст шаблонов
@app.context_processor
def inject_i18n():
    return {
        '_': _,
        'set_language': set_language,
        'get_i18n': get_i18n,
        'current_language': i18n.get_language(),
        'available_languages': i18n.available_languages(),
        'config': Config
    }

app.register_blueprint(auth_bp)

@app.before_request
def _before_request_security():
    security_middleware()
    # Обработка переключения языка
    lang = request.args.get('lang')
    if lang:
        set_language(lang)
        session['language'] = lang

@app.after_request
def _after_request_security(response):
    content_type = response.headers.get('Content-Type', '')
    ct_lower = content_type.lower()
    if ct_lower.startswith('text/html') and 'charset=' not in ct_lower:
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
    elif ct_lower.startswith('application/json') and 'charset=' not in ct_lower:
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return add_security_headers(response)

# ──────────────────────────────────────────────
# СОСТОЯНИЕ
# ──────────────────────────────────────────────
state = {
    "running":     False,
    "stop":        False,
    "city":        "",
    "phase":       "idle",
    "found_urls":  [],
    "results":     [],
    "current_url": "",
    "skipped":     0,
    "elapsed_sec": 0,
    "start_time":  None,
    "report_file": str(EXCEL_PATH),
    "active_sid":  None,
    # очередь городов
    "queue":       [],   # список строк
    "queue_done":  [],   # уже обработанные
}

# Блокировка для предотвращения одновременного запуска задач
# Для 20+ пользователей
state_lock = threading.Lock()
_STATE_LOG_INTERVAL_SEC = 5
_last_state_log_ts = 0.0


# ──────────────────────────────────────────────
# SQLite — постоянное хранилище проверенных доменов
# ──────────────────────────────────────────────
def db_init():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS sites (
                domain   TEXT PRIMARY KEY,
                url      TEXT,
                city     TEXT,
                type     TEXT,
                category TEXT,
                design   TEXT,
                ux       TEXT,
                design_score INTEGER DEFAULT 0,
                ux_score INTEGER DEFAULT 0,
                checked_at TEXT,
                rating   INTEGER DEFAULT 0,
                needs_redesign BOOLEAN DEFAULT 1
            )
        """)
        
        # Миграция: добавляем недостающие колонки если нужно
        cursor = con.execute("PRAGMA table_info(sites)")
        columns = {row[1] for row in cursor.fetchall()}
        
        if "design_score" not in columns:
            print("[MIGRATION] Добавляю колонку design_score...")
            con.execute("ALTER TABLE sites ADD COLUMN design_score INTEGER DEFAULT 0")
        
        if "ux_score" not in columns:
            print("[MIGRATION] Добавляю колонку ux_score...")
            con.execute("ALTER TABLE sites ADD COLUMN ux_score INTEGER DEFAULT 0")
        
        if "rating" not in columns:
            print("[MIGRATION] Добавляю колонку rating...")
            con.execute("ALTER TABLE sites ADD COLUMN rating INTEGER DEFAULT 0")
        
        if "category" not in columns:
            print("[MIGRATION] Добавляю колонку category...")
            con.execute("ALTER TABLE sites ADD COLUMN category TEXT DEFAULT 'Другое'")
        
        if "needs_redesign" not in columns:
            print("[MIGRATION] Добавляю колонку needs_redesign...")
            con.execute("ALTER TABLE sites ADD COLUMN needs_redesign BOOLEAN DEFAULT 1")
        
        con.execute("""
            CREATE TABLE IF NOT EXISTS examples (
                id       INTEGER PRIMARY KEY,
                url      TEXT,
                design   TEXT,
                ux       TEXT,
                is_good  BOOLEAN,
                reason   TEXT,
                added_at TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS product_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                title TEXT,
                description TEXT,
                query TEXT,
                city TEXT,
                category TEXT,
                found_at TEXT,
                analyzed_at TEXT,
                UNIQUE(url, query, city)
            )
        """)
        product_columns = {row[1] for row in con.execute("PRAGMA table_info(product_results)").fetchall()}
        product_migrations = {
            "match_level": "ALTER TABLE product_results ADD COLUMN match_level TEXT DEFAULT 'partial'",
            "rank_score": "ALTER TABLE product_results ADD COLUMN rank_score REAL DEFAULT 0",
            "tags": "ALTER TABLE product_results ADD COLUMN tags TEXT",
            "related_terms": "ALTER TABLE product_results ADD COLUMN related_terms TEXT",
            "search_tokens": "ALTER TABLE product_results ADD COLUMN search_tokens TEXT",
            "source_level": "ALTER TABLE product_results ADD COLUMN source_level TEXT DEFAULT 'partial'",
        }
        for column_name, sql in product_migrations.items():
            if column_name not in product_columns:
                print(f"[MIGRATION] Добавляю колонку product_results.{column_name}...")
                con.execute(sql)
        con.execute("CREATE INDEX IF NOT EXISTS idx_product_results_rank ON product_results(rank_score DESC)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_product_results_match_level ON product_results(match_level)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS social_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                platform TEXT NOT NULL,
                title TEXT,
                description TEXT,
                username TEXT,
                city TEXT,
                query TEXT,
                found_at TEXT,
                analyzed_at TEXT,
                design_score INTEGER,
                ux_score INTEGER,
                design_text TEXT,
                ux_text TEXT,
                UNIQUE(url, platform)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS youtube_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL UNIQUE,
                title TEXT,
                channel_id TEXT,
                channel_title TEXT,
                channel_url TEXT,
                subscriber_count INTEGER,
                views INTEGER,
                duration REAL,
                viral_score REAL,
                score REAL,
                query TEXT,
                found_at TEXT,
                analyzed_at TEXT,
                thumbnail_score REAL,
                thumbnail_quality TEXT,
                clickbait_probability TEXT,
                emotion_score REAL
            )
        """)
        con.commit()
        print("[DB] Инициализация завершена ✓")

def check_ollama_models():
    """Проверяет доступные модели в Ollama"""
    try:
        model_names = _fetch_ollama_model_names(force_refresh=True)
        print(f"[DEBUG] Доступные модели в Ollama: {model_names}")

        selected_model = str(settings.get("vision_model") or "").strip() or "llava:latest"
        settings["vision_model"] = selected_model
        if selected_model not in model_names:
            fallback = _select_best_vision_model(model_names, selected_model, low_end=_is_low_end_mode())
            if fallback and fallback in model_names:
                settings["vision_model"] = fallback
                selected_model = fallback
                log_event(
                    "vision_model_fallback_applied",
                    reason="configured_model_missing",
                    selected_model=selected_model,
                    available_models=model_names,
                )
                print(f"[INFO] Модель была переключена на доступную: '{selected_model}'")
            else:
                print(f"[WARNING] Модель '{selected_model}' НЕ найдена!")
                print(f"[INFO] Доступные модели: {', '.join(model_names)}")
                return False
        else:
            print(f"[OK] Модель '{selected_model}' найдена ✓")
            return True
    except Exception as e:
        print(f"[ERROR] Не удалось проверить модели: {e}")
        return False

def db_has_domain(domain: str) -> bool:
    with sqlite3.connect(DB_PATH) as con:
        r = con.execute("SELECT 1 FROM sites WHERE domain=?", (domain,)).fetchone()
        return r is not None

def db_save(city: str, results: list):
    """Сохраняет ТОЛЬКО сайты с плохим дизайном/UX (нуждающиеся в переделке)"""
    now = datetime.now().isoformat()
    if settings.get("debug_verbose"):
        print(f"[DEBUG db_save] Попытка сохранить {len(results)} результатов для города '{city}'")
    saved_count = 0
    skipped_count = 0
    
    with sqlite3.connect(DB_PATH) as con:
        for r in results:
            if r["design"].startswith("Пропущено"):
                if settings.get("debug_verbose"):
                    print(f"[DEBUG db_save] Пропущен: {r['url']} (design начинается с 'Пропущено')")
                skipped_count += 1
                continue
            
            design_score = r.get("design_score", 5)
            ux_score = r.get("ux_score", 5)
            
            # КЛЮЧЕВОЙ ФИЛЬТР: сохраняем только сайты с плохим дизайном ИЛИ UX
            # Нас интересуют сайты для переделки!
            needs_redesign = design_score <= 5 or ux_score <= 5
            
            if not needs_redesign:
                if settings.get("debug_verbose"):
                    print(f"[DEBUG db_save] ⏭ Пропущен (хороший дизайн): {get_domain(r['url'])} "
                          f"[Дизайн: {design_score}/10, UX: {ux_score}/10]")
                skipped_count += 1
                continue
            
            try:
                category = r.get("category", "Другое")
                domain = get_domain(r["url"])
                
                con.execute("""
                    INSERT OR REPLACE INTO sites
                    (domain, url, city, type, category, design, ux, design_score, ux_score, checked_at, needs_redesign)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (domain, r["url"], city, r["type"], category, r["design"], r["ux"], 
                      design_score, ux_score, now, 1))
                
                saved_count += 1
                emoji = "🔴" if design_score <= 3 or ux_score <= 3 else "🟠"  # критичные vs обычные плохие
                if settings.get("debug_verbose"):
                    print(f"[DEBUG db_save] {emoji} Сохранён: {domain} "
                          f"[Дизайн: {design_score}/10, UX: {ux_score}/10] - НУЖНА ПЕРЕДЕЛКА!")
            except Exception as e:
                if settings.get("debug_verbose"):
                    print(f"[DEBUG db_save] ✗ ОШИБКА при сохранении {r['url']}: {e}")
        
        con.commit()
    
    if settings.get("debug_verbose"):
        print(f"[DEBUG db_save] Итого для города '{city}': "
              f"сохранено {saved_count} (нуждаются в переделке) | "
              f"пропущено {skipped_count} (уже хороший дизайн)")

def db_all() -> list:
    with sqlite3.connect(DB_PATH) as con:
        # Сортируем так, чтобы сайты с плохим дизайном (нуждающиеся в переделке) были в начале
        rows = con.execute("""
            SELECT url,city,type,category,design,ux,checked_at,design_score,ux_score,needs_redesign 
            FROM sites 
            ORDER BY needs_redesign DESC, design_score ASC, ux_score ASC, checked_at DESC
        """).fetchall()
    return [{"url":r[0],"city":r[1],"type":r[2],"category":r[3],"design":r[4],"ux":r[5],"checked_at":r[6],
             "design_score":r[7],"ux_score":r[8],"needs_redesign":bool(r[9])} for r in rows]

def db_stats():
    with sqlite3.connect(DB_PATH) as con:
        total  = con.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
        cities = con.execute("SELECT COUNT(DISTINCT city) FROM sites").fetchone()[0]
        needs_redesign = con.execute("SELECT COUNT(*) FROM sites WHERE needs_redesign=1").fetchone()[0]
        critical = con.execute("SELECT COUNT(*) FROM sites WHERE (design_score <= 3 OR ux_score <= 3)").fetchone()[0]
    return {
        "total": total, 
        "cities": cities,
        "needs_redesign": needs_redesign,  # Сайты с плохим дизайном/UX
        "critical": critical  # Сайты с критичным дизайном/UX (дизайн или UX <= 3)
    }

def db_save_scores(domain: str, design_score: int, ux_score: int):
    """Сохранить оценки дизайна и UX (0-10)"""
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "UPDATE sites SET design_score=?, ux_score=? WHERE domain=?",
            (design_score, ux_score, domain)
        )
        con.commit()

def db_get_examples(is_good: bool) -> list:
    """Получить примеры хороших (True) или плохих (False) дизайнов"""
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT url, design, ux FROM examples WHERE is_good=? ORDER BY added_at DESC LIMIT 3",
            (is_good,)
        ).fetchall()
    return [{"url": r[0], "design": r[1], "ux": r[2]} for r in rows]

def db_save_example(url: str, design: str, ux: str, is_good: bool, reason: str = ""):
    """Сохранить результат как пример"""
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO examples (url, design, ux, is_good, reason, added_at) VALUES (?,?,?,?,?,?)",
            (url, design, ux, is_good, reason, now)
        )
        con.commit()

def db_rate_site(domain: str, rating: int):
    """Оценить сайт (1-5 звёзд)"""
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE sites SET rating=? WHERE domain=?", (rating, domain))
        con.commit()


# ──────────────────────────────────────────────
# EXCEL — единый файл, пополняется
# ──────────────────────────────────────────────
def excel_rebuild():
    """Пересобирает Excel из всей БД. Сортирует сайты по критичности переделки."""
    rows = db_all()
    if not rows:
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "TISH SEARCH — для переделки"

    hf = PatternFill("solid", fgColor="1E1E2E")
    critical_fill = PatternFill("solid", fgColor="FFE0E0")  # Красный для критичных
    bad_fill = PatternFill("solid", fgColor="FFF0E0")  # Оранжевый для плохих
    good_fill = PatternFill("solid", fgColor="E0F0FF")  # Голубой для хороших
    hfont  = Font(bold=True, color="FFFFFF", size=11)
    ufont  = Font(color="0563C1", underline="single", bold=True)
    thin   = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap   = Alignment(wrap_text=True, vertical="top")

    headers = ["#", "КРИТИЧНОСТЬ", "URL", "Город", "Тип", "Категория", "Дизайн (0-10)", "UX (0-10)", "Оценка дизайна", "Оценка UX", "Дата"]
    widths  = [4, 14, 42, 12, 10, 16, 10, 10, 40, 40, 12]

    ws.append([""] * 11)
    ws.merge_cells("A1:K1")
    tc = ws.cell(row=1, column=1)
    tc.value = f"🔴 TISH SEARCH — Сайты для переделки  |  {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    tc.font = Font(bold=True, size=13, color="FFFFFF")
    tc.alignment = Alignment(horizontal="center", vertical="center")
    tc.fill = PatternFill("solid", fgColor="CC0000")
    ws.row_dimensions[1].height = 32

    for col, (h, w) in enumerate(zip(headers, widths), 1):
        c = ws.cell(row=2, column=col, value=h)
        c.font = hfont; c.fill = hf; c.border = border
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[c.column_letter].width = w
    ws.row_dimensions[2].height = 28

    for i, r in enumerate(rows, 1):
        row  = i + 2
        design_score = r.get("design_score", 5)
        ux_score = r.get("ux_score", 5)
        needs_redesign = r.get("needs_redesign", False)
        
        # Определяем цвет строки по критичности
        if design_score <= 3 or ux_score <= 3:
            fill = critical_fill
            criticality = "🔴 КРИТИЧНАЯ"
        elif needs_redesign:
            fill = bad_fill
            criticality = "🟠 ПЛОХАЯ"
        else:
            fill = good_fill
            criticality = "✅ ОК"
        
        ws.cell(row=row, column=1, value=i).alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row=row, column=2, value=criticality).alignment = Alignment(horizontal="center", vertical="top")
        uc = ws.cell(row=row, column=3, value=r["url"])
        uc.font = ufont; uc.alignment = Alignment(vertical="top", wrap_text=True)
        ws.cell(row=row, column=4, value=r["city"]).alignment = Alignment(vertical="top", wrap_text=True)
        ws.cell(row=row, column=5, value=r["type"]).alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row=row, column=6, value=r.get("category", "Другое")).alignment = Alignment(horizontal="center", vertical="top")
        
        # Оценки числовые
        ws.cell(row=row, column=7, value=design_score if design_score > 0 else "—").alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(row=row, column=8, value=ux_score if ux_score > 0 else "—").alignment = Alignment(horizontal="center", vertical="top")
        
        # Описания оценок
        ws.cell(row=row, column=9, value=r["design"]).alignment = wrap
        ws.cell(row=row, column=10, value=r["ux"]).alignment = wrap
        ws.cell(row=row, column=11, value=r["checked_at"][:10] if r["checked_at"] else "").alignment = Alignment(vertical="top")
        
        for col in range(1, 12):
            c = ws.cell(row=row, column=col)
            c.border = border; c.fill = fill
        ws.row_dimensions[row].height = 80

    wb.save(str(EXCEL_PATH))


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────
def get_domain(url: str) -> str:
    try:
        h = urlparse(url).hostname or ""
        return h.removeprefix("www.")
    except:
        return url

def is_spam_content(title: str = "", description: str = "") -> bool:
    """Проверяет заголовок и описание на явные признаки спама"""
    content = (title + " " + description).lower()
    
    # Только явные признаки спама/фарма
    obvious_spam_keywords = [
        "casino", "betting", "poker", "jackpot",
        "viagra", "cialis", "pharmacy",
        "click here now", "limited offer now",
        "scam", "phishing",
        "xxx", "adult",
    ]
    
    return any(keyword in content for keyword in obvious_spam_keywords)

def is_junk_url(url: str) -> bool:
    u = url.lower()
    # ТОЛЬКО явно мусорные паттерны (социалки, маркетплейсы, облако)
    absolute_junk = SKIP_DOMAINS + [
        # Только самые очевидные социальки и видео
        "instagram.com", "tiktok.com", "facebook.com", "twitter.com",
        "x.com", "linkedin.com", "youtube", "rutube",
        
        # Только очевидные маркетплейсы
        "amazon", "ebay", "aliexpress", "ozon", "wildberries",
        
        # Только явно облачные платформы
        "blogger.com", "wordpress.com", "wix.com",
    ]
    return any(s in u for s in absolute_junk)

def is_quality_domain(url: str) -> bool:
    """Проверяет очень мягко - только очевидный мусор"""
    u = url.lower()
    domain = get_domain(url)
    
    # ТОЛЬКО очень очевидный мусор отклоняем
    obvious_bad = [
        len(domain) < 3,  # Слишком короткий
        len(domain) > 150,  # Слишком длинный  
        domain.startswith("10."),  # IP адреса
        domain.count(".") > 5,  # Слишком много точек (мусорные поддомены)
    ]
    
    return not any(obvious_bad)

def is_professional_domain(url: str) -> bool:
    """МАКСИМАЛЬНО мягкая проверка - принимаем почти всё"""
    u = url.lower()
    domain = get_domain(url)
    
    # Только ЯВНЫЕ спам-домены отклоняем
    obvious_spam = [
        "casino" in u,
        "poker" in u,
    ]
    
    # Все остальное принимаем
    return not any(obvious_spam)

def has_suspicious_url_pattern(url: str) -> bool:
    """Проверяет URL на явно подозрительные паттерны (очень щадящая)"""
    u = url.lower()
    
    # Только самые явные красные флаги
    obvious_suspicious = [
        # Явные редиректы и шортены
        "bit.ly", "tinyurl", "short.link", "rebrand.ly",
        "bit.do", "ow.ly", "goo.gl", "shortened.link",
        
        # Очень длинные URL с параметрами (явный мусор)
        (len(url) > 250 and "?" in url),  # Очень длинный URL с параметрами
    ]
    
    for pattern in obvious_suspicious:
        if isinstance(pattern, bool):
            if pattern:
                return True
        elif isinstance(pattern, str) and pattern in u:
            return True
    
    return False

def is_captcha_page(title: str, cur_url: str) -> bool:
    return any(s in (title + cur_url).lower() for s in CAPTCHA_SIGNALS)


# ──────────────────────────────────────────────
# EMIT
# ──────────────────────────────────────────────
def emit_status(msg, level="info"):
    socketio.emit("status", {"msg": msg, "level": level}, room=state.get("active_sid"))
    log_event(
        "status_emit",
        level=level,
        msg=msg,
        phase=state.get("phase"),
        city=state.get("city"),
        running=state.get("running"),
        stop=state.get("stop"),
        current_url=state.get("current_url"),
        queue_len=len(state.get("queue", [])),
        queue_done_len=len(state.get("queue_done", [])),
        found=len(state.get("found_urls", [])),
        analyzed=len(state.get("results", [])),
        active_sid=state.get("active_sid"),
    )

def emit_state():
    global _last_state_log_ts
    s = state["elapsed_sec"]
    payload = {
        "phase":       state["phase"],
        "city":        state["city"],
        "found":       len(state["found_urls"]),
        "analyzed":    len(state["results"]),
        "total":       len(state["found_urls"]),
        "current_url": state["current_url"],
        "skipped":     state["skipped"],
        "elapsed":     f"{s//60}м {s%60:02d}с",
        "running":     state["running"],
        "stopped":     state["stop"],
        "queue":       state["queue"],
        "queue_done":  state["queue_done"],
        "db_stats":    db_stats(),
    }
    socketio.emit("state", payload, room=state.get("active_sid"))

    now = time.time()
    if (now - _last_state_log_ts) >= _STATE_LOG_INTERVAL_SEC:
        _last_state_log_ts = now
        log_event(
            "state_snapshot",
            phase=payload["phase"],
            city=payload["city"],
            found=payload["found"],
            analyzed=payload["analyzed"],
            total=payload["total"],
            current_url=payload["current_url"],
            skipped=payload["skipped"],
            elapsed_sec=s,
            running=payload["running"],
            stop=payload["stopped"],
            queue=list(payload["queue"]),
            queue_done=list(payload["queue_done"]),
            db_total=payload["db_stats"].get("total"),
            db_cities=payload["db_stats"].get("cities"),
            active_sid=state.get("active_sid"),
        )


# ──────────────────────────────────────────────
# ТАЙМЕР
# ──────────────────────────────────────────────
def _timer():
    while True:
        time.sleep(1)
        if state["running"] and state["start_time"]:
            state["elapsed_sec"] = int(time.time() - state["start_time"])
            s = state["elapsed_sec"]
            socketio.emit("tick", {"elapsed": f"{s//60}м {s%60:02d}с"}, room=state.get("active_sid"))

threading.Thread(target=_timer, daemon=True).start()


# ──────────────────────────────────────────────
# OLLAMA — ИСПРАВЛЕННЫЙ vision
# ──────────────────────────────────────────────
def call_vision(prompt: str, image_b64: str) -> str:
    model_name = str(settings.get("vision_model") or "").strip() or "llava:latest"
    settings["vision_model"] = model_name
    request_id = uuid.uuid4().hex[:12]
    timeout_sec = max(60, _safe_int(settings.get("vision_timeout_sec"), 180))
    num_predict = max(64, _safe_int(settings.get("vision_num_predict"), 800))
    started_at = time.time()
    payload = {
        "model": model_name,
        "messages": [{
            "role":    "user",
            "content": prompt,
            "images":  [image_b64]
        }],
        "stream": False,
        "options": {
            "temperature": 0.3,  # немного повышен для более критичной оценки
            "num_predict": num_predict,
            "top_k": 40,
            "top_p": 0.9,
        }
    }
    log_event(
        "vision_request_start",
        request_id=request_id,
        model=model_name,
        ollama_url=settings["ollama_url"],
        prompt_chars=len(prompt or ""),
        image_b64_chars=len(image_b64 or ""),
        timeout_sec=timeout_sec,
        num_predict=num_predict,
        phase=state.get("phase"),
        current_url=state.get("current_url"),
        stop=state.get("stop"),
    )
    try:
        emit_status(f"  🤖 Анализирую с {model_name}...", "info")
        
        r = req.post(
            f"{settings['ollama_url']}/api/chat",
            json=payload, timeout=timeout_sec
        )
        r.raise_for_status()
        
        resp = r.json()
        if settings.get("debug_verbose"):
            print(f"[DEBUG] API ответ: {resp}")
        
        if "message" in resp:
            msg = resp["message"]
            # Сначала ищем обычный контент
            content = msg.get("content", "").strip()
            
            # Если контент пуст, проверяем поле "thinking" (для qwen3-vl)
            if not content and "thinking" in msg:
                content = msg.get("thinking", "").strip()
            
            if content:
                if settings.get("debug_verbose"):
                    print(f"[DEBUG] Получен ответ: {content[:200]}")
                duration_ms = int((time.time() - started_at) * 1000)
                log_event(
                    "vision_request_success",
                    request_id=request_id,
                    duration_ms=duration_ms,
                    response_chars=len(content),
                )
                _degrade_vision_runtime_after_slow_call(
                    duration_ms=duration_ms,
                    trigger="slow_success",
                    model_name=model_name,
                )
                return content
        
        if settings.get("debug_verbose"):
            print(f"[DEBUG] Неожиданный формат ответа: {resp}")
        duration_ms = int((time.time() - started_at) * 1000)
        log_event(
            "vision_request_empty_response",
            level="warn",
            request_id=request_id,
            duration_ms=duration_ms,
            response_keys=list(resp.keys()),
        )
        emit_status(f"⚠ Модель ответила пустым ответом", "warn")
        return "Нет ответа от модели"
        
    except req.exceptions.Timeout:
        duration_ms = int((time.time() - started_at) * 1000)
        msg = f"Timeout: модель долго обрабатывает. Проверь модель {model_name}"
        if settings.get("debug_verbose"):
            print(f"[DEBUG] {msg}")
        log_event(
            "vision_request_timeout",
            level="error",
            request_id=request_id,
            duration_ms=duration_ms,
            model=model_name,
            current_url=state.get("current_url"),
            stop=state.get("stop"),
        )
        _degrade_vision_runtime_after_slow_call(
            duration_ms=duration_ms,
            trigger="timeout",
            model_name=model_name,
        )
        emit_status(msg, "error")
        return msg
    except req.exceptions.ConnectionError as e:
        msg = f"Нет соединения с Ollama по адресу {settings['ollama_url']}"
        if settings.get("debug_verbose"):
            print(f"[DEBUG] {msg}: {e}")
        log_event(
            "vision_request_connection_error",
            level="error",
            request_id=request_id,
            duration_ms=int((time.time() - started_at) * 1000),
            error=str(e),
            ollama_url=settings["ollama_url"],
        )
        emit_status(msg, "error")
        return msg
    except Exception as e:
        msg = f"Ошибка анализа: {str(e)[:100]}"
        if settings.get("debug_verbose"):
            print(f"[DEBUG] {msg}")
        duration_ms = int((time.time() - started_at) * 1000)
        log_event(
            "vision_request_error",
            level="error",
            request_id=request_id,
            duration_ms=duration_ms,
            error=str(e),
        )
        emit_status(msg, "error")
        return msg


# ──────────────────────────────────────────────
# ПЕРЕПРОВЕРКА БД
# ──────────────────────────────────────────────
