#!/usr/bin/env python3
"""Собирает поставки WB (FBW) по кабинетам INHOMEKA и Гротек в data.json для дашборда.

Использование:
  python3 fetch_supplies.py --env .env --out data.json [--prev old_data.json]

--prev: прошлый data.json — составы уже принятых поставок берутся из него,
чтобы не запрашивать их заново (экономит лимиты API).
"""
import argparse, json, time, datetime as dt, urllib.request, urllib.error

CABINETS = [("inhomeka", "INHOMEKA", "INHOMEKA_WB_TOKEN"), ("grotek", "Гротек", "GROTEK_WB_TOKEN")]
SUP = "https://supplies-api.wildberries.ru/api/v1"
CONTENT = "https://content-api.wildberries.ru/content/v2/get/cards/list?locale=ru"
STATUS = {1: "Не запланирована", 2: "Запланирована", 3: "Отгрузка разрешена",
          4: "Идёт приёмка", 5: "Принята", 6: "Отгружена на воротах"}
MSK = dt.timezone(dt.timedelta(hours=3))


def req(method, url, token, body=None, tries=8):
    data = json.dumps(body).encode() if body is not None else None
    for i in range(tries):
        r = urllib.request.Request(url, data=data, method=method,
                                   headers={"Authorization": token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                return json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                print(f"  HTTP {e.code} {url[:70]}", flush=True)
                wait = int(e.headers.get("X-Ratelimit-Retry") or 0) or min(5 * (i + 1), 30)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"Не удалось получить {url}")


def list_supplies(token, body):
    out, offset = [], 0
    while True:
        page = req("POST", f"{SUP}/supplies?limit=1000&offset={offset}", token, body) or []
        out += page
        if len(page) < 1000:
            return out
        offset += 1000
        time.sleep(2)


def goods(token, sid):
    out, offset = [], 0
    while True:
        page = req("GET", f"{SUP}/supplies/{sid}/goods?limit=1000&offset={offset}", token) or []
        out += page
        if len(page) < 1000:
            return out
        offset += 1000
        time.sleep(2)


def cards(token):
    """nmID -> (название, фото). Если контент-API недоступен — пустой словарь."""
    res, cursor = {}, {"limit": 100}
    try:
        while True:
            d = req("POST", CONTENT, token, {"settings": {"cursor": cursor, "filter": {"withPhoto": -1}}}, tries=2)
            cs = (d or {}).get("cards") or []
            for c in cs:
                ph = (c.get("photos") or [{}])[0]
                res[c["nmID"]] = (c.get("title") or "", ph.get("c246x328") or ph.get("tm") or ph.get("big") or "")
            pages = getattr(cards, "_p", 0) + 1
            cards._p = pages
            if len(cs) < 100 or pages >= 60:
                cards._p = 0
                return res
            cur = d["cursor"]
            if cursor.get("nmID") == cur.get("nmID"):
                cards._p = 0
                return res
            cursor = {"limit": 100, "updatedAt": cur["updatedAt"], "nmID": cur["nmID"]}
            time.sleep(0.7)
    except Exception:
        return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=".env")
    ap.add_argument("--out", default="data.json")
    ap.add_argument("--prev")
    ap.add_argument("--prev-supplies")
    ap.add_argument("--prev-items")
    ap.add_argument("--date-from", default="2026-10-01", help="плановая дата поставки с")
    ap.add_argument("--names", action="store_true", help="подтягивать названия из карточек (долго)")
    a = ap.parse_args()

    env = {}
    for line in open(a.env, encoding="utf-8"):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

    prev = {}
    if a.prev:
        try:
            for s in json.load(open(a.prev, encoding="utf-8")).get("supplies", []):
                if s.get("statusID") == 5 and s.get("items") is not None:
                    prev[(s["cab"], s["id"])] = s
        except Exception:
            pass
    if a.prev_supplies and a.prev_items:
        # прошлые данные в формате дашборда (supplies.json + items.json)
        try:
            ps = json.load(open(a.prev_supplies, encoding="utf-8"))
            pi = json.load(open(a.prev_items, encoding="utf-8"))
            ps = ps.get("rows", ps) if isinstance(ps, dict) else ps
            pi = pi.get("rows", pi) if isinstance(pi, dict) else pi
            by_sid = {}
            for i in pi:
                by_sid.setdefault(i["sid"], []).append(
                    {"art": i.get("article"), "nm": int(i["nm_id"]) if str(i.get("nm_id") or "").isdigit() else None,
                     "bc": i.get("barcode"), "size": i.get("size"), "color": i.get("color"),
                     "title": i.get("title"), "photo": "", "qty": i.get("qty"), "acc": i.get("accepted")})
            for s in ps:
                if int(s.get("status_id") or 0) != 5 or not s.get("items_loaded"):
                    continue
                sid = int(s["supply_id"])
                prev[(s["cab"], sid)] = {
                    "cab": s["cab"], "id": sid, "preorder": s.get("preorder", False), "statusID": 5,
                    "status": s.get("status"), "date": s.get("date") or None, "created": s.get("created"),
                    "fact": s.get("fact_date") or None, "wh": s.get("warehouse"), "whActual": s.get("warehouse_actual"),
                    "boxType": s.get("box_type"), "qty": s.get("units"), "accepted": s.get("accepted"),
                    "discrepancies": s.get("discrepancies"), "acceptanceCost": s.get("acceptance_cost"),
                    "coef": s.get("coef"), "items": by_sid.get(s["sid"], [])}
        except Exception as e:
            print("Прошлые данные не прочитаны:", e)

    now = dt.datetime.now(MSK)
    frm = a.date_from
    till = (now + dt.timedelta(days=120)).strftime("%Y-%m-%d")
    created_from = (now - dt.timedelta(days=60)).strftime("%Y-%m-%d")

    supplies, errors = [], []
    for cab, name, key in CABINETS:
        token = env.get(key)
        if not token:
            errors.append(f"{name}: нет ключа {key}")
            continue
        try:
            dated = list_supplies(token, {"dates": [{"from": frm, "till": till, "type": "supplyDate"}]})
            time.sleep(2)
            undated = []
        except Exception as e:
            errors.append(f"{name}: {e}")
            continue
        seen, rows = set(), []
        for s in dated + undated:
            sid = s.get("supplyID") or s.get("preorderID")
            if sid in seen:
                continue
            seen.add(sid)
            rows.append(s)
        print(f"{name}: поставок {len(rows)}, загружаю карточки", flush=True)
        names = cards(token) if a.names else {}
        print(f"{name}: карточек {len(names)}", flush=True)
        done = 0
        for s in rows:
            sid, is_pre = (s["supplyID"], False) if s.get("supplyID") else (s["preorderID"], True)
            p = prev.get((cab, sid))
            if p and s.get("statusID") == 5:
                supplies.append(p)
                continue
            q = "?isPreorderID=true" if is_pre else ""
            try:
                det = req("GET", f"{SUP}/supplies/{sid}{q}", token) or {}
                time.sleep(2.1)
                gs = req("GET", f"{SUP}/supplies/{sid}/goods?limit=1000{'&isPreorderID=true' if is_pre else ''}", token) or []
                time.sleep(2.1)
            except Exception as e:
                errors.append(f"{name} {sid}: {e}")
                det, gs = {}, None
            items = None
            if gs is not None:
                items = []
                for g in gs:
                    t, ph = names.get(g.get("nmID"), ("", ""))
                    items.append({"art": g.get("vendorCode") or "", "nm": g.get("nmID"), "bc": g.get("barcode"),
                                  "size": g.get("techSize") if g.get("techSize") not in (None, "0") else "",
                                  "color": g.get("color") or "", "title": t, "photo": ph,
                                  "qty": g.get("quantity") or 0, "acc": g.get("acceptedQuantity")})
            done += 1
            if done % 10 == 0:
                print(f"{name}: {done}/{len(rows)}", flush=True)
            st = s.get("statusID") or det.get("statusID")
            supplies.append({
                "cab": cab, "id": sid, "preorder": is_pre, "statusID": st, "status": STATUS.get(st, str(st)),
                "date": (s.get("supplyDate") or "")[:10] or None, "created": (s.get("createDate") or "")[:10],
                "fact": (s.get("factDate") or "")[:10] or None,
                "wh": det.get("warehouseName") or "", "whActual": det.get("actualWarehouseName") or "",
                "boxType": {0: "Без коробов", 2: "Короба", 5: "Монопаллеты", 6: "Суперсейф"}.get(s.get("boxTypeID"), ""),
                "qty": det.get("quantity"), "accepted": det.get("acceptedQuantity"),
                "discrepancies": det.get("discrepancies"), "acceptanceCost": det.get("acceptanceCost"),
                "coef": det.get("paidAcceptanceCoefficient"), "items": items,
            })

    json.dump({"updated": now.strftime("%Y-%m-%d %H:%M"), "cabinets": {c: n for c, n, _ in CABINETS},
               "supplies": supplies, "errors": errors},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Поставок: {len(supplies)}, ошибок: {len(errors)}")
    for e in errors[:10]:
        print(" -", e)


if __name__ == "__main__":
    main()
