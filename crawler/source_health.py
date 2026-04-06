#!/opt/mm187/.venv/bin/python
import os
import socket
import time

import requests

from common import DEFAULT_TIMEOUT, VERIFY_TLS, build_session


PRIMARY_SOURCES = [
    ("meirentu", "https://meirentu.cc/group/xiuren.html"),
    ("huotumao", "https://www.huotumao.com/info/coser"),
    ("coserlab", "https://coserlab.io/archives/category/cosplay"),
    ("miaoyinshe", "https://www.miaoyinshe.com/cosplay"),
    ("miaohuaying", "https://www.miaohuaying.com/cosplay/"),
    ("xiaomiaoshe", "https://www.xiaomiaoshe.com/cosplay/"),
]

LEGACY_SOURCES = [
    ("06se", "https://www.06se.com/cos"),
    ("mzt", "https://www.mzitu.com/xinggan"),
    ("xmt", "http://www.xgmmtk.com/"),
    ("amn", "https://www.2meinv.com/tags-Cosplay-1.html"),
    ("mm131", "https://mm131.pro/e/action/ListInfo/?classid=1"),
    ("ytu", "https://www.yeitu.com/meinv/xinggan"),
]


def probe(url):
    session = build_session(retries=0)
    last_status = "request_error"
    for attempt in range(2):
        try:
            response = session.get(url, timeout=min(DEFAULT_TIMEOUT, 3), verify=VERIFY_TLS)
        except requests.exceptions.ConnectionError:
            host = url.split("//", 1)[1].split("/", 1)[0]
            try:
                socket.getaddrinfo(host, None)
            except socket.gaierror:
                return "dns_failed"
            last_status = "connection_error"
        except requests.RequestException:
            last_status = "request_error"
        else:
            if response.status_code == 200:
                return "ok"
            last_status = "http_{}".format(response.status_code)

        if attempt == 0:
            time.sleep(1)

    return last_status


def main():
    sources = list(PRIMARY_SOURCES)
    if os.environ.get("SOURCE_HEALTH_INCLUDE_LEGACY", "0").lower() in ("1", "true", "yes", "on"):
        sources.extend(LEGACY_SOURCES)

    for source_name, url in sources:
        print("{}\t{}\t{}".format(source_name, probe(url), url))


if __name__ == "__main__":
    main()
