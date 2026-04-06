import os

import pymysql
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_TIMEOUT = int(os.environ.get("CRAWLER_TIMEOUT", "10"))
VERIFY_TLS = os.environ.get("CRAWLER_VERIFY_TLS", "0").lower() in ("1", "true", "yes", "on")
BLOCK_MARKERS = (
    "403 forbidden",
    "access denied",
    "the region has been denied",
    "temporarily unavailable",
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def build_proxies():
    proxies = {}
    http_proxy = os.environ.get("CRAWLER_HTTP_PROXY") or os.environ.get("HTTP_PROXY")
    https_proxy = os.environ.get("CRAWLER_HTTPS_PROXY") or os.environ.get("HTTPS_PROXY")
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    return proxies


def build_session(headers=None, retries=2):
    session = requests.Session()
    session.keep_alive = False
    retry = Retry(
        total=retries,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD", "OPTIONS"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    if headers:
        session.headers.update(headers)
    proxies = build_proxies()
    if proxies:
        session.proxies.update(proxies)
    return session


def create_db_connection(dbhost):
    return pymysql.connect(
        host=dbhost.get("host"),
        user=dbhost.get("user"),
        password=dbhost.get("password"),
        database=dbhost.get("dbname"),
        charset="utf8mb4",
    )


def _block_reason(text):
    lowered = (text or "").lower()
    for marker in BLOCK_MARKERS:
        if marker in lowered:
            return marker
    return ""


def fetch(session, url, timeout=None, headers=None, referer=None, verify=None):
    request_headers = dict(headers or {})
    if referer:
        request_headers["Referer"] = referer

    try:
        response = session.get(
            url,
            headers=request_headers or None,
            timeout=timeout or DEFAULT_TIMEOUT,
            verify=VERIFY_TLS if verify is None else verify,
        )
    except requests.RequestException as exc:
        print("页面获取失败：{} {}".format(url, exc))
        return None

    if response.status_code != 200:
        print("页面状态异常：{} status={}".format(url, response.status_code))
        return None

    reason = _block_reason(response.text)
    if reason:
        print("页面被拦截：{} {}".format(url, reason))
        return None

    return response


def download_file(session, url, dest_path, headers=None, referer=None, timeout=None, verify=None):
    response = fetch(
        session,
        url,
        headers=headers,
        referer=referer,
        timeout=timeout,
        verify=verify,
    )
    if response is None:
        return False

    with open(dest_path, "wb") as output_file:
        output_file.write(response.content)
    return True
