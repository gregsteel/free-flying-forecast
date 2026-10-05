import hashlib
import hmac
import json
import random
from urllib.parse import unquote

import pytest

from ffforecast import livetrack24 as lt
from ffforecast.livetrack24 import Client, LiveTrack24Error

KEY, SECRET = "TESTKEY", "test-secret-1234"


def decrypt(passe: str, key: str) -> str:
    """The inverse of the manual's encryptWithKey, to prove the round trip."""
    import base64

    raw = base64.b64decode(passe.translate(str.maketrans("-_,", "+/=")) + "=" * (-len(passe) % 4))
    offset, multi = raw[0], raw[1]
    help_key = "!" + key
    out = []
    for i, code in enumerate(raw[2:]):
        pos = (i * multi + offset) % len(key)
        sign = 1 if ord(help_key[pos]) & 1 else -1
        out.append((code - (ord(key[pos]) & 0x3F) * sign) % 256)
    return bytes(out).decode()


def test_the_otp_answer_is_the_first_16_hex_digits_of_the_hmac():
    want = hmac.new(b"secret", b"question", hashlib.sha256).hexdigest()[:16]
    assert lt.otp_answer("question", "secret") == want and len(want) == 16


def test_an_encrypted_password_can_be_read_back_with_the_key():
    for pw in ("hunter2", "pässwörd 123!", "a"):
        assert decrypt(lt.encrypt_password(pw, SECRET, random.Random(5)), SECRET) == pw


def test_encrypted_passwords_differ_each_time_and_are_url_safe():
    a, b = lt.encrypt_password("pw", SECRET), lt.encrypt_password("pw", SECRET)
    assert all(c.isalnum() or c in "-_" for c in a + b)  # no + / = or comma


def test_low_and_non_ascii_characters_survive_the_wrap_round():
    for pw in ("  ~~  ", "\u20ac uro", "\x20\x21"):  # space is below the key's offset: it wraps
        assert decrypt(lt.encrypt_password(pw, SECRET, random.Random(1)), SECRET) == pw


def test_delta_unpacking_follows_the_manual():
    assert lt.unpack_delta("100,5,3,-2,4") == [100, 105, 108, 106, 110]
    assert lt.unpack_delta("100,5-3") == [100, 105, 102]  # "-" starts a negative change
    assert lt.unpack_delta("7") == [7]


def test_a_track_string_becomes_metres_degrees_and_times():
    t = lt.unpack_track(
        "pilot:77:1000,60,60:-2200000,10,-5:8800000,20,10:150000,5000,-300:300,-20:90,1:0,0:50,-10"
    )
    assert (t["username"], t["user_id"]) == ("pilot", "77")
    assert t["times"] == [1000, 1060, 1120]
    assert t["lats"][0] == pytest.approx(-2200000 / 60000)
    assert t["alts_m"] == [1500.0, 1550.0, 1547.0]
    assert t["courses_deg"] == [180, 182]  # the course is doubled
    assert t["varios_ms"][0] == 0.5


def test_a_short_track_string_is_refused():
    with pytest.raises(LiveTrack24Error):
        lt.unpack_track("only:three:fields")


# ---- a pretend LiveTrack24 that checks the one-time-password rules


class Server:
    def __init__(self, allowed_key=KEY, needs_login=True):
        self.n = 0
        self.question = ""
        self.allowed_key = allowed_key
        self.needs_login = needs_login
        self.logged_in = False
        self.urls: list[str] = []

    def _new(self):
        self.n += 1
        self.question = f"q{self.n:04d}"
        return self.question

    def __call__(self, url: str) -> str:
        self.urls.append(url)
        path = url.removeprefix(lt.BASE).split("/")
        op = path[0]
        kv = dict(zip(path[1::2], path[2::2], strict=False))
        if kv.get("ak") != self.allowed_key:
            return json.dumps(
                {"qwe": "", "newqwe": 1, "error": "No access for this appKey from IP: 1.2.3.4"}
            )
        right = lt.otp_answer(self.question, SECRET) if self.question else None
        if kv.get("vc") != right:
            return json.dumps({"qwe": self._new(), "newqwe": 1, "error": "Wrong OTP"})
        if op == "6":
            user, passe = unquote(kv["username"]), unquote(kv["passe"])
            if decrypt(passe, SECRET) != "right-password":
                return json.dumps({"qwe": self._new(), "error": "Wrong password"})
            self.logged_in = True
            return json.dumps(
                {"qwe": self._new(), "error": "", "userID": "11", "ut": "token", "username": user}
            )
        if self.needs_login and not self.logged_in:
            return json.dumps({"qwe": self._new(), "reLogin": 1, "error": "No user logged in"})
        if op == "ping":
            return json.dumps({"qwe": self._new(), "ip": "9.9.9.9"})
        return json.dumps({"qwe": self._new(), "op": op, "params": kv})


def client(server, password="right-password", pauses=None):
    return Client(
        KEY,
        SECRET,
        "someone",
        password,
        server,
        "device1",
        sleep=(pauses if pauses is not None else []).append,
    )


def test_a_first_call_gets_a_question_then_answers_it_and_logs_in():
    s = Server()
    r = client(s).call("30", lat=-36.76, lon=146.97, radius=5, ago=3600)
    assert r["op"] == "30" and r["params"]["radius"] == "5" and s.logged_in
    assert any("/di/device1/ut/" in u for u in s.urls)  # the identity was added when asked for


def test_a_second_call_needs_no_new_login():
    s, c = Server(), None
    c = client(s)
    c.call("ping")
    before = len(s.urls)
    c.call("ping")
    assert len(s.urls) - before == 1 and sum("/op/6/" in u for u in s.urls) == 1


def test_a_wrong_password_is_reported_without_the_password():
    with pytest.raises(LiveTrack24Error) as e:
        client(Server(), "wrong").call("ping")
    assert "login failed" in str(e.value) and "wrong" not in str(e.value)


def test_a_key_not_allowed_from_this_address_is_a_clear_error():
    with pytest.raises(LiveTrack24Error, match="No access for this appKey"):
        client(Server(allowed_key="OTHER")).call("ping")


def test_calls_are_paused_and_capped():
    pauses: list[float] = []
    s = Server()
    c = client(s, pauses=pauses)
    c.call("ping")
    assert pauses and all(p == lt.PAUSE_S for p in pauses)
    c.calls = lt.MAX_CALLS
    with pytest.raises(LiveTrack24Error, match="stopped after"):
        c.call("ping")


def test_the_url_follows_the_documented_format():
    s = Server()
    client(s).call("30", lat=1.5, lon=2.5, radius=5, ago=60)
    first = s.urls[0]
    assert first.startswith(
        "https://api.livetrack24.com/api/v2/op/30/lat/1.5/lon/2.5/radius/5/ago/60"
    )
    assert "/ak/TESTKEY/vc/" in first


def test_the_secret_and_password_never_appear_in_a_url():
    s = Server()
    client(s).call("ping")
    assert not any(SECRET in u or "right-password" in u for u in s.urls)


def test_names_are_hidden_in_a_reply_but_nothing_else():
    reply = {
        "users": [{"username": "someone", "userID": "7", "alt": 1500, "displayName": "Some One"}]
    }
    assert lt.redact(reply) == {
        "users": [{"username": "***", "userID": "7", "alt": 1500, "displayName": "***"}]
    }


def test_the_probe_command_names_the_missing_settings(monkeypatch, capsys):
    from ffforecast import cli

    for name in cli.LT24_ENV:
        monkeypatch.delenv(name, raising=False)
    assert cli.main(["lt24-probe"]) == 2
    err = capsys.readouterr().err
    assert all(name in err for name in cli.LT24_ENV)
