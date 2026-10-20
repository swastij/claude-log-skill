#!/usr/bin/env python3
"""Log a task's learnings to the personal Notion "Engineering learnings" databases.

Usage:
    python3 -I ~/.claude/scripts/notion-log.py entry.json      # upsert
    python3 -I ~/.claude/scripts/notion-log.py --dry-run entry.json

entry.json shape (every key optional except task_id and name; clickup_id / clickup_url
are accepted as aliases):
{
  "task_id": "PROJ-123",                 # any tracker id (ClickUp, Jira, Linear, GitHub); the upsert key
  "name": "Login OTP rate limit",
  "task_url": "https://tracker.example.com/PROJ-123",
  "prs": ["https://github.com/example/api/pull/42"],
  "repo": ["api", "mobile"],
  "area": ["auth"],
  "risk": "high",
  "status": "Done",
  "shipped_on": "2026-10-08",
  "spawned_from": "PROJ-100",
  "surprised_me": "...",
  "how_it_works": "...",
  "would_bite_again": "...",
  "decisions": [
    {"decision": "OTP retry limit 3/hr, 5/day", "why": "...", "alternatives": "...",
     "impact": "...", "kind": "security", "reversible": true}
  ],
  "questions": [
    {"question": "...", "source": "quiz|I asked|should have asked", "my_answer": "",
     "correct_answer": "...", "rating": 3, "category": "security"}
  ]
}
Rows (decisions/questions) are skipped if a row with the same title already exists
for this task, so re-running an edited entry is safe.
"""
import json, os, sys, urllib.request

TOKEN = os.environ.get("NOTION_TOKEN") or open(os.path.expanduser("~/.notion-token")).read().strip()
DB = json.load(open(os.environ.get("NOTION_LEARNINGS", os.path.expanduser("~/.notion-learnings.json"))))
H = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
DRY = "--dry-run" in sys.argv


def call(method, path, body=None):
    is_write = method == "PATCH" or path == "/pages"
    if DRY and is_write:
        print(f"[dry-run] {method} {path}\n{json.dumps(body, indent=2)[:1500]}")
        return {"id": "dry-run"}
    req = urllib.request.Request("https://api.notion.com/v1" + path, method=method,
                                 data=json.dumps(body).encode() if body else None, headers=H)
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} failed: {e.read().decode()}")


# ---- property builders -------------------------------------------------------
def rt(text):
    text = (text or "").strip()
    if not text:
        return {"rich_text": []}
    return {"rich_text": [{"text": {"content": text[i:i + 2000]}} for i in range(0, len(text), 2000)]}


def title(text):
    return {"title": [{"text": {"content": (text or "")[:2000]}}]}


def sel(v):
    return {"select": {"name": v}} if v else None


def multi(vs):
    return {"multi_select": [{"name": v} for v in vs]} if vs else None


def clean(props):
    return {k: v for k, v in props.items() if v is not None}


# ---- lookups -----------------------------------------------------------------
def find_task(task_id):
    res = call("POST", f"/databases/{DB['tasks']}/query", {
        "filter": {"property": "Task ID", "rich_text": {"equals": task_id}}, "page_size": 1})
    return res["results"][0]["id"] if res["results"] else None


def existing_titles(db, title_prop, task_page_id):
    res = call("POST", f"/databases/{db}/query", {
        "filter": {"property": "Task", "relation": {"contains": task_page_id}}, "page_size": 100})
    out = set()
    for r in res["results"]:
        t = r["properties"][title_prop]["title"]
        out.add(t[0]["plain_text"] if t else "")
    return out


# ---- main --------------------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    e = json.load(open(args[0]))
    cid = e.get("task_id") or e.get("clickup_id")
    if not cid:
        sys.exit("entry needs task_id")
    name = e["name"]
    task_url = e.get("task_url") or e.get("clickup_url")

    props = clean({
        "Name": title(name),
        "Task ID": rt(cid),
        "Task URL": {"url": task_url} if task_url else None,
        "PRs": rt("\n".join(e.get("prs", []))) if e.get("prs") else None,
        "Repo": multi(e.get("repo")),
        "Area": multi(e.get("area")),
        "Risk": sel(e.get("risk")),
        "Status": sel(e.get("status")),
        "Shipped on": {"date": {"start": e["shipped_on"]}} if e.get("shipped_on") else None,
        "Surprised me": rt(e["surprised_me"]) if e.get("surprised_me") else None,
        "How it works": rt(e["how_it_works"]) if e.get("how_it_works") else None,
        "Would bite again": rt(e["would_bite_again"]) if e.get("would_bite_again") else None,
    })
    if e.get("spawned_from"):
        parent = find_task(e["spawned_from"])
        if parent:
            props["Spawned from"] = {"relation": [{"id": parent}]}
        else:
            print(f"warning: spawned_from {e['spawned_from']} not found in Notion, skipped")

    page_id = find_task(cid)
    if page_id:
        call("PATCH", f"/pages/{page_id}", {"properties": props})
        print(f"updated task {cid} ({name})")
    else:
        page_id = call("POST", "/pages", {"parent": {"database_id": DB["tasks"]}, "properties": props})["id"]
        print(f"created task {cid} ({name})")

    if page_id == "dry-run":
        have_d = have_q = set()
    else:
        have_d = existing_titles(DB["decisions"], "Decision", page_id)
        have_q = existing_titles(DB["questions"], "Question", page_id)

    n = 0
    for d in e.get("decisions", []):
        if d["decision"] in have_d:
            continue
        call("POST", "/pages", {"parent": {"database_id": DB["decisions"]}, "properties": clean({
            "Decision": title(d["decision"]),
            "Why": rt(d.get("why")),
            "Alternatives rejected": rt(d.get("alternatives")),
            "Impact": rt(d.get("impact")),
            "Kind": sel(d.get("kind")),
            "Reversible": {"checkbox": bool(d.get("reversible", True))},
            "Task": {"relation": [{"id": page_id}]},
        })})
        n += 1
    print(f"added {n} decision(s), skipped {len(e.get('decisions', [])) - n} existing")

    n = 0
    for q in e.get("questions", []):
        if q["question"] in have_q:
            continue
        call("POST", "/pages", {"parent": {"database_id": DB["questions"]}, "properties": clean({
            "Question": title(q["question"]),
            "Source": sel(q.get("source", "quiz")),
            "My answer": rt(q.get("my_answer")),
            "Correct answer": rt(q.get("correct_answer")),
            "Rating": {"number": q["rating"]} if q.get("rating") is not None else None,
            "Category": sel(q.get("category")),
            "Task": {"relation": [{"id": page_id}]},
        })})
        n += 1
    print(f"added {n} question(s), skipped {len(e.get('questions', [])) - n} existing")


if __name__ == "__main__":
    main()
