"""Opt-in public GETs, globally paced, with immutable response provenance.

No cookies, authentication, browser impersonation or alternate backend. One retry on a
transport error and never on an HTTP status: a store that answers 403 or 404 has answered,
and asking again is pressing a merchant who declined. HTTP access failures stop a store.
The default test suite never invokes this CLI.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html import unescape
import json
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

AGENT = "ApprovCatalogueAudit/1.0 (public catalogue readiness research)"
COHORT = Path(__file__).with_name("cohort.json")
_LOCK = threading.Lock()
_LAST = 0.0


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def policy_body(body):
    try:
        parsed = json.loads(body)
        if "policy" in parsed:
            return parsed["policy"]["body"] or ""
        if "page" in parsed:
            return parsed["page"].get("body_html", parsed["page"].get("body", "")) or ""
        return body
    except (ValueError, KeyError, TypeError):
        return body


def policy_excerpts(body):
    body = policy_body(body)
    text = unescape(re.sub(r"<[^>]+>", " ", body))
    text = re.sub(r"\s+", " ", text)
    return list(dict.fromkeys(text[max(0, m.start()-140):m.end()+180]
                             for m in re.finditer(r"scrap(?:e|ing)|crawl|spider|automated (?:access|means|system)|data min", text, re.I)))[:12]


def get(url, directory, name, interval=1.5):
    global _LAST
    meta_path = directory / (name + ".meta.json")
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        body = (directory / meta["body_file"]).read_bytes()
        if hashlib.sha256(body).hexdigest() != meta["sha256"]:
            raise ValueError("cached response hash mismatch: " + str(meta_path))
        return meta, body
    with _LOCK:
        time.sleep(max(0, _LAST + interval - time.monotonic()))
        _LAST = time.monotonic()
    meta = {"requested_url": url, "started_at": now(), "user_agent": AGENT}
    # A *transport* error is retried once; an HTTP status never is. The distinction is the
    # point of the no-retries rule, which exists so that a store saying no is recorded as
    # having said no -- retrying a 403 is pressing a merchant who declined, and retrying a
    # 404 invents a feed. A TLS handshake that failed says nothing about the merchant at
    # all, and treating it as a closure is how the first cohort scored six readable
    # cosmetics feeds as permanently unreachable: all six return 200 on a plain retry, and
    # the headline retrieval rate was understated by a fifth as a result.
    attempts = []
    for attempt in range(2):
        try:
            try:
                response = urlopen(Request(url, headers={"User-Agent": AGENT, "Accept": "application/json,text/html,text/plain"}), timeout=25)
            except HTTPError as error:
                response = error
            with response:
                body = response.read(24 * 1024 * 1024 + 1)
                meta.update(status=response.status, final_url=response.url,
                            content_type=response.headers.get("Content-Type"),
                            etag=response.headers.get("ETag"), last_modified=response.headers.get("Last-Modified"))
            if len(body) > 24 * 1024 * 1024:
                meta["error"] = "response_exceeds_byte_limit"
            break
        except (URLError, TimeoutError, OSError) as error:
            body = b""
            attempts.append(str(error))
            meta.update(status=None, error=str(error))
            if attempt == 0:
                with _LOCK:
                    time.sleep(max(0, _LAST + interval * 4 - time.monotonic()))
                    _LAST = time.monotonic()
    if attempts:
        meta["transport_attempts"] = attempts
    meta.update(finished_at=now(), bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), body_file=name + ".body")
    (directory / meta["body_file"]).write_bytes(body)
    save(meta_path, meta)
    return meta, body


def fetch_store(store, root, *, policies_only=False, max_pages=20, terms_policy="exclude"):
    sector, merchant, host = store
    directory = root / host
    directory.mkdir(parents=True, exist_ok=True)
    base = "https://" + host
    manifest = {"sector": sector, "merchant": merchant, "host": host, "started_at": now(),
                "selection": "frozen purposive cohort", "responses": [], "page_limit": max_pages,
                "pagination_complete": False, "products": 0}
    def request(path, name):
        meta, body = get(base + path, directory, name)
        manifest["responses"].append(meta)
        return meta, body
    robots_meta, robots = request("/robots.txt", "robots")
    policy_meta, policy = request("/policies/terms-of-service", "terms")
    policy_text = policy_body(policy.decode("utf-8", errors="replace"))
    # Some stores publish a short policy object linking their actual public terms.
    if policy_meta["status"] == 200 and len(policy_text) < 2000:
        links = re.findall(r'href=["\']([^"\']+)["\']', policy_text)
        link = next((urljoin(base, link) for link in links if "term" in link.lower()), None)
        if link and urlsplit(link).hostname in {host, host.removeprefix("www."), "www." + host.removeprefix("www.")}:
            policy_meta, policy = get(link, directory, "linked-terms")
            manifest["responses"].append(policy_meta)
    manifest["terms"] = {"status": policy_meta["status"], "url": policy_meta.get("final_url"),
                         "automation_excerpts": policy_excerpts(policy.decode("utf-8", errors="replace")),
                         "review": "Public terms fetched and keyword-screened; not legal clearance or permission to republish the corpus."}
    manifest["terms"]["collection_policy"] = terms_policy
    parser = RobotFileParser()
    parser.parse(robots.decode("utf-8", errors="replace").splitlines() if robots_meta["status"] == 200 else [])
    denied = robots_meta["status"] in (401, 403, 429) or (robots_meta["status"] == 200 and not parser.can_fetch(AGENT, base + "/products.json?limit=250&page=1"))
    manifest["robots_allows_feed"] = not denied
    if policies_only:
        manifest["status"] = "policies_checked"
    elif denied:
        manifest["status"] = "robots_disallows_or_access_denied"
    elif terms_policy == "exclude" and manifest["terms"]["automation_excerpts"]:
        manifest["status"] = "terms_automation_restriction_requires_review"
    elif terms_policy == "exclude" and policy_meta["status"] != 200:
        manifest["status"] = "terms_unavailable"
    else:
        records, seen = [], set()
        manifest["status"] = "page_limit"
        for page in range(1, max_pages + 1):
            meta, body = request(f"/products.json?limit=250&page={page}", f"products-{page:03d}")
            if meta["status"] != 200 or meta.get("error"):
                manifest["status"] = "http_or_transport_failure"
                break
            try:
                payload = json.loads(body)
                products = payload["products"]
                if not isinstance(products, list) or not all(isinstance(p, dict) for p in products):
                    raise ValueError("products must be a list of records")
            except (ValueError, KeyError, TypeError) as error:
                manifest["status"] = "not_a_product_feed"
                manifest["error"] = str(error)
                break
            if meta["sha256"] in seen and products:
                manifest["status"] = "repeated_page"
                break
            seen.add(meta["sha256"])
            records.extend(products)
            if len(products) < 250:
                manifest["status"] = "complete" if records else "empty_feed"
                manifest["pagination_complete"] = True
                break
        save(directory / "products.json", records)
        manifest["products"] = len(records)
        manifest["products_sha256"] = hashlib.sha256((directory / "products.json").read_bytes()).hexdigest()
    manifest["finished_at"] = now()
    save(directory / "manifest.json", manifest)
    print(f"{host}: {manifest['status']}, {manifest['products']} products", flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("--policies-only", action="store_true")
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--terms-policy", choices=("exclude", "record-only"), default="exclude",
                        help="record-only requires an explicit study-owner ruling on the archived restrictions")
    args = parser.parse_args()
    if args.max_pages < 1:
        parser.error("--max-pages must be positive")
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    args.cache.mkdir(parents=True, exist_ok=True)
    save(args.cache / "cohort.json", cohort)
    with ThreadPoolExecutor(max_workers=2) as pool:
        manifests = list(pool.map(lambda store: fetch_store(store, args.cache, policies_only=args.policies_only, max_pages=args.max_pages, terms_policy=args.terms_policy), cohort["stores"]))
    save(args.cache / "manifest.json", {"cohort": cohort, "stores": manifests, "completed_at": now()})


if __name__ == "__main__":
    main()
