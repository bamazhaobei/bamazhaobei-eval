# -*- coding: utf-8 -*-
"""
职业本科择校评估 · 腾讯云 SCF 处理器
同时支持：
  POST / → 写入评估记录到飞书多维表格
  GET  / → 读取数据（dashboard 统计 + CSV 导出）
"""

import json
import time
import urllib.request
import urllib.parse

# ── 配置 ─────────────────────────────────────────
APP_ID       = "cli_aaa8d610e8f95bcf"
APP_SECRET   = "U89znBS9nKBeBHvmcH4zIgRRBJiYLHEi"
BASE_TOKEN   = "DVHHbMwz5aS3cds28lbcXucanhg"
TABLE_ID     = "tbl4NUFj7Ztpa8Uu"
ADMIN_PWD    = "bamazhaobei2026"

# ── Token 缓存 ────────────────────────────────────
_token        = None
_token_expire = 0


def get_tenant_token():
    global _token, _token_expire
    now = time.time()
    if _token and now < _token_expire - 300:
        return _token

    body = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    if data.get("code") != 0:
        raise RuntimeError("飞书Token获取失败: " + json.dumps(data, ensure_ascii=False))

    _token = data["tenant_access_token"]
    _token_expire = now + data.get("expire", 7200)
    return _token


# ── 飞书 API 操作 ────────────────────────────────

def feisho_request(method, path, body=None):
    """通用飞书 OpenAPI 请求"""
    token = get_tenant_token()
    url = f"https://open.feishu.cn/open-apis{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def write_record(fields):
    """写入一条记录到飞书表格"""
    result = feisho_request(
        "POST",
        f"/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records",
        {"fields": fields},
    )
    if result.get("code") != 0:
        raise RuntimeError("飞书写入失败: " + json.dumps(result, ensure_ascii=False))
    return result


def read_all_records():
    """分页读取全部记录"""
    all_records = []
    page_token = None

    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token

        qs = urllib.parse.urlencode(params)
        result = feisho_request(
            "GET",
            f"/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records?{qs}",
        )

        if result.get("code") != 0:
            break

        items = result.get("data", {}).get("items", [])
        all_records.extend(items)

        if not result.get("data", {}).get("has_more"):
            break
        page_token = result.get("data", {}).get("page_token")
        if not page_token:
            break

    return all_records


# ── 辅助函数 ─────────────────────────────────────

def build_write_fields(body, ts_now):
    """将 POST body 映射为飞书表格字段"""
    fields = {}

    # 文本字段
    text_map = [
        ("目标省份",    body.get("province", "")),
        ("目标行业",    body.get("industry", "")),
        ("考研意愿",    body.get("exam", "")),
        ("家庭年收入",  body.get("familyIncome", "")),
        ("是否尽早工作", body.get("earlyWork", "")),
        ("兴趣方向",    body.get("interest", "")),
        ("性格类型",    body.get("personality", "")),
        ("学科强项",    body.get("subject", "")),
        ("实践强项",    body.get("practical", "")),
        ("实操意愿",    body.get("practice", "")),
        ("月薪目标",    body.get("income", "")),
        ("完整报告",    body.get("reportText", "")),
        ("时间",        ts_now),
    ]
    for name, val in text_map:
        if val:
            fields[name] = val

    # 数字字段
    fields["分数"] = int(body.get("score", 0))
    fields["匹配学校数"] = int(body.get("totalSchools", 0))

    # Top 1-5 学校和得分
    tp = body.get("tp", [])
    if isinstance(tp, list):
        for i in range(min(len(tp), 5)):
            pair = str(tp[i]).split("|")
            school = pair[0].strip() if len(pair) >= 1 else ""
            score_val = float(pair[1].strip()) if len(pair) >= 2 else 0.0
            fields[f"Top{i + 1}学校"] = school
            fields[f"Top{i + 1}得分"] = score_val

    return fields


def build_dashboard_data(records):
    """将飞书记录转为 dashboard 所需 JSON"""
    filtered = []
    for r in records:
        f = r.get("fields", {})
        # 跳过空记录（分数为 0 或不存在）
        if not f.get("分数"):
            continue
        filtered.append(f)

    # 按时间倒序
    filtered.sort(key=lambda x: x.get("时间", ""), reverse=True)

    # 统计
    score_dist = {}
    province_stats = {}
    industry_stats = {}

    for f in filtered:
        score = f.get("分数", 0)
        bucket = f"{score // 50 * 50}-{score // 50 * 50 + 50}"
        score_dist[bucket] = score_dist.get(bucket, 0) + 1

        prov = f.get("目标省份")
        if prov and prov != "不限":
            province_stats[prov] = province_stats.get(prov, 0) + 1

        ind = f.get("目标行业")
        if ind and ind != "不限":
            industry_stats[ind] = industry_stats.get(ind, 0) + 1

    # 格式化记录（dashboard.html 期望的字段名）
    formatted = []
    for f in filtered[:500]:
        formatted.append({
            "timestamp":   f.get("时间", ""),
            "score":       f.get("分数", 0),
            "province":    f.get("目标省份", ""),
            "industry":    f.get("目标行业", ""),
            "incomeLevel": f.get("月薪目标", ""),
            "practice":    f.get("实操意愿", ""),
            "exam":        f.get("考研意愿", ""),
            "topSchools":  [f.get("Top1学校", "")] if f.get("Top1学校") else [],
            "topScores":   [f.get("Top1得分", 0)] if f.get("Top1得分") else [],
        })

    return {
        "type":              "full",
        "total":             len(filtered),
        "scoreDistribution": score_dist,
        "provinceStats":     province_stats,
        "industryStats":     industry_stats,
        "records":           formatted,
    }


def build_csv_data(records):
    """将飞书记录转为 CSV 字符串"""
    filtered = []
    for r in records:
        f = r.get("fields", {})
        if not f.get("分数"):
            continue
        filtered.append(f)

    filtered.sort(key=lambda x: x.get("时间", ""), reverse=True)

    header = "时间,分数,省份,行业方向,收入目标,实操意愿,考研意愿," \
             "Top1学校,Top1分数,Top2学校,Top2分数,Top3学校,Top3分数"

    rows = []
    for f in filtered[:500]:
        rows.append(
            f'"{f.get("时间","")}",'
            f'"{f.get("分数","")}",'
            f'"{f.get("目标省份","")}",'
            f'"{f.get("目标行业","")}",'
            f'"{f.get("月薪目标","")}",'
            f'"{f.get("实操意愿","")}",'
            f'"{f.get("考研意愿","")}",'
            f'"{f.get("Top1学校","")}",'
            f'"{f.get("Top1得分","")}",'
            f'"{f.get("Top2学校","")}",'
            f'"{f.get("Top2得分","")}",'
            f'"{f.get("Top3学校","")}",'
            f'"{f.get("Top3得分","")}"'
        )

    return "\uFEFF" + header + "\n" + "\n".join(rows)


# ── CORS Headers ─────────────────────────────────

def cors_headers():
    return {
        "Content-Type":                     "application/json; charset=utf-8",
        "Access-Control-Allow-Origin":      "*",
        "Access-Control-Allow-Methods":     "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers":     "Content-Type",
    }


# ── 主入口 ──────────────────────────────────────

def main_handler(event, context):
    method = event.get("httpMethod", "GET")
    headers = cors_headers()

    # OPTIONS 预检
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": headers, "body": ""}

    # ── POST：写入评估记录 ──
    if method == "POST":
        try:
            body_str = event.get("body", "{}")
            if event.get("isBase64Encoded"):
                import base64
                body_str = base64.b64decode(body_str).decode("utf-8")

            body = json.loads(body_str) if body_str else {}

            ts_now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 8 * 3600))
            fields = build_write_fields(body, ts_now)
            write_record(fields)

            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps({"ok": True, "time": ts_now}, ensure_ascii=False),
            }
        except Exception as e:
            return {
                "statusCode": 500,
                "headers": headers,
                "body": json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            }

    # ── GET：读取数据 ──
    # 取 query string（兼容 API 网关 v1 / v2）
    qs = event.get("queryString") or event.get("queryStringParameters") or {}
    if isinstance(qs, str):
        qs = dict(urllib.parse.parse_qsl(qs))
    pwd = qs.get("pwd", "")
    fmt = qs.get("format", "")

    # 密码校验
    if pwd != ADMIN_PWD:
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps({
                "type": "summary",
                "message": "需要密码查看详细数据",
            }, ensure_ascii=False),
        }

    try:
        records = read_all_records()

        # CSV 导出
        if fmt == "csv":
            csv_text = build_csv_data(records)
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "text/csv; charset=utf-8",
                    "Content-Disposition": "attachment; filename=evaluation-data.csv",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": csv_text,
            }

        # JSON 数据
        data = build_dashboard_data(records)
        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps(data, ensure_ascii=False, default=str),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps({
                "type": "error",
                "message": str(e),
            }, ensure_ascii=False),
        }
