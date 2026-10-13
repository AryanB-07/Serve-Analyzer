"""Changing an account's email, downloading your data, and reporting a result that looks wrong."""

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from serve_api import keys, reports
from serve_api.db import now
from serve_api.storage import LocalStorage
from serve_api.tables import result_reports
from tests.test_account import (  # noqa: F401  (fixtures)
    PASSWORD,
    app,
    client,
    db_of,
    mailer,
    settings,
    signup,
    token_from,
    uploaded_analysis,
    verify,
)


def change(client: TestClient, new_email: str, password: str = PASSWORD):
    return client.post("/auth/email-change", json={"new_email": new_email, "password": password})


def finished(app, settings, client: TestClient, status: str = "succeeded", results: dict | None = None) -> str:
    """An analysis that finished with ``status``, its upload and results in storage."""
    analysis_id = uploaded_analysis(client, settings)
    if results is not None:
        path = LocalStorage(settings).path(keys.output_key(analysis_id, keys.RESULTS))
        path.write_text(json.dumps(results))
    fields = {"error_code": "NOT_A_SERVE", "error_message": "This doesn't look like a serve."} if status == "failed" else {}
    db_of(app).set_status(analysis_id, status, **fields)
    return analysis_id


# --- changing your email ----------------------------------------------------------------

def test_changing_email_needs_the_link_sent_to_the_new_address(app, client, mailer):
    old = signup(client)
    verify(client, mailer, old)
    assert change(client, "New@Example.com").status_code == 202
    message = mailer.sent[-1]
    assert message.to == "new@example.com" and "/confirm-email?token=" in message.text
    # Nothing changes until the link is opened.
    assert client.get("/auth/me").json()["email"] == old

    res = TestClient(app).post("/auth/email-change/confirm", json={"token": token_from(mailer.last_link())})
    assert res.status_code == 204
    me = client.get("/auth/me").json()  # the existing session carries on
    assert me["email"] == "new@example.com" and me["email_verified"] is True
    assert mailer.sent[-1].to == old and "new@example.com" in mailer.sent[-1].text
    assert client.post("/auth/login", json={"email": "new@example.com", "password": PASSWORD}).status_code == 200
    assert client.post("/auth/login", json={"email": old, "password": PASSWORD}).status_code == 401


def test_an_email_change_link_works_once_and_only_the_latest(client, mailer):
    signup(client)
    change(client, "first@example.com")
    first = token_from(mailer.last_link("first@example.com"))
    change(client, "second@example.com")
    second = token_from(mailer.last_link("second@example.com"))
    assert client.post("/auth/email-change/confirm", json={"token": first}).status_code == 400
    assert client.post("/auth/email-change/confirm", json={"token": second}).status_code == 204
    assert client.post("/auth/email-change/confirm", json={"token": second}).status_code == 400
    assert client.get("/auth/me").json()["email"] == "second@example.com"


def test_other_links_cannot_change_the_email(client, mailer):
    email = signup(client)
    verification = token_from(mailer.last_link(email))
    assert client.post("/auth/email-change/confirm", json={"token": verification}).status_code == 400
    change(client, "new@example.com")
    link = token_from(mailer.last_link("new@example.com"))
    assert client.post("/auth/verify-email", json={"token": link}).status_code == 400


def test_changing_email_needs_the_password_and_a_free_new_address(app, client, mailer):
    email = signup(client)
    signup(TestClient(app), "taken@example.com")
    assert change(client, "new@example.com", "wrong password").status_code == 403
    assert change(client, "Taken@example.com").status_code == 409
    assert change(client, email.upper()).status_code == 400
    assert client.post("/auth/email-change", json={"new_email": "nope", "password": PASSWORD}).status_code == 422
    assert not any(m.to in ("new@example.com", "taken@example.com") and "Confirm your new" in m.subject
                   for m in mailer.sent)


def test_an_address_taken_after_the_link_was_sent_is_refused(app, client, mailer):
    email = signup(client)
    change(client, "contested@example.com")
    token = token_from(mailer.last_link("contested@example.com"))
    signup(TestClient(app), "contested@example.com")
    assert client.post("/auth/email-change/confirm", json={"token": token}).status_code == 409
    assert client.get("/auth/me").json()["email"] == email


def test_email_change_requests_are_limited(client, mailer):
    signup(client)  # the signup's verification email counts too
    assert [change(client, f"n{i}@example.com").status_code for i in range(3)] == [202, 202, 429]


def test_wrong_passwords_when_changing_email_are_rate_limited(client):
    signup(client)
    for _ in range(10):
        change(client, "new@example.com", "nope")
    assert change(client, "new@example.com").status_code == 429


# --- downloading your data --------------------------------------------------------------

def test_the_export_holds_the_account_and_every_analysis(app, client, mailer, settings):
    email = signup(client)
    verify(client, mailer, email)
    done = finished(app, settings, client, results={"hand": "right", "phases": {"contact": 30}})
    failed = finished(app, settings, client, status="failed")
    client.put(f"/analyses/{failed}/report", json={"reason": "was_a_serve", "note": "It was!"})

    res = client.get("/auth/me/export")
    assert res.status_code == 200
    assert res.headers["content-disposition"].startswith('attachment; filename="serve-analyzer-data-')
    assert res.headers["cache-control"] == "no-store"
    data = res.json()
    assert data["account"]["email"] == email and data["account"]["email_verified"] is True
    assert data["account"]["terms_version"]
    by_id = {a["id"]: a for a in data["analyses"]}
    assert list(by_id) == [done, failed]  # oldest first
    assert by_id[done]["results"] == {"hand": "right", "phases": {"contact": 30}}
    assert set(by_id[done]["files"]) == {"original_video", "playback_video", "annotated_video", "thumbnail", "frames"}
    assert by_id[failed]["results"] is None and set(by_id[failed]["files"]) == {"original_video"}
    assert by_id[failed]["error"]["code"] == "NOT_A_SERVE"
    assert by_id[failed]["report"]["reason"] == "was_a_serve" and by_id[failed]["report"]["note"] == "It was!"
    # The links work for the person who exported.
    original = client.get(by_id[done]["files"]["original_video"])
    assert original.status_code == 200 and original.content == b"x"


def test_the_export_leaves_out_other_peoples_data_and_expired_videos(app, client, mailer, settings):
    verify(client, mailer, signup(client))
    mine = finished(app, settings, client, results={"hand": "right"})
    db_of(app).mark_input_deleted(mine)
    other = TestClient(app)
    verify(other, mailer, signup(other))
    finished(app, settings, other, results={"hand": "left"})
    data = client.get("/auth/me/export").json()
    assert [a["id"] for a in data["analyses"]] == [mine]
    assert "original_video" not in data["analyses"][0]["files"]
    assert data["analyses"][0]["original_video_deleted_at"] is not None


def test_exports_need_a_session_and_are_limited(app, client):
    assert TestClient(app).get("/auth/me/export").status_code == 401
    signup(client)
    assert [client.get("/auth/me/export").status_code for _ in range(6)] == [200] * 5 + [429]


# --- reporting a result that looks wrong ------------------------------------------------

def test_a_finished_analysis_can_be_reported_and_the_report_replaced(app, client, mailer, settings):
    verify(client, mailer, signup(client))
    analysis_id = finished(app, settings, client)
    assert client.get(f"/analyses/{analysis_id}/report").json() is None
    res = client.put(f"/analyses/{analysis_id}/report", json={"reason": "not_a_serve", "note": "  a smash  "})
    assert res.status_code == 200 and res.json()["note"] == "a smash"
    client.put(f"/analyses/{analysis_id}/report", json={"reason": "wrong_phases", "note": "   "})
    report = client.get(f"/analyses/{analysis_id}/report").json()
    assert report["reason"] == "wrong_phases" and report["note"] is None
    with db_of(app).engine.connect() as conn:
        row = conn.execute(select(result_reports)).mappings().one()
    assert row["status"] == "succeeded" and row["error_code"] is None


def test_reasons_must_fit_how_the_analysis_ended(app, client, mailer, settings):
    verify(client, mailer, signup(client))
    done, failed = finished(app, settings, client), finished(app, settings, client, status="failed")
    assert client.put(f"/analyses/{done}/report", json={"reason": "was_a_serve"}).status_code == 422
    assert client.put(f"/analyses/{failed}/report", json={"reason": "wrong_phases"}).status_code == 422
    assert client.put(f"/analyses/{failed}/report", json={"reason": "was_a_serve"}).status_code == 200
    assert client.put(f"/analyses/{done}/report", json={"reason": "made_up"}).status_code == 422
    assert client.put(f"/analyses/{done}/report", json={"reason": "other", "note": "x" * 1001}).status_code == 422
    waiting = uploaded_analysis(client, settings)
    assert client.put(f"/analyses/{waiting}/report", json={"reason": "other"}).status_code == 409


def test_nobody_else_can_report_or_read_your_report(app, client, mailer, settings):
    verify(client, mailer, signup(client))
    analysis_id = finished(app, settings, client)
    client.put(f"/analyses/{analysis_id}/report", json={"reason": "other", "note": "private"})
    stranger = TestClient(app)
    signup(stranger)
    assert stranger.get(f"/analyses/{analysis_id}/report").status_code == 404
    assert stranger.put(f"/analyses/{analysis_id}/report", json={"reason": "other"}).status_code == 404


def test_reports_are_deleted_with_their_analysis_and_account(app, client, mailer, settings):
    verify(client, mailer, signup(client))
    first, second = finished(app, settings, client), finished(app, settings, client)
    for analysis_id in (first, second):
        client.put(f"/analyses/{analysis_id}/report", json={"reason": "other"})
    db = db_of(app)

    def count():
        with db.engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(result_reports)).scalar_one()

    client.delete(f"/analyses/{first}")
    assert count() == 1
    client.request("DELETE", "/auth/me", json={"password": PASSWORD})
    assert count() == 0


def test_the_operator_can_list_reports_as_csv(app, client, mailer, settings, monkeypatch, capsys):
    verify(client, mailer, signup(client))
    done, failed = finished(app, settings, client), finished(app, settings, client, status="failed")
    client.put(f"/analyses/{done}/report", json={"reason": "not_a_serve", "note": "a smash,\nfrom the side"})
    client.put(f"/analyses/{failed}/report", json={"reason": "was_a_serve"})
    db_of(app).mark_input_deleted(failed)
    monkeypatch.setenv("SERVE_API_DATA_DIR", str(settings.data_dir))
    reports.main([])
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert [(r["analysis_id"], r["reason"], r["status"], r["error_code"]) for r in rows] == [
        (done, "not_a_serve", "succeeded", ""), (failed, "was_a_serve", "failed", "NOT_A_SERVE")]
    assert rows[0]["note"] == "a smash, from the side"
    assert rows[0]["original_until"] >= now().date().isoformat() and rows[1]["original_until"] == "deleted"
    reports.main(["--days", "0.0001"])
    capsys.readouterr()


@pytest.mark.parametrize("path", ["/auth/email-change", "/auth/email-change/confirm"])
def test_the_new_account_routes_refuse_cross_origin_posts(client, path):
    res = client.post(path, json={}, headers={"Origin": "https://evil.example.com"})
    assert res.status_code == 403
