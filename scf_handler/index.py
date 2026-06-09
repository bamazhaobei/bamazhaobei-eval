# -*- coding: utf-8 -*-
"""
职业本科择校评估 · 腾讯云 SCF 处理器 v3
  POST / → 写入评估记录 → 飞书表格
  POST /?action=download → 上传完整报告附件 + 标记下载
  GET  /?pwd=xxx → Dashboard JSON 数据
  GET  / (无参) → 返回完整 H5 评估页面
"""
import json, time, urllib.request, urllib.parse, uuid, os

# ── 配置 ─────────────────────────────────────────
APP_ID       = "cli_aaa8d610e8f95bcf"
APP_SECRET   = "U89znBS9nKBeBHvmcH4zIgRRBJiYLHEi"
BASE_TOKEN   = "DVHHbMwz5aS3cds28lbcXucanhg"
TABLE_ID     = "tbl4NUFj7Ztpa8Uu"
ADMIN_PWD    = "bamazhaobei2026"

# 需要确保存在的字段 key → (name, type)
REQUIRED_FIELDS = {
    "是否下载": "checkbox",
    "下载时间": "text",
}

# ── Token 缓存 ────────────────────────────────────
_token = None
_token_expire = 0
_fields_checked = False

def get_token():
    global _token, _token_expire
    now = time.time()
    if _token and now < _token_expire - 300:
        return _token
    body = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if data.get("code") != 0:
        raise RuntimeError("Token fail: " + json.dumps(data, ensure_ascii=False))
    _token = data["tenant_access_token"]
    _token_expire = now + data.get("expire", 7200)
    return _token


def feisho_req(method, path, body=None, extra_headers=None):
    """通用飞书 OpenAPI 请求"""
    token = get_token()
    url = "https://open.feishu.cn/open-apis" + path
    h = {"Authorization": "Bearer " + token}
    if extra_headers:
        h.update(extra_headers)
    else:
        h["Content-Type"] = "application/json; charset=utf-8"
    data = json.dumps(body).encode("utf-8") if body and not extra_headers else body
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ── 字段自动创建 ────────────────────────────────

def ensure_fields():
    """检查并自动创建缺失字段"""
    global _fields_checked
    if _fields_checked:
        return
    r = feisho_req("GET", "/bitable/v1/apps/" + BASE_TOKEN + "/tables/" + TABLE_ID + "/fields")
    if r.get("code") != 0:
        return
    existing = {f["name"]: f["type"] for f in r.get("data", {}).get("fields", [])}
    for name, ftype in REQUIRED_FIELDS.items():
        if name not in existing:
            body = {"type": ftype, "name": name}
            if ftype == "checkbox":
                body["defaultValue"] = False
            feisho_req("POST", "/bitable/v1/apps/" + BASE_TOKEN + "/tables/" + TABLE_ID + "/fields", body)
    _fields_checked = True


# ── 附件上传 ────────────────────────────────────

def upload_attachment(file_name, content_bytes):
    """上传文件到飞书，返回 file_token"""
    boundary = "----FormBoundary" + uuid.uuid4().hex[:16]
    body_parts = [
        ("--" + boundary + "\r\n").encode(),
        ('Content-Disposition: form-data; name="file_name"; filename="' + file_name + '"\r\n').encode(),
        ("Content-Type: text/plain\r\n\r\n").encode(),
        content_bytes,
        ("\r\n--" + boundary + "--\r\n").encode(),
    ]
    body = b"".join(body_parts)

    r = feisho_req(
        "POST",
        "/drive/v1/medias/upload_all?file_name=" + urllib.parse.quote(file_name)
        + "&parent_type=bitable_file&parent_node=" + BASE_TOKEN
        + "&size=" + str(len(body)),
        body=body,
        extra_headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
    )
    if r.get("code") != 0:
        raise RuntimeError("Upload fail: " + json.dumps(r, ensure_ascii=False))
    return r.get("data", {}).get("file_token", "")


# ── 记录 CRUD ──────────────────────────────────

def write_record(fields):
    """写入记录，返回 (record_id, 时间)"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 8 * 3600))
    fields["时间"] = ts
    r = feisho_req("POST",
                   "/bitable/v1/apps/" + BASE_TOKEN + "/tables/" + TABLE_ID + "/records",
                   {"fields": fields})
    if r.get("code") != 0:
        raise RuntimeError("Write fail: " + json.dumps(r, ensure_ascii=False))
    rid = r.get("data", {}).get("record", {}).get("record_id", "")
    return rid, ts


def update_record(record_id, fields):
    """更新已有记录的字段"""
    r = feisho_req("PUT",
                   "/bitable/v1/apps/" + BASE_TOKEN + "/tables/" + TABLE_ID + "/records/" + record_id,
                   {"fields": fields})
    if r.get("code") != 0:
        raise RuntimeError("Update fail: " + json.dumps(r, ensure_ascii=False))


def read_all():
    all_recs = []
    page_token = None
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        qs = urllib.parse.urlencode(params)
        r = feisho_req("GET", "/bitable/v1/apps/" + BASE_TOKEN + "/tables/" + TABLE_ID + "/records?" + qs)
        if r.get("code") != 0:
            break
        items = r.get("data", {}).get("items", [])
        all_recs.extend(items)
        if not r.get("data", {}).get("has_more"):
            break
        page_token = r.get("data", {}).get("page_token")
        if not page_token:
            break
    return all_recs


# ── 字段构建 ──────────────────────────────────

def build_fields(body):
    f = {}
    text_map = [
        ("目标省份", body.get("province", "")),
        ("目标行业", body.get("industry", "")),
        ("考研意愿", body.get("exam", "")),
        ("家庭年收入", body.get("familyIncome", "")),
        ("是否尽早工作", body.get("earlyWork", "")),
        ("兴趣方向", body.get("interest", "")),
        ("性格类型", body.get("personality", "")),
        ("学科强项", body.get("subject", "")),
        ("实践强项", body.get("practical", "")),
        ("实操意愿", body.get("practice", "")),
        ("月薪目标", body.get("income", "")),
        ("完整报告", body.get("fullReport", "")),
    ]
    for k, v in text_map:
        if v:
            f[k] = v
    f["分数"] = int(body.get("score", 0))
    f["匹配学校数"] = int(body.get("totalSchools", 0))
    tp = body.get("tp", [])
    if isinstance(tp, list):
        for i in range(min(len(tp), 5)):
            pair = str(tp[i]).split("|")
            sch = pair[0].strip() if len(pair) >= 1 else ""
            sc  = float(pair[1].strip()) if len(pair) >= 2 else 0.0
            f["Top" + str(i + 1) + "学校"] = sch
            f["Top" + str(i + 1) + "得分"] = sc
    return f


# ── Dashboard 数据构建 ──────────────────────────

def build_dashboard(records):
    filtered = [r["fields"] for r in records if r.get("fields", {}).get("分数")]
    filtered.sort(key=lambda x: x.get("时间", ""), reverse=True)
    sd, ps_, ins = {}, {}, {}
    for fld in filtered:
        sc = int(fld.get("分数", 0))
        b = str(sc // 50 * 50) + "-" + str(sc // 50 * 50 + 50)
        sd[b] = sd.get(b, 0) + 1
        if fld.get("目标省份") and fld["目标省份"] != "不限":
            ps_[fld["目标省份"]] = ps_.get(fld["目标省份"], 0) + 1
        if fld.get("目标行业") and fld["目标行业"] != "不限":
            ins[fld["目标行业"]] = ins.get(fld["目标行业"], 0) + 1
    fmt = []
    for fld in filtered[:500]:
        fmt.append({
            "timestamp": fld.get("时间", ""),
            "score": fld.get("分数", 0),
            "province": fld.get("目标省份", ""),
            "industry": fld.get("目标行业", ""),
            "incomeLevel": fld.get("月薪目标", ""),
            "practice": fld.get("实操意愿", ""),
            "exam": fld.get("考研意愿", ""),
            "topSchools": [fld.get("Top1学校", "")] if fld.get("Top1学校") else [],
            "topScores": [fld.get("Top1得分", 0)] if fld.get("Top1得分") else [],
        })
    return {"type": "full", "total": len(filtered),
            "scoreDistribution": sd, "provinceStats": ps_,
            "industryStats": ins, "records": fmt}


def build_csv(records):
    filtered = [r["fields"] for r in records if r.get("fields", {}).get("分数")]
    filtered.sort(key=lambda x: x.get("时间", ""), reverse=True)
    hdr = "时间,分数,省份,行业方向,收入目标,实操意愿,考研意愿,Top1学校,Top1分数"
    rows = []
    for f in filtered[:500]:
        rows.append('"' + str(f.get("时间","")) + '",'
                    '"' + str(f.get("分数","")) + '",'
                    '"' + str(f.get("目标省份","")) + '",'
                    '"' + str(f.get("目标行业","")) + '",'
                    '"' + str(f.get("月薪目标","")) + '",'
                    '"' + str(f.get("实操意愿","")) + '",'
                    '"' + str(f.get("考研意愿","")) + '",'
                    '"' + str(f.get("Top1学校","")) + '",'
                    '"' + str(f.get("Top1得分","")) + '"')
    return "\uFEFF" + hdr + "\n" + "\n".join(rows)


# ── HTML 页面（内嵌，base64 wrapper 绕过 API 网关 Content-Type）──
HTML_WRAPPER_START = '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>职业本科择校评估</title></head><body><script>document.write(decodeURIComponent(escape(atob("'
HTML_WRAPPER_END   = '"))))</script></body></html>'

# ── 主入口 ─────────────────────────────────────

def main_handler(event, context):
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    try:
        # 自动创建缺失字段
        ensure_fields()

        # 兼容 API 网关 v1 / v2
        method = (event.get("httpMethod", "")
                  or event.get("requestContext", {}).get("http", {}).get("method", "")
                  or "GET")

        if method == "OPTIONS":
            return {"statusCode": 200, "headers": headers, "body": ""}

        # 解析 queryString
        qs = (event.get("queryStringParameters", {})
              or event.get("queryString", {}) or {})
        if isinstance(qs, str):
            qs = dict(urllib.parse.parse_qsl(qs))

        # 解析 body
        body_str = event.get("body", "") or ""
        if body_str and event.get("isBase64Encoded"):
            import base64
            body_str = base64.b64decode(body_str).decode("utf-8")
        body = json.loads(body_str) if body_str else {}

        # ── GET：HTML 页面 / JSON 数据 ──
        if method == "GET":
            pwd = qs.get("pwd", "")
            fmt = qs.get("format", "")

            if not pwd:
                # 浏览器访问 → 返回 H5 页面（用 base64 wrapper）
                import base64 as b64
                html_b64 = b64.b64encode(open(os.path.join(os.path.dirname(__file__), "index.html"), "rb").read()).decode()
                return {
                    "statusCode": 200,
                    "isBase64Encoded": False,
                    "headers": {"content-type": "text/html; charset=utf-8"},
                    "body": HTML_WRAPPER_START + html_b64 + HTML_WRAPPER_END
                }
                # fallback if file not found - use the embedded hardcoded version
                # (HTML will be added by build script)

            if pwd != ADMIN_PWD:
                return {"statusCode": 200, "headers": headers,
                        "body": json.dumps({"type": "summary", "message": u"需要密码查看详细数据"}, ensure_ascii=False)}

            records = read_all()
            if fmt == "csv":
                csv_text = build_csv(records)
                return {"statusCode": 200,
                        "headers": {"Content-Type": "text/csv; charset=utf-8",
                                    "Content-Disposition": "attachment; filename=evaluation-data.csv",
                                    "Access-Control-Allow-Origin": "*"},
                        "body": csv_text}
            data = build_dashboard(records)
            return {"statusCode": 200, "headers": headers,
                    "body": json.dumps(data, ensure_ascii=False, default=str)}

        # ── POST ──
        if method == "POST":
            action = qs.get("action", body.get("action", ""))

            # ── action=download：标记下载 + 上传完整报告附件 ──
            if action == "download":
                record_id = body.get("recordId", "")
                full_report = body.get("fullReport", "")
                if not record_id:
                    return {"statusCode": 400, "headers": headers,
                            "body": json.dumps({"ok": False, "error": "missing recordId"}, ensure_ascii=False)}

                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 8 * 3600))

                # 标记是否下载 + 下载时间
                update_record(record_id, {"是否下载": True, "下载时间": ts})

                # 上传完整报告为附件
                if full_report:
                    try:
                        file_token = upload_attachment(
                            "爸妈找北_完整报告_" + ts[:10].replace("-", "") + ".txt",
                            full_report.encode("utf-8")
                        )
                        if file_token:
                            update_record(record_id, {"附件": [{"file_token": file_token}]})
                    except Exception as ue:
                        # 附件上传失败不影响下载标记
                        pass

                return {"statusCode": 200, "headers": headers,
                        "body": json.dumps({"ok": True, "time": ts}, ensure_ascii=False)}

            # ── 普通 POST：写入评估记录 ──
            fields = build_fields(body)
            rid, ts = write_record(fields)
            return {"statusCode": 200, "headers": headers,
                    "body": json.dumps({"ok": True, "recordId": rid, "time": ts}, ensure_ascii=False)}

        return {"statusCode": 405, "headers": headers,
                "body": json.dumps({"error": "Method not allowed"}, ensure_ascii=False)}

    except Exception as e:
        return {"statusCode": 500, "headers": headers,
                "body": json.dumps({"ok": False, "error": str(e), "type": type(e).__name__}, ensure_ascii=False)}
