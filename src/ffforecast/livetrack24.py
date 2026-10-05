"""A reader for LiveTrack24's API v2 (https://www.livetrack24.com/docs/api).

Written from LiveTrack24's own manual and PHP samples; not yet run against the live service, which
needs an application key and secret (free from LiveTrack24 on request, and tied to the IP address the
calls come from) and a user's login. Everything here is read-only. XCSoar's LiveTrack24 code is not a
guide to it: that only uploads a pilot's own track.

How a call works: each reply carries a one-time-password question (`qwe`); the next call must answer
it with `vc`, the first 16 hex digits of HMAC-SHA256(question, appSecret). A reply of `newqwe: 1`
means the call is repeated with the device id (`di`) and user token (`ut`) added; `reLogin: 1` means
logging in again first.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import random
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

BASE = "https://api.livetrack24.com/api/v2/op/"
PAUSE_S = 1.0  # between calls
MAX_CALLS = 60  # one run never makes more than this many


class LiveTrack24Error(Exception):
    """A call could not be made or LiveTrack24 refused it. The message is safe to show."""


def otp_answer(question: str, app_secret: str) -> str:
    """`vc`: the first 16 hex digits of HMAC-SHA256 of the question, keyed with the app secret."""
    return hmac.new(app_secret.encode(), question.encode(), hashlib.sha256).hexdigest()[:16]


def encrypt_password(password: str, key: str, rand: random.Random | None = None) -> str:
    """The manual's `encryptWithKey`: the `passe` form of a password, so it is not sent as plain
    text. Like the PHP original it works on the password's bytes (UTF-8) and a result outside 0 to
    255 wraps round, as PHP's chr() does."""
    r = rand or random.Random()
    offset, multi = r.randint(0, 255), r.randint(0, 255)
    out = bytearray([offset, multi])
    help_key = "!" + key
    for i, byte in enumerate(password.encode()):
        pos = (i * multi + offset) % len(key)
        sign = 1 if ord(help_key[pos]) & 1 else -1
        out.append((byte + (ord(key[pos]) & 0x3F) * sign) % 256)
    text = base64.b64encode(bytes(out)).decode()
    return text.translate(str.maketrans("+/=", "-_,")).rstrip(",")


def unpack_delta(packed: str) -> list[int]:
    """A track field is a base value followed by changes: '-' starts a negative change, and the
    values are separated by commas. Each value after the first is added to the one before."""
    text = "".join(
        f",{c}" if c == "-" and i and packed[i - 1] != "," else c for i, c in enumerate(packed)
    )
    values = [int(x) for x in text.split(",") if x != ""]
    for i in range(1, len(values)):
        values[i] += values[i - 1]
    return values


def unpack_track(track: str) -> dict[str, Any]:
    """One track string from `getTrackPoints`:
    `username:userID:times:lats:lons:alts:sogs:cogs:agls:varios`, each field delta packed.
    As the manual gives them: latitude and longitude are divided by 60000 (degrees), altitude by
    100 (metres), vario by 100 (m/s), and the course is doubled (degrees)."""
    f = track.split(":")
    if len(f) < 10:
        raise LiveTrack24Error("a track string has fewer fields than the manual describes")
    n = unpack_delta
    return {
        "username": f[0],
        "user_id": f[1],
        "times": n(f[2]),
        "lats": [v / 60000 for v in n(f[3])],
        "lons": [v / 60000 for v in n(f[4])],
        "alts_m": [v / 100 for v in n(f[5])],
        "speeds": n(f[6]),
        "courses_deg": [v * 2 for v in n(f[7])],
        "agls_m": n(f[8]),
        "varios_ms": [v / 100 for v in n(f[9])],
    }


class Client:
    """Calls LiveTrack24 on behalf of a user. `transport(url) -> str` fetches a URL (injected so
    tests need no network)."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        username: str,
        password: str,
        transport: Callable[[str], str],
        device_id: str,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._key, self._secret = app_key, app_secret
        self._user, self._password = username, password
        self._get = transport
        self.device_id = device_id
        self._sleep = sleep
        self._qwe = ""
        self._ut = "0"
        self.calls = 0

    def _url(self, op: str, params: dict[str, Any], with_identity: bool) -> str:
        path = "/".join(
            [quote(str(op), safe="")]
            + [part for k, v in params.items() for part in (quote(str(k)), quote(str(v), safe=","))]
        )
        url = f"{BASE}{path}/ak/{self._key}/vc/{otp_answer(self._qwe, self._secret)}"
        if with_identity:
            url += f"/di/{self.device_id}/ut/{quote(self._ut, safe='')}"
        return url

    def _once(self, op: str, params: dict[str, Any], with_identity: bool) -> dict[str, Any]:
        import json

        if self.calls >= MAX_CALLS:
            raise LiveTrack24Error(f"stopped after {MAX_CALLS} calls in one run")
        if self.calls:
            self._sleep(PAUSE_S)
        self.calls += 1
        try:
            reply = json.loads(self._get(self._url(op, params, with_identity)))
        except (ValueError, OSError) as e:
            raise LiveTrack24Error(
                f"could not read LiveTrack24's reply ({type(e).__name__})"
            ) from e
        if not isinstance(reply, dict):
            raise LiveTrack24Error("LiveTrack24's reply was not a JSON object")
        if "ut" in reply:
            self._ut = str(reply["ut"])
        if "qwe" in reply:
            self._qwe = str(reply["qwe"])
        return reply

    def call(self, op: str, **params: Any) -> dict[str, Any]:
        """One operation, following the manual's calling sequence. Raises LiveTrack24Error on a
        refusal (wrong key, key not allowed from this address, bad login)."""
        reply = self._once(op, params, False)
        if reply.get("newqwe"):
            reply = self._once(op, params, True)
        if reply.get("reLogin"):
            self._login()
            reply = self._once(op, params, True)
            if reply.get("reLogin"):
                raise LiveTrack24Error("LiveTrack24 would not keep the login")
        if reply.get("error"):
            raise LiveTrack24Error(str(reply["error"]))
        return reply

    def _login(self) -> None:
        reply = self._once(
            "6",
            {"username": self._user, "passe": encrypt_password(self._password, self._secret)},
            True,
        )
        if reply.get("newqwe"):  # answer the new question and try once more
            reply = self._once(
                "6",
                {"username": self._user, "passe": encrypt_password(self._password, self._secret)},
                True,
            )
        if reply.get("error") or not reply.get("userID"):
            raise LiveTrack24Error(f"login failed: {reply.get('error') or 'no user returned'}")

    # --- the reads the verification needs (names and parameters from the PHP samples)

    def waypoints_near(self, lat: float, lon: float, radius_km: float, limit: int = 3) -> dict:
        """Op 3, 'List takeoffs': the waypoints around a point."""
        return self.call("3", lat=lat, lon=lon, radius=radius_km, limit=limit)

    def users_near(self, lat: float, lon: float, radius_km: float, ago_s: int) -> dict:
        """Op 30, 'Minimal Info': the last position of users active within `ago_s` seconds."""
        return self.call("30", lat=lat, lon=lon, radius=radius_km, ago=ago_s)

    def track_points(self, user_ids: list[str], track_ids: list[str] | None = None, **kw: Any):
        """`getTrackPoints`: the points of the given users and/or tracks, delta packed."""
        params: dict[str, Any] = {"userIDs": ",".join(user_ids)}
        if track_ids:
            params["trackIDs"] = ",".join(track_ids)
        params.update(kw)
        return self.call("getTrackPoints", **params)


_NAME_KEYS = ("username", "displayname", "name", "userlist", "pilot")


def redact(value: Any) -> Any:
    """A copy of a reply with people's names replaced by '***', for showing what it looks like
    without showing who."""
    if isinstance(value, dict):
        return {
            k: ("***" if str(k).lower() in _NAME_KEYS and isinstance(v, str) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value
