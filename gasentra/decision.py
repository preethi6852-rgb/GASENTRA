"""The decision function. Plain rules, no AI model. Precedence: errors, blocks, holds, allows."""
import re
from dataclasses import dataclass, field

from .matching import numbers_in
from .recipients import classify, parse_recipients

SAFE_ALTERNATIVE = "Send a redacted summary without personal fields, or send it to an internal address."


@dataclass
class Decision:
    action: str            # allow | hold | block
    rule: str
    reason: str
    risk: str = "normal"   # normal | high
    evidence: dict = field(default_factory=dict)


def update_intent(user_texts, policy):
    """Did the user ask for an update at all? (an action word plus an offer/salary/record target)"""
    text = " ".join(user_texts).lower()
    words = any(re.search(r"\b%s\b" % re.escape(w), text) for w in policy["update_intent_words"])
    targets = any(t in text for t in policy["update_intent_targets"])
    return words and targets


def decide_outbound(recipients_raw, tainted, match_report, cfg, user_addrs):
    addrs, valid = parse_recipients(recipients_raw)
    if not valid or not addrs:
        return Decision("block", "MALFORMED_RECIPIENT", "Recipient is missing or not a valid address (fail closed).")
    classes = {a: classify(a, cfg, user_addrs) for a in addrs}
    ev = {"recipients": classes, "tainted": tainted}
    if match_report:
        ev["match"] = match_report
        ev["matched_fields"] = [m["field"] for m in match_report["matched_fields"]]
    all_ok = all(c in ("internal", "trusted", "user") for c in classes.values())
    all_internal = all(c == "internal" for c in classes.values())
    any_unknown = any(c == "unknown" for c in classes.values())
    ev["safer_option"] = SAFE_ALTERNATIVE

    if not tainted:
        if all_ok:
            return Decision("allow", "CLEAN_KNOWN_RECIPIENT", "Recipient traces to the user or a trusted list; no sensitive data seen.", evidence=ev)
        return Decision("hold", "UNKNOWN_RECIPIENT", "Recipient does not trace to the user's words or a trusted list.", evidence=ev)

    if all_internal:
        return Decision("allow", "TAINTED_INTERNAL", "Sensitive data is going to an internal address.", evidence=ev)
    if any_unknown:
        return Decision("block", "TAINTED_UNTRACED_RECIPIENT",
                        "The session holds sensitive data and the recipient appears only in untrusted content.", evidence=ev)
    strength = match_report["strength"] if match_report else "none"
    if strength == "strong":
        return Decision("hold", "TAINTED_EXTERNAL_MATCH",
                        "Sensitive fields are leaving to an external recipient the user named. Human check needed.",
                        risk="high", evidence=ev)
    if strength == "weak":
        return Decision("hold", "TAINTED_EXTERNAL_PARTIAL",
                        "Some sensitive fields appear in a message going outside. Human check needed.",
                        evidence=ev)
    return Decision("hold", "TAINTED_EXTERNAL_NO_MATCH",
                    "Sensitive data was read in this session and the message is going outside. "
                    "No overlap was found, but a reworded message cannot be proven clean.", evidence=ev)


def decide_field_write(args, meta, cfg, user_texts, old_value, untrusted_numbers):
    field_name = str(args.get(meta["field_arg"], ""))
    cid = args.get(meta["id_arg"])
    ev = {"candidate": cid, "field": field_name, "old_value": old_value, "new_value": args.get(meta["value_arg"])}
    if field_name not in meta["protected_fields"]:
        return Decision("allow", "UNPROTECTED_FIELD", "Field is not protected.", evidence=ev)
    if not update_intent(user_texts, cfg.policy):
        return Decision("block", "PROTECTED_WRITE_NOT_REQUESTED",
                        "The user never asked for an update to this field.", evidence=ev)
    new_digits = re.sub(r"[^\d]", "", str(args.get(meta["value_arg"], "")))
    if new_digits and new_digits in numbers_in(" ".join(user_texts)):
        ev["source"] = "user's own words"
        return Decision("allow", "VALUE_FROM_USER", "The new value matches what the user said.", evidence=ev)
    ev["source"] = "untrusted content" if new_digits and new_digits in untrusted_numbers else "derived by the agent"
    return Decision("hold", "VALUE_NOT_FROM_USER",
                    "The user asked for an update but the new value is not in the user's own words.", evidence=ev)
