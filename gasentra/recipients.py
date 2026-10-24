"""Recipient provenance: where did this address come from?"""
import re

from .matching import EMAIL_RE


def parse_recipients(value):
    """Returns (addresses, valid). Anything that is not a clean email address makes it invalid."""
    if value is None:
        return [], False
    parts = [p for p in re.split(r"[,;\s]+", str(value).strip()) if p]
    if not parts:
        return [], False
    addrs, valid = [], True
    for p in parts:
        if EMAIL_RE.fullmatch(p):
            addrs.append(p.lower())
        else:
            valid = False
    return addrs, valid


def user_addresses(user_texts):
    return {a.lower() for a in EMAIL_RE.findall(" ".join(user_texts))}


def classify(addr, cfg, user_addrs):
    """internal | trusted | user | unknown (user = named in the user's own messages)."""
    domain = addr.split("@")[-1].lower()
    for d in cfg.internal_domains:
        if domain == d or domain.endswith("." + d):
            return "internal"
    if addr in cfg.trusted_contacts:
        return "trusted"
    if addr in user_addrs:
        return "user"
    return "unknown"
