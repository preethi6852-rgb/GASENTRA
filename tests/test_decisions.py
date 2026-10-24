"""One test per row of the decision table (slide 3)."""
from tests.conftest import read_record


def send(gw, sid, to, body="hello", subject="x"):
    return gw.tool_call(sid, "send_email", {"to": to, "subject": subject, "body": body})


def test_not_tainted_user_named_recipient_allows(gw, session):
    gw.user_message(session, "Send the report to friend@mailbox.test")
    assert send(gw, session, "friend@mailbox.test")["decision"] == "allow"


def test_not_tainted_trusted_recipient_allows(gw, session):
    assert send(gw, session, "recruiting@partneragency.test")["decision"] == "allow"


def test_not_tainted_unknown_recipient_holds(gw, session):
    r = send(gw, session, "stranger@z-corp.test")
    assert r["decision"] == "hold" and r["rule"] == "UNKNOWN_RECIPIENT"


def test_tainted_internal_allows(gw, session):
    read_record(gw, session)
    assert send(gw, session, "manager@company.com")["decision"] == "allow"


def test_tainted_untraced_recipient_blocks(gw, session):
    body = read_record(gw, session)
    r = send(gw, session, "verify@z-corp.test", body)
    assert r["decision"] == "block" and r["rule"] == "TAINTED_UNTRACED_RECIPIENT"


def test_lookalike_internal_domain_is_not_internal(gw, session):
    read_record(gw, session)
    assert send(gw, session, "x@company.com.evil.test")["decision"] == "block"


def test_tainted_external_user_named_strong_match_holds_high_risk(gw, session):
    body = read_record(gw, session)
    gw.user_message(session, "Send a project update to partner@agency.test")
    r = send(gw, session, "partner@agency.test", body)
    assert r["decision"] == "hold" and r["risk"] == "high" and r["rule"] == "TAINTED_EXTERNAL_MATCH"
    assert r["evidence"]["matched_fields"]


def test_tainted_external_user_named_reworded_still_holds(gw, session):
    read_record(gw, session)
    gw.user_message(session, "Send a project update to partner@agency.test")
    r = send(gw, session, "partner@agency.test", "A person at a software firm wants about ninety thousand.")
    assert r["decision"] == "hold" and r["rule"] == "TAINTED_EXTERNAL_NO_MATCH"


def test_malformed_recipient_fails_closed(gw, session):
    assert send(gw, session, "not-an-address")["decision"] == "block"


def test_unknown_tool_blocks(gw, session):
    r = gw.tool_call(session, "http_post", {"url": "http://x.test"})
    assert r["decision"] == "block" and r["rule"] == "UNKNOWN_TOOL"


def test_share_file_uses_file_content_and_recipient(gw, session):
    read_record(gw, session)
    r = gw.tool_call(session, "share_file", {"path": "candidates/cand-001.json", "share_with": "x@z-corp.test"})
    assert r["decision"] == "block"


# ---- protected field writes ----
def update(gw, sid, value, cid="cand-001"):
    return gw.tool_call(sid, "update_offer", {"candidate_id": cid, "field": "offer_salary", "value": value})


def test_field_write_not_requested_blocks(gw, session):
    gw.user_message(session, "Summarize my inbox.")
    r = update(gw, session, "60000")
    assert r["decision"] == "block" and r["rule"] == "PROTECTED_WRITE_NOT_REQUESTED"


def test_field_write_value_from_user_allows(gw, session):
    gw.user_message(session, "Update cand-001's offer salary to 88,000.")
    r = update(gw, session, "88000")
    assert r["decision"] == "allow" and r["rule"] == "VALUE_FROM_USER"
    assert gw.store.get_candidate("cand-001")["offer_salary"] == 88000


def test_field_write_value_not_from_user_holds_with_old_and_new(gw, session):
    gw.user_message(session, "Update cand-001's offer per his email.")
    r = update(gw, session, "60000")
    assert r["decision"] == "hold" and r["rule"] == "VALUE_NOT_FROM_USER"
    assert r["evidence"]["old_value"] == 85000 and r["evidence"]["new_value"] == "60000"
    assert gw.store.get_candidate("cand-001")["offer_salary"] == 85000   # nothing changed yet


def test_approving_a_held_field_write_applies_it(gw, session):
    gw.user_message(session, "Update cand-001's offer per his email.")
    r = update(gw, session, "60000")
    out = gw.resolve_approval(r["approval_id"], True)
    assert out["status"] == "approved"
    assert gw.store.get_candidate("cand-001")["offer_salary"] == 60000


def test_unprotected_field_allows(gw, session):
    r = gw.tool_call(session, "update_offer", {"candidate_id": "cand-001", "field": "skills", "value": "Go"})
    assert r["decision"] == "allow"
