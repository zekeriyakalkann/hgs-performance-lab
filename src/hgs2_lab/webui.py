"""Yerel web arayüzü (ilk sürüm): senaryoları listeler, sentetik deneyi kullanıcı isteğiyle başlatır, sonuçları gösterir.

Yalnızca standart kütüphane (`http.server`); yeni bağımlılık yoktur. Başlatma: `python -m hgs2_lab.webui`.

Güvenlik sınırları:
* Sunucu her zaman `127.0.0.1`'e bağlanır (değiştirilemez); ayrılmış portlar (8080, 5432) arayüz portu olamaz.
* `Host` başlığı yalnızca `127.0.0.1:<port>` / `localhost:<port>` olabilir (DNS rebinding'e karşı); POST istekleri
  süreç başına üretilen bir form belirteci (CSRF) ister.
* Arayüzden YALNIZCA sentetik deney manifestleri çalıştırılır: mevcut `run_synthetic_experiment` aynen çağrılır
  (uygulamanın kendi `127.0.0.1` sentetik sunucusu + `execute_run`'ın ön kontrolü, hedef/dinleyici doğrulaması ve
  güvenlik sınırları). Harici bir hedef gerektiren HTTP senaryoları (`run`) ve kampanyalar yalnızca listelenir.
* Çalıştırılacak manifest, kullanıcının gönderdiği ad ile sunucu tarafında taranan listeden seçilir; kullanıcı girdisi
  yol, komut veya argüman olarak kullanılmaz. Aynı anda tek deney çalışır; hiçbir test kendiliğinden başlamaz.
* Sonuçlar mevcut okuyucu (`load_run`), analiz (`build_analysis`) ve sınıflandırıcı (`build_run_document`) ile bellekte
  hesaplanır; arayüz sonuç dosyası dışında dosya yazmaz. Senaryo başlıkları ve gövdeleri gösterilmez.
* Kapanışta (Ctrl+C) çalışan deney kesilmez, bitmesi beklenir (süresi manifestteki `limits` ile sınırlıdır).
"""

from __future__ import annotations

import argparse
import hmac
import html
import json
import secrets
import sys
import threading
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from .analysis import AnalysisOutputError, build_analysis
from .campaign import CampaignError, load_campaign
from .execution import PreflightError
from .models import validate_run_id
from .reader import RunData, load_run
from .records import CLASSES
from .result_analysis import build_run_document, resolve_dataset_kind
from .sanitize import sanitize_text, sanitize_url
from .scenarios import ScenarioError, load_scenarios
from .storage import StorageError
from .synthetic import ManifestError, estimated_min_duration_seconds, guard_forecast
from .synthetic_experiment import output_paths as synthetic_output_paths
from .synthetic_experiment import prepare as prepare_synthetic
from .synthetic_experiment import run_synthetic_experiment
from .target_guard import RESERVED_PORTS

HOST = "127.0.0.1"  # sabit: arayüz yalnızca bu bilgisayardan erişilebilir
DEFAULT_PORT = 8765
MAX_CONFIG_BYTES = 1_000_000
MAX_FORM_BYTES = 4096
RECENT_RUNS = 20

KIND_SYNTHETIC = "synthetic"
KIND_HTTP = "http_scenarios"
KIND_CAMPAIGN = "campaign"

HTTP_NOT_RUNNABLE = ("Harici bir hedef süreç gerektirir; arayüz yalnızca uygulamanın kendi sentetik sunucusuna karşı "
                     "çalıştırır. Komut satırı: hgs2-lab run")
CAMPAIGN_NOT_RUNNABLE = "Toplu çalıştırma arayüzde yok. Komut satırı: hgs2-lab campaign run"


# --- senaryo kataloğu (mevcut yükleyicilerle; yeni veri kaynağı yok) ---
@dataclass
class CatalogEntry:
    file: str  # yalnızca dosya adı (configs dizini içinde)
    kind: str
    runnable: bool
    reason: str | None = None  # çalıştırılamıyorsa nedeni
    error: str | None = None  # dosya geçersizse yükleyicinin mesajı
    info: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None


def _detect_kind(path: Path) -> str | None:
    if path.stat().st_size > MAX_CONFIG_BYTES:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if "manifest_version" in data:
        return KIND_SYNTHETIC
    if "campaign_version" in data:
        return KIND_CAMPAIGN
    if "scenarios" in data and "base_url" not in data:  # base_url: yapılandırma dosyası, senaryo değil
        return KIND_HTTP
    return None


def _synthetic_entry(path: Path) -> CatalogEntry:
    entry = CatalogEntry(path.name, KIND_SYNTHETIC, runnable=False, path=path)
    try:
        manifest, _sha, plan = prepare_synthetic(path)
    except ManifestError as exc:
        entry.error = sanitize_text(str(exc))
        entry.reason = "Manifest geçersiz"
        return entry
    entry.runnable = True
    entry.info = {
        "id": manifest.experiment_id,
        "description": manifest.description,
        "seed": manifest.seed,
        "timeout_seconds": manifest.timeout_seconds,
        "planned_requests": len(plan.entries),
        "min_duration_seconds": estimated_min_duration_seconds(manifest, plan),
        "limits": manifest.limits.to_dict(),
        "warning": guard_forecast(plan, manifest.limits),
        "scenarios": [
            {"name": s.name, "method": s.method, "warmup": s.warmup_repetitions, "repetitions": s.repetitions,
             "delay_seconds": s.delay_seconds, "fault": s.fault.to_dict()}
            for s in manifest.scenarios
        ],
    }
    return entry


def _http_entry(path: Path) -> CatalogEntry:
    entry = CatalogEntry(path.name, KIND_HTTP, runnable=False, reason=HTTP_NOT_RUNNABLE, path=path)
    try:
        scenarios = load_scenarios(path)
    except ScenarioError as exc:
        entry.error = sanitize_text(str(exc))
        return entry
    entry.info = {"scenarios": [
        {"name": s.name, "method": s.method, "path": sanitize_url(s.path), "warmup": s.warmup_repetitions,
         "repetitions": s.repetitions, "delay_seconds": s.delay_seconds,
         "expected_status": ",".join(map(str, s.expected_status)) or "2xx"}
        for s in scenarios
    ]}
    return entry


def _campaign_entry(path: Path) -> CatalogEntry:
    entry = CatalogEntry(path.name, KIND_CAMPAIGN, runnable=False, reason=CAMPAIGN_NOT_RUNNABLE, path=path)
    try:
        campaign, _sha = load_campaign(path)
    except CampaignError as exc:
        entry.error = sanitize_text(str(exc))
        return entry
    entry.info = {"id": campaign.campaign_id, "description": campaign.description, "seeds": list(campaign.seeds),
                  "plans": len({e.plan_id for e in campaign.experiments}), "experiments": len(campaign.experiments)}
    return entry


_ENTRY_BUILDERS = {KIND_SYNTHETIC: _synthetic_entry, KIND_HTTP: _http_entry, KIND_CAMPAIGN: _campaign_entry}


def scan_catalog(configs_dir: Path) -> list[CatalogEntry]:
    """`configs_dir` altındaki JSON dosyalarını türüne göre mevcut yükleyicilerle okur (istek göndermez)."""
    if not configs_dir.is_dir():
        return []
    entries = []
    for path in sorted(configs_dir.glob("*.json")):
        kind = _detect_kind(path)
        if kind is not None:
            entries.append(_ENTRY_BUILDERS[kind](path))
    return entries


# --- kaydedilmiş çalıştırmalar ---
def list_run_ids(results_dir: Path) -> list[tuple[str, bool]]:
    """(run_id, kısmi mi) listesi; en yeni önce (JSON dosyasının değişme zamanına göre)."""
    if not results_dir.is_dir():
        return []
    found = []
    for path in results_dir.glob("*.json"):
        stem = path.name[: -len(".json")]
        partial = stem.endswith(".partial")
        run_id = stem[: -len(".partial")] if partial else stem
        try:
            validate_run_id(run_id)
            mtime = path.stat().st_mtime
        except (ValueError, OSError):
            continue
        found.append((mtime, run_id, partial))
    found.sort(key=lambda item: item[0], reverse=True)
    return [(run_id, partial) for _mtime, run_id, partial in found]


def _read_labels(results_dir: Path, run: RunData) -> dict[str, Any] | None:
    labels_path = synthetic_output_paths(results_dir, run.run_id, run.partial)[0]
    if not labels_path.is_file():
        return None
    try:
        document = json.loads(labels_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {"error": "Etiket dosyası okunamadı"}
    verdict = document.get("verdict") if isinstance(document, dict) else None
    summary = document.get("summary") if isinstance(document, dict) else None
    if not isinstance(verdict, dict) or not isinstance(summary, dict):
        return {"error": "Etiket dosyası beklenen biçimde değil"}
    return {"valid": verdict.get("valid"), "reasons": [r.get("code") for r in verdict.get("reasons", [])
                                                       if isinstance(r, dict)],
            "summary": {k: summary.get(k) for k in ("planned", "confirmed", "contradicted", "not_executed")}}


@dataclass
class RunView:
    run_id: str
    partial: bool
    error: str | None = None
    run: dict[str, Any] | None = None  # build_analysis()["run"]
    overall: dict[str, Any] | None = None
    scenarios: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    classification: dict[str, Any] | None = None
    labels: dict[str, Any] | None = None


class RunViews:
    """Kaydedilmiş çalıştırmanın görünümü; mevcut okuyucu, analiz ve sınıflandırıcıyla (bellekte) üretilir."""

    def __init__(self, results_dir: Path, max_cached: int = 32) -> None:
        self._dir = results_dir
        self._cache: dict[tuple[str, bool, str], RunView] = {}
        self._max = max_cached
        self._lock = threading.Lock()

    def get(self, run_id: str) -> RunView:
        try:
            run = load_run(self._dir, run_id)
        except (StorageError, ValueError) as exc:
            return RunView(run_id, partial=False, error=sanitize_text(str(exc)))
        key = (run_id, run.partial, run.files[0].sha256)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached
        analysis = build_analysis(run)
        document = build_run_document(run, dataset_kind=resolve_dataset_kind(run, None))["classification"]
        view = RunView(
            run_id, run.partial, run=analysis["run"], overall=analysis["overall"], scenarios=analysis["scenarios"],
            warnings=analysis["warnings"], labels=_read_labels(self._dir, run),
            classification={"version": document["classifier_version"], "summary": document["summary"]},
        )
        with self._lock:
            if len(self._cache) >= self._max:
                self._cache.clear()
            self._cache[key] = view
        return view


# --- arka plan çalıştırması (tek iş parçacığı; kuyruk yok) ---
SyntheticRunner = Callable[..., Any]


class RunManager:
    """Aynı anda en çok bir sentetik deney yürütür. İş parçacığı daemon değildir: süreç onu yarıda bırakmaz."""

    def __init__(self, results_dir: Path, runner: SyntheticRunner = run_synthetic_experiment) -> None:
        self._results_dir = results_dir
        self._runner = runner
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._closed = False
        self._state: dict[str, Any] = {"status": "idle"}

    def state(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, entry: CatalogEntry) -> tuple[bool, str]:
        if entry.kind != KIND_SYNTHETIC or not entry.runnable or entry.path is None:
            return False, "Bu dosya arayüzden çalıştırılamaz"
        with self._lock:
            if self._closed:
                return False, "Arayüz kapanıyor; yeni deney başlatılmaz"
            if self._thread is not None and self._thread.is_alive():
                return False, "Bir deney zaten çalışıyor; bitmesini bekleyin"
            self._state = {"status": "running", "file": entry.file, "started_at": _now_iso()}
            self._thread = threading.Thread(target=self._work, args=(entry.path,), name="hgs2-ui-run", daemon=False)
            self._thread.start()
        return True, "Deney başlatıldı"

    def _work(self, manifest_path: Path) -> None:
        update: dict[str, Any]
        try:
            outcome = self._runner(manifest_path, results_dir=self._results_dir)
            update = {"status": "finished", "run_id": outcome.run.run_id, "run_status": outcome.run.status,
                      "valid": outcome.valid}
        except ManifestError as exc:
            update = {"status": "error", "message": f"Manifest geçersiz: {exc}"}
        except PreflightError as exc:
            update = {"status": "error", "message": f"Deney reddedildi, hiçbir istek gönderilmedi: {exc}"}
        except (StorageError, AnalysisOutputError) as exc:
            update = {"status": "error", "message": f"Sonuçlar kaydedilemedi: {exc}"}
        except Exception as exc:  # noqa: BLE001 - arayüz ayakta kalır; iz yalnızca yerel konsola yazılır
            traceback.print_exc()
            update = {"status": "error", "message": f"Beklenmeyen hata: {type(exc).__name__}"}
        if "message" in update:
            update["message"] = sanitize_text(update["message"])
        with self._lock:
            self._state = {**self._state, **update, "finished_at": _now_iso()}

    def close(self, timeout: float | None = None) -> bool:
        """Yeni deneyleri reddeder ve çalışan deneyin bitmesini bekler. Bittiyse (ya da yoksa) True."""
        with self._lock:
            self._closed = True
            thread = self._thread
        if thread is not None:
            thread.join(timeout)
            return not thread.is_alive()
        return True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- HTML ---
def _e(value: Any) -> str:
    return html.escape("—" if value is None else str(value))


def _ms(entry: dict[str, Any]) -> str:
    if entry.get("value") is not None:
        return f"{entry['value']:.2f}"
    if entry.get("status") == "insufficient_sample":
        return f"yetersiz örneklem (en az {entry['min_samples']})"
    return "veri yok"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"%{value * 100:.1f}"


def _badge(text: str, tone: str) -> str:
    return f'<span class="b {tone}">{_e(text)}</span>'


_STATUS_TONE = {"completed": "ok", "aborted": "bad", "interrupted": "warn", "failed": "bad"}


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


_CSS = """
body{font-family:Segoe UI,Arial,sans-serif;margin:0;color:#1d1d1f;background:#f6f7f9}
header{background:#24323f;color:#fff;padding:10px 24px}header a{color:#fff;margin-right:18px;text-decoration:none}
header strong{margin-right:28px}main{padding:16px 24px;max-width:1200px}
section{background:#fff;border:1px solid #dde1e6;border-radius:6px;padding:12px 16px;margin-bottom:16px}
h1{font-size:20px}h2{font-size:16px;margin-top:0}table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid #e6e8eb;padding:5px 8px;text-align:left;vertical-align:top}th{background:#f0f2f4}
.b{display:inline-block;padding:1px 8px;border-radius:10px;font-size:13px}.ok{background:#d8f0dc;color:#14532d}
.bad{background:#fadbd8;color:#7f1d1d}.warn{background:#fdf0cf;color:#713f12}.n{background:#e6e8eb;color:#333}
.note{color:#555;font-size:13px}.err{color:#7f1d1d}button{padding:4px 12px}
"""


def page(title: str, body: str, *, refresh: bool = False) -> str:
    meta = '<meta http-equiv="refresh" content="2">' if refresh else ""
    return (f'<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">{meta}<title>{_e(title)} · HGS2 Lab</title>'
            f"<style>{_CSS}</style></head><body><header><strong>HGS2 Performance Lab</strong>"
            '<a href="/">Dashboard</a><a href="/scenarios">Test senaryoları</a><a href="/runs">Sonuçlar</a></header>'
            f"<main><h1>{_e(title)}</h1>{body}</main></body></html>")


def _run_state_html(state: dict[str, Any]) -> str:
    status = state["status"]
    if status == "idle":
        return "<p>Bu oturumda arayüzden deney başlatılmadı.</p>"
    if status == "running":
        return (f"<p>{_badge('çalışıyor', 'warn')} <b>{_e(state['file'])}</b> — başlangıç {_e(state['started_at'])}. "
                "Sayfa 2 sn'de bir yenilenir.</p>")
    if status == "error":
        return (f"<p>{_badge('başlatılamadı / hata', 'bad')} <b>{_e(state['file'])}</b>: "
                f"<span class=err>{_e(state['message'])}</span></p>")
    valid = _badge("deney geçerli", "ok") if state["valid"] else _badge("deney geçersiz", "bad")
    return (f"<p>{_badge(state['run_status'], _STATUS_TONE.get(state['run_status'], 'n'))} {valid} "
            f"<b>{_e(state['file'])}</b> → <a href=\"/runs/{_e(state['run_id'])}\">{_e(state['run_id'])}</a> "
            f"(bitiş {_e(state['finished_at'])})</p>")


def _key_results(view: RunView) -> str:
    run, overall = view.run, view.overall
    assert run is not None and overall is not None
    measured, rates, rt = overall["measured"], overall["rates"], overall["response_time_ms"]
    execution = run["execution"]
    status = execution["status"] or "bilinmiyor"
    rows = [
        ["Çalıştırma", f'<a href="/runs/{_e(view.run_id)}">{_e(view.run_id)}</a>' + (" (kısmi)" if view.partial else "")],
        ["Durum", _badge(status, _STATUS_TONE.get(status, "n"))
         + (f" durdurma nedeni: {_e(execution['stop_reason'])}" if execution.get("stop_reason") else "")],
        ["Hedef etiketi / veri türü", f"{_e(run['target_label'])} / {_e(run['dataset_kind'])}"],
        ["Başlangıç / bitiş", f"{_e(run['started_at'])} / {_e(run['finished_at'])}"],
        ["Ölçüm isteği", f"{measured['total']} (başarılı {measured['successful']}, HTTP hatası "
                         f"{measured['http_errors']}, taşıma hatası {measured['transport_errors']})"],
        ["Hata oranı", _pct(rates["failure_rate"])],
        ["Yanıt süresi medyanı (ms)", _ms(rt["median"])],
    ]
    if view.labels and "error" not in view.labels:
        rows.append(["Sentetik deney", _badge("geçerli", "ok") if view.labels["valid"] else _badge("geçersiz", "bad")])
    return _table(["", ""], rows)


def render_dashboard(catalog: list[CatalogEntry], runs: list[tuple[str, bool]], last: RunView | None,
                     state: dict[str, Any], results_dir: Path, configs_dir: Path) -> str:
    synthetic = [e for e in catalog if e.kind == KIND_SYNTHETIC]
    http_files = [e for e in catalog if e.kind == KIND_HTTP]
    campaigns = [e for e in catalog if e.kind == KIND_CAMPAIGN]
    syn_count = sum(len(e.info.get("scenarios", [])) for e in synthetic)
    http_count = sum(len(e.info.get("scenarios", [])) for e in http_files)
    status = (f"<section><h2>Uygulama durumu</h2><p>{_badge('çalışıyor', 'ok')} hgs2-lab {_e(__version__)} · "
              f"yalnızca http://{HOST} üzerinde</p><p class=note>Senaryo dizini: {_e(configs_dir)} · "
              f"Sonuç dizini: {_e(results_dir)}</p>{_run_state_html(state)}</section>")
    counts = _table(["Tür", "Dosya", "Senaryo", "Arayüzden çalıştırılabilir"], [
        ["Sentetik deney manifesti", str(len(synthetic)), str(syn_count),
         f"{sum(e.runnable for e in synthetic)} dosya"],
        ["HTTP senaryo dosyası", str(len(http_files)), str(http_count), "hayır"],
        ["Sentetik kampanya", str(len(campaigns)), "—", "hayır"],
    ])
    scen = f'<section><h2>Test senaryoları</h2>{counts}<p><a href="/scenarios">Senaryoları görüntüle</a></p></section>'
    if last is None:
        latest = ("<section><h2>Son test çalışması</h2><p>Henüz test çalıştırılmadı: sonuç dizininde kayıtlı "
                  "çalıştırma yok.</p></section>")
    elif last.error is not None:
        latest = (f"<section><h2>Son test çalışması</h2><p>{_e(last.run_id)} okunamadı: "
                  f"<span class=err>{_e(last.error)}</span></p></section>")
    else:
        latest = f"<section><h2>Son test çalışması</h2>{_key_results(last)}</section>"
    return page("Dashboard", status + scen + latest, refresh=state["status"] == "running")


def _fault_text(fault: dict[str, Any]) -> str:
    params = ", ".join(f"{k}={v}" for k, v in fault.items() if k != "type")
    return fault["type"] + (f" ({params})" if params else "")


def render_scenarios(catalog: list[CatalogEntry], state: dict[str, Any], token: str, message: str | None) -> str:
    running = state["status"] == "running"
    parts = []
    if message:
        parts.append(f"<section><p>{_e(message)}</p></section>")
    parts.append(f"<section><h2>Çalıştırma durumu</h2>{_run_state_html(state)}</section>")
    if not catalog:
        parts.append("<section><p>Senaryo dizininde tanınan senaryo dosyası yok.</p></section>")
    for entry in catalog:
        title = {KIND_SYNTHETIC: "Sentetik deney", KIND_HTTP: "HTTP senaryoları", KIND_CAMPAIGN: "Sentetik kampanya"}
        head = f"<h2>{_e(title[entry.kind])}: {_e(entry.file)}</h2>"
        if entry.error:
            parts.append(f"<section>{head}<p>{_badge('geçersiz', 'bad')} <span class=err>{_e(entry.error)}</span>"
                         "</p></section>")
            continue
        info, body = entry.info, ""
        if entry.kind == KIND_SYNTHETIC:
            limits = ", ".join(f"{k}={v}" for k, v in info["limits"].items())
            body += (f"<p><b>{_e(info['id'])}</b> — {_e(info['description'])}</p>"
                     f"<p class=note>seed {_e(info['seed'])} · istemci zaman aşımı {_e(info['timeout_seconds'])} sn · "
                     f"planlanan istek {_e(info['planned_requests'])} · tahmini en kısa süre "
                     f"{info['min_duration_seconds']:.1f} sn · sınırlar: {_e(limits)}</p>")
            if info["warning"]:
                body += f"<p>{_badge('uyarı', 'warn')} {_e(info['warning'])}</p>"
            body += _table(["Senaryo", "Metot", "Isınma", "Ölçüm", "Bekleme (sn)", "Planlanan hata"], [
                [_e(s["name"]), _e(s["method"]), _e(s["warmup"]), _e(s["repetitions"]), _e(s["delay_seconds"]),
                 _e(_fault_text(s["fault"]))] for s in info["scenarios"]])
            disabled = " disabled" if running else ""
            body += (f'<form method="post" action="/run"><input type="hidden" name="token" value="{_e(token)}">'
                     f'<input type="hidden" name="manifest" value="{_e(entry.file)}">'
                     f"<p>{_badge('çalıştırılabilir', 'ok')} <button type=submit{disabled}>Deneyi başlat</button> "
                     "<span class=note>Uygulamanın kendi 127.0.0.1 sentetik sunucusuna karşı; gerçek HGS2 ölçümü "
                     "değildir.</span></p></form>")
        elif entry.kind == KIND_HTTP:
            body += _table(["Senaryo", "Metot", "Yol", "Isınma", "Ölçüm", "Bekleme (sn)", "Beklenen durum"], [
                [_e(s["name"]), _e(s["method"]), _e(s["path"]), _e(s["warmup"]), _e(s["repetitions"]),
                 _e(s["delay_seconds"]), _e(s["expected_status"])] for s in info["scenarios"]])
        else:
            body += (f"<p><b>{_e(info['id'])}</b> — {_e(info['description'])}</p><p class=note>plan {info['plans']}"
                     f" · seed {_e(', '.join(map(str, info['seeds'])))} · deney {info['experiments']}</p>")
        if not entry.runnable:
            body += f"<p>{_badge('arayüzden çalıştırılamaz', 'n')} <span class=note>{_e(entry.reason)}</span></p>"
        parts.append(f"<section>{head}{body}</section>")
    return page("Test senaryoları", "".join(parts), refresh=running)


def render_runs(rows: list[tuple[str, bool, RunView]]) -> str:
    if not rows:
        return page("Sonuçlar", "<section><p>Henüz test çalıştırılmadı: sonuç dizininde kayıtlı çalıştırma yok."
                                "</p></section>")
    table_rows = []
    for run_id, partial, view in rows:
        link = f'<a href="/runs/{_e(run_id)}">{_e(run_id)}</a>' + (" (kısmi)" if partial else "")
        if view.error is not None:
            table_rows.append([link, _badge("okunamadı", "bad"), "", "", "", "", ""])
            continue
        run, overall = view.run, view.overall
        status = run["execution"]["status"] or "bilinmiyor"
        table_rows.append([link, _badge(status, _STATUS_TONE.get(status, "n")), _e(run["target_label"]),
                           _e(run["started_at"]), _e(overall["measured"]["total"]),
                           _pct(overall["rates"]["failure_rate"]), _ms(overall["response_time_ms"]["median"])])
    table = _table(["Çalıştırma", "Durum", "Hedef etiketi", "Başlangıç", "Ölçüm isteği", "Hata oranı",
                    "Medyan (ms)"], table_rows)
    return page("Sonuçlar", f"<section><p class=note>En yeni {RECENT_RUNS} çalıştırma.</p>{table}</section>")


def _group_rows(name: str, group: dict[str, Any]) -> list[str]:
    m, rt, tp = group["measured"], group["response_time_ms"], group["throughput"]
    errors = ", ".join([f"HTTP {k}: {v}" for k, v in m["http_errors_by_status"].items()]
                       + [f"{k}: {v}" for k, v in m["transport_errors_by_type"].items()]) or "yok"
    throughput = f"{tp['requests_per_second']:.2f}" if tp["status"] == "ok" else f"hesaplanmadı ({tp['reason']})"
    return [_e(name), _e(group["requests"]["warmup"]), _e(m["total"]), _e(m["successful"]), _e(errors),
            _pct(group["rates"]["failure_rate"]), _ms(rt["median"]), _ms(rt["p90"]), _ms(rt["p95"]), _ms(rt["p99"]),
            "—" if rt["min"] is None else f"{rt['min']:.2f}", "—" if rt["max"] is None else f"{rt['max']:.2f}",
            _e(throughput)]


def render_run(view: RunView) -> str:
    if view.error is not None:
        return page(f"Çalıştırma {view.run_id}", f"<section><p class=err>{_e(view.error)}</p></section>")
    run = view.run
    assert run is not None and view.overall is not None and view.classification is not None
    execution = run["execution"]
    parts = [f"<section><h2>Genel sonuç</h2>{_key_results(view)}"]
    if execution.get("available"):
        parts.append(f"<p class=note>planlanan istek {_e(execution['planned_requests'])}, kaydedilen "
                     f"{_e(execution['recorded_requests'])}, yürütülmeyen {_e(execution['not_executed'])}</p>")
    if run.get("synthetic"):
        parts.append(f"<p class=note>Sentetik deney {_e(run['synthetic'].get('experiment_id'))}, seed "
                     f"{_e(run['synthetic'].get('seed'))}; gerçek HGS2 ölçümü değildir.</p>")
    parts.append("</section>")
    if view.labels is not None:
        labels = view.labels
        if "error" in labels:
            parts.append(f"<section><h2>Sentetik etiketler</h2><p class=err>{_e(labels['error'])}</p></section>")
        else:
            s = labels["summary"]
            reasons = ", ".join(map(str, labels["reasons"])) or "yok"
            parts.append(f"<section><h2>Sentetik etiketler</h2>" + _table(
                ["Planlanan", "Doğrulanan", "Çelişen", "Yürütülmeyen", "Deney geçerli", "Gerekçe kodları"],
                [[_e(s["planned"]), _e(s["confirmed"]), _e(s["contradicted"]), _e(s["not_executed"]),
                  _badge("evet", "ok") if labels["valid"] else _badge("hayır", "bad"), _e(reasons)]]) + "</section>")
    summary = view.classification["summary"]
    class_rows = [[_e(c), _e(summary["by_classification"].get(c, 0))] for c in CLASSES]
    outcome_rows = ", ".join(f"{k}={v}" for k, v in sorted(summary["by_test_outcome"].items())) or "yok"
    parts.append(
        f"<section><h2>Sonuç sınıfları (mevcut sınıflandırıcı: {_e(view.classification['version'])})</h2>"
        f"<p>Ölçüm isteği kaydı: {_e(summary['records'])} · test sonucu: {_e(outcome_rows)} · inceleme gerektiren: "
        f"{_e(summary['requires_review'])}</p>{_table(['Sınıf', 'Kayıt'], class_rows)}"
        "<p class=note>Beklenti dosyası verilmeden sınıflandırıldı (results classify ile aynı varsayılan); beklenen "
        "sonucu bilinmeyen kayıtlar INCONCLUSIVE olabilir.</p></section>")
    headers = ["Kapsam", "Isınma", "Ölçüm", "Başarılı", "Hatalar", "Hata oranı", "Medyan (ms)", "p90", "p95", "p99",
               "En az", "En çok", "Throughput (istek/sn)"]
    rows = [_group_rows("tümü", view.overall)] + [_group_rows(s["scenario"], s) for s in view.scenarios]
    parts.append(f"<section><h2>Performans ölçümleri (analiz modülü)</h2>{_table(headers, rows)}"
                 "<p class=note>Yanıt süreleri yalnızca başarılı (http_ok) ölçüm isteklerinin duration_ms "
                 "değerleridir; hata oranı = (HTTP hatası + taşıma hatası) / ölçüm isteği.</p></section>")
    if view.warnings:
        parts.append("<section><h2>Analiz uyarıları</h2>" + _table(
            ["Kod", "Kapsam", "Mesaj"], [[_e(w["code"]), _e(w["scope"]), _e(w["message"])] for w in view.warnings])
                     + "</section>")
    return page(f"Çalıştırma {view.run_id}", "".join(parts))


# --- HTTP ---
class LabUI:
    """Arayüzün durumu: dizinler, form belirteci, çalıştırma yöneticisi."""

    def __init__(self, configs_dir: Path, results_dir: Path, *, port: int,
                 runner: SyntheticRunner = run_synthetic_experiment) -> None:
        self.configs_dir = configs_dir
        self.results_dir = results_dir
        self.port = port
        self.token = secrets.token_urlsafe(24)
        self.manager = RunManager(results_dir, runner)
        self.views = RunViews(results_dir)

    def allowed_hosts(self, port: int) -> set[str]:
        return {f"{HOST}:{port}", f"localhost:{port}"}


class Handler(BaseHTTPRequestHandler):
    server_version = "hgs2-lab-ui"
    sys_version = ""
    ui: LabUI  # make_server tarafından alt sınıfta atanır

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in self.ui.allowed_hosts(self.server.server_address[1])

    def _send(self, status: HTTPStatus, body: str, *, location: str | None = None) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'")
        if location:
            self.send_header("Location", location)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - http.server arayüzü
        if not self._host_ok():
            self._send(HTTPStatus.BAD_REQUEST, "Geçersiz Host başlığı")
            return
        ui = self.ui
        url = urlsplit(self.path)
        if url.path == "/":
            runs = list_run_ids(ui.results_dir)
            last = ui.views.get(runs[0][0]) if runs else None
            self._send(HTTPStatus.OK, render_dashboard(scan_catalog(ui.configs_dir), runs, last, ui.manager.state(),
                                                       ui.results_dir, ui.configs_dir))
        elif url.path == "/scenarios":
            message = {"started": "Deney başlatıldı."}.get(parse_qs(url.query).get("m", [""])[0])
            self._send(HTTPStatus.OK, render_scenarios(scan_catalog(ui.configs_dir), ui.manager.state(), ui.token,
                                                       message))
        elif url.path == "/runs":
            rows = [(run_id, partial, ui.views.get(run_id))
                    for run_id, partial in list_run_ids(ui.results_dir)[:RECENT_RUNS]]
            self._send(HTTPStatus.OK, render_runs(rows))
        elif url.path.startswith("/runs/"):
            try:
                run_id = validate_run_id(unquote(url.path[len("/runs/"):]))
            except ValueError:
                self._send(HTTPStatus.NOT_FOUND, page("Bulunamadı", "<p>Geçersiz çalıştırma kimliği.</p>"))
                return
            if run_id not in {r for r, _p in list_run_ids(ui.results_dir)}:
                self._send(HTTPStatus.NOT_FOUND, page("Bulunamadı", "<p>Bu çalıştırma bulunamadı.</p>"))
                return
            self._send(HTTPStatus.OK, render_run(ui.views.get(run_id)))
        else:
            self._send(HTTPStatus.NOT_FOUND, page("Bulunamadı", "<p>Sayfa yok.</p>"))

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_ok():
            self._send(HTTPStatus.BAD_REQUEST, "Geçersiz Host başlığı")
            return
        origin = self.headers.get("Origin")
        if origin is not None and urlsplit(origin).netloc not in self.ui.allowed_hosts(self.server.server_address[1]):
            self._send(HTTPStatus.FORBIDDEN, "Geçersiz kaynak (Origin)")
            return
        if urlsplit(self.path).path != "/run":
            self._send(HTTPStatus.NOT_FOUND, page("Bulunamadı", "<p>Sayfa yok.</p>"))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_FORM_BYTES:
            self._send(HTTPStatus.BAD_REQUEST, "Geçersiz istek gövdesi")
            return
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        token = form.get("token", [""])[0]
        if not hmac.compare_digest(token.encode(), self.ui.token.encode()):
            self._send(HTTPStatus.FORBIDDEN, page("Reddedildi", "<p>Form belirteci geçersiz; sayfayı yenileyin.</p>"))
            return
        name = form.get("manifest", [""])[0]
        entry = next((e for e in scan_catalog(self.ui.configs_dir) if e.file == name), None)
        if entry is None:
            self._send(HTTPStatus.NOT_FOUND, page("Bulunamadı", "<p>Bu senaryo dosyası bulunamadı.</p>"))
            return
        ok, message = self.ui.manager.start(entry)
        if not ok:
            self._send(HTTPStatus.CONFLICT, page("Başlatılamadı", f"<section><p>{_e(message)}</p>"
                                                                  '<p><a href="/scenarios">Geri</a></p></section>'))
            return
        self._send(HTTPStatus.SEE_OTHER, "", location="/scenarios?m=started")


def make_server(ui: LabUI) -> ThreadingHTTPServer:
    """`127.0.0.1:<ui.port>`'a bağlanan sunucu (port 0: boş port). Ayrılmış portlar reddedilir."""
    if ui.port in RESERVED_PORTS:
        raise ValueError(f"Port {ui.port} ayrılmış ({RESERVED_PORTS[ui.port]}); arayüz bu portu kullanamaz")
    handler = type("BoundHandler", (Handler,), {"ui": ui})
    server = ThreadingHTTPServer((HOST, ui.port), handler)
    server.daemon_threads = True  # yalnızca sayfa istekleri; deney iş parçacığı RunManager'da ve daemon değil
    ui.port = server.server_address[1]
    return server


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hgs2_lab.webui",
                                     description="HGS2 Performance Lab yerel web arayüzü (yalnızca 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Dinlenecek port (varsayılan {DEFAULT_PORT})")
    parser.add_argument("--configs-dir", default="configs", help="Senaryo/manifest dizini (varsayılan configs)")
    parser.add_argument("--results-dir", default="results", help="Sonuç dizini (varsayılan results)")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("port 0..65535 aralığında olmalı")
    ui = LabUI(Path(args.configs_dir).resolve(), Path(args.results_dir).resolve(), port=args.port,
               runner=run_synthetic_experiment)
    try:
        server = make_server(ui)
    except (ValueError, OSError) as exc:
        print(f"Arayüz başlatılamadı: {exc}", file=sys.stderr)
        return 1
    print(f"HGS2 Performance Lab arayüzü: http://{HOST}:{ui.port}/  (durdurmak için Ctrl+C)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if ui.manager.running:
            print("Çalışan deneyin bitmesi bekleniyor (yeni deney başlatılmaz)...", file=sys.stderr)
        ui.manager.close()
        print("Arayüz kapatıldı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
