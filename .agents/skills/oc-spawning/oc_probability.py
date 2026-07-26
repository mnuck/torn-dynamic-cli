"""Client for the unofficial tornprobability.com OC success-probability API.

This is a free, unauthenticated, third-party service (not run by Torn or by
us) documented at https://www.torn.com/forums.php#/p=threads&f=67&t=16449041
with a swagger spec at https://tornprobability.com:3000/api-docs/. No
published SLA or rate limit — treat every call as best-effort enrichment,
never as something the pipeline depends on.

Given a crime's per-slot checkpoint_pass_rate values, /CalculateSuccess
returns a modeled successChance/failureChance (plus per-ending breakdowns)
for that specific team composition. The tricky part is ordering: Torn's own
slots carry a position_info.number (1, 2, 3, ... for duplicate positions
like "Imitator #1/#2/#3"), but tornprobability's own P1..Pn indexing (from
/GetRoleNames) groups by role name in its own order (e.g. all Imitators
before all Looters) — the two P-numbering schemes are unrelated. We bridge
them by name: build "{position} {number}" (or bare position name when a
scenario has no duplicates of it) and look that string up in the role-name
map for the scenario to find the correct parameter index.
"""

import json
import ssl
import time
import urllib.error
import urllib.request

BASE_URL = "https://tornprobability.com:3000/api"
TIMEOUT = 10
USER_AGENT = "torn-dynamic-cli-oc-probability/1.0"


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_SSL_CTX = _ssl_context()


class RateLimiter:
    """Blocks callers so calls are spaced at most `per_second` apart."""

    def __init__(self, per_second=2.0):
        self.min_interval = 1.0 / per_second
        self._last = 0.0

    def wait(self):
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()


def _request(path, method="GET", body=None, retries=2):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/json"
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_SSL_CTX) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.0)
    raise RuntimeError(f"tornprobability.com request failed ({path}): {last_err}")


def get_supported_scenarios():
    """{scenario name: expected parameter count}."""
    data = _request("/GetSupportedScenarios")
    return {s["name"]: s["parameters"] for s in data}


def get_role_names():
    """{scenario name: {"P1": "Imitator 1", ...}} as tornprobability defines it."""
    return _request("/GetRoleNames")


def _role_index_map(role_map):
    """{"P1": "Imitator 1", ...} -> {"Imitator 1": 0, ...} (0-based param index)."""
    idx = {}
    for key, name in role_map.items():
        idx[name] = int(key[1:]) - 1
    return idx


def _candidate_names(slot):
    pos = slot.get("position") or ""
    info = slot.get("position_info") or {}
    number = info.get("number")
    names = []
    if number is not None:
        names.append(f"{pos} {number}")
    names.append(pos)
    return names


def build_parameters(crime, role_index, n_params):
    """Ordered CPR list for /CalculateSuccess, or None if data is unusable.

    Bails (returns None) rather than guessing on: unfilled slots, missing
    CPR, a slot whose role name doesn't map cleanly, or an index collision —
    a wrong guess here silently corrupts the result, so we skip instead.
    """
    params = [None] * n_params
    for slot in crime.get("slots", []):
        if not slot.get("user"):
            return None
        cpr = slot.get("checkpoint_pass_rate")
        if cpr is None:
            return None
        idx = next((role_index[c] for c in _candidate_names(slot) if c in role_index), None)
        if idx is None or not (0 <= idx < n_params) or params[idx] is not None:
            return None
        params[idx] = cpr
    if any(p is None for p in params):
        return None
    return params


def calculate_success(scenario, parameters, limiter):
    limiter.wait()
    return _request("/CalculateSuccess", method="POST",
                     body={"scenario": scenario, "parameters": parameters})


def enrich_crime(crime, scenarios, role_maps, limiter):
    """Mutates `crime` in place with an "oc_success_probability" key.

    Returns one of: "enriched", "already", "unsupported", "incomplete".
    Raises only on an actual API/network failure (caller's job to catch).
    """
    if "oc_success_probability" in crime:
        return "already"
    name = crime.get("name")
    n_params = scenarios.get(name)
    role_map = role_maps.get(name)
    if n_params is None or role_map is None:
        return "unsupported"
    role_index = _role_index_map(role_map)
    params = build_parameters(crime, role_index, n_params)
    if params is None:
        return "incomplete"
    result = calculate_success(name, params, limiter)
    crime["oc_success_probability"] = {
        "source": "tornprobability.com",
        "fetched_at": int(time.time()),
        "scenario": name,
        "parameters": params,
        "result": result,
    }
    return "enriched"


def enrich_crimes(crimes, limiter=None, on_each=None):
    """Best-effort enrichment pass over a list of crime dicts (mutated in place).

    A single crime's failure (network hiccup, unexpected shape) never stops
    the rest of the batch. Returns a status-name -> count dict.
    """
    limiter = limiter or RateLimiter(2.0)
    scenarios = get_supported_scenarios()
    role_maps = get_role_names()
    counts = {}
    for c in crimes:
        try:
            status = enrich_crime(c, scenarios, role_maps, limiter)
        except Exception:
            status = "error"
        counts[status] = counts.get(status, 0) + 1
        if on_each:
            on_each(c, status)
    return counts
