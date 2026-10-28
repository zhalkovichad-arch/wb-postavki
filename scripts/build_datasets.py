#!/usr/bin/env python3
"""data.json (из fetch_supplies.py) -> supplies.json и items.json для дашборда."""
import json, sys

src = sys.argv[1] if len(sys.argv) > 1 else "data.json"
d = json.load(open(src, encoding="utf-8"))
names = d.get("cabinets", {})
sup, items = [], []
for s in d["supplies"]:
    sid = f"{s['cab']}:{s['id']}"
    its = s.get("items") or []
    units = sum(i.get("qty") or 0 for i in its)
    acc = sum(i.get("acc") or 0 for i in its) if its else None
    sup.append({
        "sid": sid, "cab": s["cab"], "cabinet": names.get(s["cab"], s["cab"]),
        "supply_id": str(s["id"]), "preorder": bool(s.get("preorder")),
        "status": s["status"], "status_id": s["statusID"],
        "date": s.get("date") or "", "fact_date": s.get("fact") or "", "created": s.get("created") or "",
        "warehouse": s.get("wh") or "", "warehouse_actual": s.get("whActual") or "",
        "box_type": s.get("boxType") or "",
        "units": s.get("qty") if s.get("qty") is not None else units,
        "accepted": s.get("accepted") if s.get("accepted") is not None else acc,
        "discrepancies": s.get("discrepancies") or 0,
        "acceptance_cost": s.get("acceptanceCost") if (s.get("acceptanceCost") or 0) >= 0 else None, "coef": s.get("coef"),
        "skus": len(its), "items_loaded": s.get("items") is not None,
        "loaded_at": d["updated"],
    })
    for i in its:
        items.append({
            "key": f"{sid}|{i.get('bc') or i.get('art')}|{i.get('size') or ''}",
            "sid": sid, "article": i.get("art") or "", "title": i.get("title") or "",
            "nm_id": str(i.get("nm") or ""), "barcode": i.get("bc") or "",
            "size": i.get("size") or "", "color": i.get("color") or "",
            "qty": i.get("qty") or 0, "accepted": i.get("acc"),
        })
sup.sort(key=lambda r: (r["date"] or "9999", r["cab"], r["supply_id"]))
# ключ строки состава должен быть уникальным
seen = {}
for r in items:
    k = r["key"]
    seen[k] = seen.get(k, 0) + 1
    if seen[k] > 1:
        r["key"] = f"{k}#{seen[k]}"
json.dump({"updated": d["updated"], "rows": sup}, open("supplies.json", "w", encoding="utf-8"), ensure_ascii=False)
json.dump({"updated": d["updated"], "rows": items}, open("items.json", "w", encoding="utf-8"), ensure_ascii=False)
print(len(sup), "поставок,", len(items), "строк состава; ошибки:", d.get("errors"))
