# -*- coding: utf-8 -*-
import json

def main_handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps({"ok": True, "method": event.get("httpMethod", "N/A"), "keys": sorted(event.keys())}, ensure_ascii=False)
    }
