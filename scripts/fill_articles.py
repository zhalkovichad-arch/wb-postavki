#!/usr/bin/env python3
"""Дозаполняет пустой артикул продавца в составе поставок.

С осени 2026 метод WB /api/v1/supplies/{ID}/goods у части поставок отдаёт
vendorCode пустой строкой (nmID и баркод при этом есть). Артикул берём:
  1) из справочника data/articles.json (nmID -> артикул, копится с каждого запуска);
  2) для оставшихся nmID — из карточек контент-API (постранично, с лимитом времени).

Использование: fill_articles.py data.json data/articles.json [.env]
"""
import json, sys, time, urllib.request

CONTENT = "https://content-api.wildberries.ru/content/v2/get/cards/list?locale=ru"
KEYS = {"inhomeka": "INHOMEKA_WB_TOKEN", "grotek": "GROTEK_WB_TOKEN"}
BUDGET = 240  # секунд на кабинет для поиска по карточкам


def post(token, body, deadline):
    data = json.dumps(body).encode()
    for i in range(4):
        if time.time() > deadline:
            return None
        try:
            r = urllib.request.Request(CONTENT, data=data, method="POST",
                                       headers={"Authorization": token, "Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=30) as resp:
                return json.loads(resp.read())
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def from_cards(token, want):
    """Листает карточки (по 20 — крупные ответы обрываются), пока не найдёт все nmID из want."""
    found, cursor, t0 = {}, {"limit": 20}, time.time()
    while want - found.keys() and time.time() - t0 < BUDGET:
        d = post(token, {"settings": {"cursor": cursor, "filter": {"withPhoto": -1}}}, t0 + BUDGET)
        if not d:
            break
        cs = d.get("cards") or []
        for c in cs:
            if c.get("vendorCode"):
                found[str(c["nmID"])] = c["vendorCode"]
        if len(cs) < 20:
            break
        cur = d["cursor"]
        cursor = {"limit": 20, "updatedAt": cur["updatedAt"], "nmID": cur["nmID"]}
        time.sleep(0.6)
    return found


def main():
    src, cache_path = sys.argv[1], sys.argv[2]
    env = {}
    if len(sys.argv) > 3:
        for line in open(sys.argv[3], encoding="utf-8"):
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    d = json.load(open(src, encoding="utf-8"))
    try:
        cache = json.load(open(cache_path, encoding="utf-8"))
    except Exception:
        cache = {}

    # 1) пополняем справочник тем, что WB отдал
    for s in d["supplies"]:
        for i in s.get("items") or []:
            if i.get("art") and i.get("nm"):
                cache.setdefault(s["cab"], {})[str(i["nm"])] = i["art"]

    # 2) ищем недостающие в карточках
    for cab, key in KEYS.items():
        known = cache.setdefault(cab, {})
        want = {str(i["nm"]) for s in d["supplies"] if s["cab"] == cab
                for i in s.get("items") or [] if not i.get("art") and i.get("nm") and str(i["nm"]) not in known}
        if want and env.get(key):
            got = from_cards(env[key], want)
            known.update(got)
            print(f"{cab}: без артикула {len(want)} nmID, найдено в карточках {len(want & got.keys())}", flush=True)

    # 3) заполняем
    filled = left = 0
    for s in d["supplies"]:
        for i in s.get("items") or []:
            if not i.get("art"):
                a = cache.get(s["cab"], {}).get(str(i.get("nm")))
                if a:
                    i["art"] = a
                    filled += 1
                else:
                    left += 1
    json.dump(d, open(src, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
    print(f"Артикулы: дозаполнено {filled}, осталось пустых {left}")


if __name__ == "__main__":
    main()
