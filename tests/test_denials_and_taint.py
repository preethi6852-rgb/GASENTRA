from tests.conftest import read_record


def bad_send(gw, sid):
    return gw.tool_call(sid, "send_email", {"to": "x@z-corp.test", "subject": "s", "body": "b"})


def test_taint_turns_on_after_sensitive_read_and_stays(gw, session):
    assert gw.store.get_session(session)["tainted"] is False
    gw.tool_call(session, "read_file", {"path": "public/job_post.txt"})
    assert gw.store.get_session(session)["tainted"] is False      # public data does not taint
    read_record(gw, session)
    assert gw.store.get_session(session)["tainted"] is True
    gw.tool_call(session, "read_inbox")
    assert gw.store.get_session(session)["tainted"] is True       # stays for the whole conversation


def test_write_propagation_label_survives_a_context_reset(gw):
    s1 = gw.start_session()["id"]
    read_record(gw, s1, "cand-002")
    gw.tool_call(s1, "write_note", {"path": "notes/a.txt", "content": "Summary of the candidate."})
    assert gw.store.get_resource("notes/a.txt")["label"] == "personal"
    s2 = gw.start_session()["id"]                                   # context reset = new session
    assert gw.store.get_session(s2)["tainted"] is False
    gw.tool_call(s2, "read_file", {"path": "notes/a.txt"})
    assert gw.store.get_session(s2)["tainted"] is True


def test_untainted_note_stays_internal(gw, session):
    gw.tool_call(session, "write_note", {"path": "notes/b.txt", "content": "Interviews on Friday."})
    assert gw.store.get_resource("notes/b.txt")["label"] == "internal"


def test_session_freezes_after_repeated_denials(gw, session):
    read_record(gw, session)
    results = [bad_send(gw, session) for _ in range(3)]
    assert [r["decision"] for r in results] == ["block"] * 3
    assert results[-1]["frozen"] is True
    assert gw.store.get_session(session)["frozen"] is True
    assert gw.tool_call(session, "read_inbox")["decision"] == "frozen"        # everything is rejected now
    assert bad_send(gw, session)["agent_message"] == "This session has been suspended."


def test_only_a_human_unfreezes(gw, session):
    read_record(gw, session)
    for _ in range(3):
        bad_send(gw, session)
    s = gw.unfreeze(session)
    assert s["frozen"] is False and s["denial_count"] == 0
    assert gw.tool_call(session, "read_inbox")["decision"] == "allow"


def test_rejected_approvals_count_as_denials(gw, session):
    read_record(gw, session)
    gw.user_message(session, "Send an update to partner@agency.test")
    for _ in range(3):
        r = gw.tool_call(session, "send_email", {"to": "partner@agency.test", "subject": "s", "body": "x"})
        gw.resolve_approval(r["approval_id"], False)
    assert gw.store.get_session(session)["frozen"] is True


def test_agent_never_sees_the_reason(gw, session):
    read_record(gw, session)
    r = bad_send(gw, session)
    assert r["agent_message"] == "This action is not permitted."
    assert "recipient" not in r["agent_message"].lower()


def test_every_decision_is_in_the_audit_log(gw, session):
    read_record(gw, session)
    bad_send(gw, session)
    rules = [e["rule"] for e in gw.store.list_audit(session)]
    assert "TAINTED_UNTRACED_RECIPIENT" in rules


def test_approving_cannot_run_in_a_frozen_session(gw, session):
    read_record(gw, session)
    gw.user_message(session, "Send an update to partner@agency.test")
    held = gw.tool_call(session, "send_email", {"to": "partner@agency.test", "subject": "s", "body": "x"})
    for _ in range(3):
        bad_send(gw, session)
    out = gw.resolve_approval(held["approval_id"], True)
    assert out["status"] == "rejected"
