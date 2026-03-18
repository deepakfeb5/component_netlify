# ============================================================
# Mouser Client (FINAL PRODUCTION VERSION)
# ============================================================
import requests, time, random, json, os
from typing import Any, Dict, List, Optional, Tuple

# Retry / timeout constants
MAX_RETRIES = 5
TIMEOUT = 10
BACKOFF_BASE = 1.5
BACKOFF_CAP = 4.0

session = requests.Session()


# ------------------------------------------------------------
# Lightweight API Rate Limiter
# ------------------------------------------------------------
class RateLimiter:
    def __init__(self, per_sec: float = 3):
        self.delay = 1.0 / per_sec
        self.last_call = 0.0

    def wait(self):
        now = time.time()
        diff = now - self.last_call
        if diff < self.delay:
            time.sleep(self.delay - diff)
        self.last_call = time.time()


rate_limiter = RateLimiter(3)  # 3 requests per second


# ============================================================
# MouserClient
# ============================================================
class MouserClient:
    SEARCH_URL = "https://api.mouser.com/api/v1/search/partnumber"

    def __init__(self, api_key: Optional[str]):
        # ✅ Ensure MOUSER_API_KEY is loaded correctly
        self.api_key = (api_key or "").strip()

        # ✅ In-memory cache to reduce API calls
        # { mpn → (main_data, alternates, error) }
        self.cache: Dict[str, Tuple[
            Optional[Dict[str, Any]],
            List[str],
            Optional[str]
        ]] = {}

    # --------------------------------------------------------
    def _backoff_sleep(self, attempt: int):
        delay = min(BACKOFF_CAP, (BACKOFF_BASE ** attempt)) + random.random() * 0.25
        time.sleep(delay)

    # --------------------------------------------------------
    def _post_once(self, mpn: str) -> requests.Response:
        rate_limiter.wait()
        return session.post(
            self.SEARCH_URL,
            params={"apiKey": self.api_key},
            json={"SearchByPartRequest": {"mouserPartNumber": mpn}},
            timeout=TIMEOUT,
        )

    # --------------------------------------------------------
    def search_part(self, mpn: str) -> Tuple[
        Optional[Dict[str, Any]],
        List[str],
        Optional[str]
    ]:
        """
        Returns:
            (main_data, alternates, error)

        main_data = {
            "price": str|None,
            "manufacturer": str|None,
            "stock": str|None,
            "lifecycle": str|None
        }
        alternates = [ "ALT-XYZ", ... ]
        error = "No results" | "Missing MOUSER_API_KEY" | "HTTP 403..." | None
        """

        key = (mpn or "").strip()

        # ✅ Return cached result if available
        if key in self.cache:
            return self.cache[key]

        # ✅ If API KEY missing (your screenshot case)
        if not self.api_key:
            result = (None, [], "Missing MOUSER_API_KEY")
            self.cache[key] = result
            return result

        last_exc: Optional[Exception] = None

        # ======================================================
        # Retry loop
        # ======================================================
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self._post_once(key)
            except Exception as e:
                last_exc = e
                self._backoff_sleep(attempt)
                continue

            # --------------------------------------------------
            # ✅ Success (HTTP 200)
            # --------------------------------------------------
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except json.JSONDecodeError:
                    result = (None, [], "Invalid JSON response from Mouser")
                    self.cache[key] = result
                    return result

                parts = data.get("SearchResults", {}).get("Parts", []) or []

                # ✅ No results for MPN
                if not parts:
                    result = (None, [], "No results")
                    self.cache[key] = result
                    return result

                # ✅ MAIN PART (first part)
                main = parts[0]

                alternates = [
                    (p.get("ManufacturerPartNumber") or "").strip()
                    for p in parts[1:]
                    if p.get("ManufacturerPartNumber")
                ]

                price_breaks = main.get("PriceBreaks", []) or []
                unit_price = (
                    price_breaks[0].get("Price")
                    if price_breaks else None
                )

                main_data = {
                    "price": unit_price,
                    "manufacturer": main.get("Manufacturer"),
                    "stock": main.get("Availability"),
                    "lifecycle": main.get("LifecycleStatus"),
                }

                result = (main_data, alternates, None)
                self.cache[key] = result
                return result

            # --------------------------------------------------
            # ✅ Mouser rate-limiting (429, 403)
            # --------------------------------------------------
            if resp.status_code in (403, 429):
                try:
                    body = resp.json()
                except Exception:
                    body = {}

                err_list = body.get("Errors") or []
                code = (err_list[0] or {}).get("Code") if err_list else None

                if code == "TooManyRequests":
                    self._backoff_sleep(attempt)
                    continue

            # --------------------------------------------------
            # ✅ Other HTTP errors
            # --------------------------------------------------
            snippet = (resp.text or "").strip()[:300]
            result = (None, [], f"HTTP {resp.status_code}: {snippet}")
            self.cache[key] = result
            return result

        # ======================================================
        # If exhausted retries
        # ======================================================
        if last_exc:
            result = (None, [], f"Network error: {last_exc}")
            self.cache[key] = result
            return result

        result = (None, [], "Request failed after retries")
        self.cache[key] = result
        return result
