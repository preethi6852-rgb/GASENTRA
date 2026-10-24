"""Simulated tools running on synthetic data. Nothing here touches the network."""
import json
import re

from .matching import fingerprint


def _cast(value):
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else str(value)


def run_tool(store, cfg, sid, tool, args, via_approval=False):
    """Runs one tool and returns {'text', 'resource', 'label'}. The label comes from the label map."""
    session = store.get_session(sid)
    if tool == "read_inbox":
        mails = store.emails_for(session["scenario"])
        text = "\n\n".join("From: %s\nSubject: %s\n\n%s" % (m["sender"], m["subject"], m["body"]) for m in mails)
        return {"text": text or "Inbox is empty.", "resource": "inbox/", "label": cfg.label_for_path("inbox/")}

    if tool == "read_file":
        path = str(args.get("path", "")).strip()
        if path.startswith("candidates/"):
            cid = path.split("/", 1)[1].replace(".json", "")
            cand = store.get_candidate(cid)
            if not cand:
                return {"text": "File not found: " + path, "resource": path, "label": "public"}
            return {"text": json.dumps(cand, indent=2), "resource": path, "label": cfg.label_for_path(path)}
        res = store.get_resource(path)
        if not res:
            return {"text": "File not found: " + path, "resource": path, "label": "public"}
        return {"text": res["content"], "resource": path, "label": res["label"]}

    if tool == "write_note":
        path = str(args.get("path", "notes/untitled.txt")).lstrip("/")
        if not path.startswith("notes/"):
            path = "notes/" + path
        content = str(args.get("content", ""))
        label = cfg.label_for_path(path)
        if session["tainted"]:
            # write-propagation: a note written while tainted keeps the highest sensitive label seen
            seen = [o["label"] for o in store.outputs(sid) if o["label"] in cfg.taint_labels]
            label = cfg.highest(seen) if seen else label
        store.put_resource(path, label, content, sid)
        return {"text": "Note saved to " + path, "resource": path, "label": "internal"}

    if tool == "send_email":
        store.add_sent(sid, tool, str(args.get("to", "")), str(args.get("subject", "")),
                       str(args.get("body", "")), via_approval)
        return {"text": "Email sent to %s" % args.get("to"), "resource": "outbox/", "label": "internal"}

    if tool == "share_file":
        path = str(args.get("path", ""))
        res = store.get_resource(path)
        content = res["content"] if res else ""
        if not res and path.startswith("candidates/"):
            cand = store.get_candidate(path.split("/", 1)[1].replace(".json", ""))
            content = json.dumps(cand, indent=2) if cand else ""
        store.add_sent(sid, tool, str(args.get("share_with", "")), path, content, via_approval)
        return {"text": "Shared %s with %s" % (path, args.get("share_with")), "resource": "outbox/", "label": "internal"}

    if tool == "update_offer":
        cid, field = str(args.get("candidate_id", "")), str(args.get("field", ""))
        cand = store.get_candidate(cid)
        if not cand:
            return {"text": "Candidate not found: " + cid, "resource": "candidates/", "label": "internal"}
        old = cand.get(field)
        new = _cast(args.get("value"))
        store.update_candidate(cid, field, new)
        return {"text": json.dumps({"candidate": cid, "field": field, "before": old, "after": new}),
                "resource": "candidates/" + cid, "label": "internal"}

    return {"text": "Unknown tool: " + tool, "resource": "", "label": "internal"}


def execute_and_record(store, cfg, sid, tool, args, via_approval=False):
    """Runs the tool, stores the labelled result in the ledger, and sets taint on sensitive reads."""
    result = run_tool(store, cfg, sid, tool, args, via_approval)
    store.add_output(sid, tool, result["resource"], result["label"], result["text"], fingerprint(result["text"]))
    if result["label"] in cfg.taint_labels:
        store.set_tainted(sid)
    return result
