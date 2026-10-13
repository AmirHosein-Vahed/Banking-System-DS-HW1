import json, uuid, datetime

VALID_ACTIONS = {"balance", "deposit", "withdraw"}

def new_req_id():
    return uuid.uuid4().hex[:12]

def validate(raw_obj):
    """Return (ok, req) or (ok=False, error_dict_partial). req has req_id, action, account, amount."""
    if not isinstance(raw_obj, dict):
        return False, ("MALFORMED", "request must be a JSON object")
    action = raw_obj.get("action")
    if action not in VALID_ACTIONS:
        # could be missing/unknown
        if action is None:
            return False, ("MISSING_FIELD", "missing action")
        return False, ("UNSUPPORTED_ACTION", f"unsupported action: {action}")
    account = raw_obj.get("account")
    if not isinstance(account, str) or not account:
        return False, ("MISSING_FIELD", "missing or invalid account")
    # amount
    amount = raw_obj.get("amount")
    if action in ("deposit", "withdraw"):
        if amount is None:
            return False, ("MISSING_FIELD", "missing amount")
        if isinstance(amount, bool) or not isinstance(amount, int):
            # allow numeric strings? spec says invalid - reject non-int
            return False, ("INVALID_AMOUNT", "amount must be an integer")
        if amount <= 0:
            return False, ("INVALID_AMOUNT", "amount must be > 0")
    else:
        amount = 0
    req_id = raw_obj.get("req_id") or new_req_id()
    return True, {"req_id": req_id, "action": action, "account": account, "amount": amount}

def parse_line(line):
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return False, ("MALFORMED", "broken JSON")
    return validate(obj)

def success_resp(req, balance):
    return {"status": "success", "req_id": req["req_id"], "account": req["account"], "balance": balance}

def error_resp(req_id, code, message):
    return {"status": "error", "req_id": req_id, "code": code, "message": message}
