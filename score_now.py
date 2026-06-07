#!/usr/bin/env python3
"""Block Pulse: capture the 99 pristine cameras and score street-level activity 0-10.
Appends one row per camera to data/activity_log.csv. Designed to run hourly."""
import json, base64, subprocess, urllib.request, concurrent.futures as cf, time, csv, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo
NYC = ZoneInfo("America/New_York")

HERE = os.path.dirname(os.path.abspath(__file__))
def _get_key():
    k = os.environ.get("ANTHROPIC_API_KEY")          # GitHub Actions / any env
    if k: return k.strip()
    return subprocess.check_output(                  # local macOS keychain
        ["security","find-generic-password","-s","ANTHROPIC_API_KEY","-w"]).decode().strip()
KEY = _get_key()
MODEL = "claude-haiku-4-5-20251001"
CAMS = json.load(open(os.path.join(HERE,"data","pristine.json")))
LOG  = os.path.join(HERE,"data","activity_log.csv")

PROMPT = """Estimate FOOT TRAFFIC in this NYC street camera frame: people on foot only — pedestrians on
sidewalks, in crosswalks, or waiting. This is a pedestrian index.

CRITICAL: Ignore ALL vehicles. Cars, taxis, buses, trucks, vans and traffic do NOT count toward the
score. A street jammed bumper-to-bumper with cars but empty of people scores 0-1. Do not let traffic,
road width, or how "busy" the scene looks influence the number — count human beings on foot.

Respond ONLY with compact JSON, no prose:
{"activity":0-10,"peds":<approx number of people on foot visible>,"vehicles":<approx vehicles, reference only>,"lit":"day|dusk|night","note":"<=6 words"}

Score strictly by how many people are on foot:
0 = nobody on foot
1-2 = 1-3 people
3-4 = a handful (about 4-10)
5-6 = steady pedestrian flow (about 10-25)
7-8 = busy, crowded sidewalks (about 25-60)
9-10 = packed with people (60+)"""

def fetch(cam):
    url=f"https://webcams.nyctmc.org/api/cameras/{cam['id']}/image"
    for _ in range(3):
        try:
            raw=urllib.request.urlopen(url,timeout=20).read()
            if len(raw)>1500: return base64.b64encode(raw).decode()
        except Exception: time.sleep(1)
    return None

def score(cam):
    b64=fetch(cam)
    base={"id":cam["id"],"name":cam["name"],"area":cam["area"],"lat":cam["lat"],"lon":cam["lon"]}
    if not b64: return {**base,"activity":"","peds":"","vehicles":"","lit":"","note":"no image"}
    body={"model":MODEL,"max_tokens":120,"messages":[{"role":"user","content":[
        {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}},
        {"type":"text","text":PROMPT}]}]}
    req=urllib.request.Request("https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"x-api-key":KEY,"anthropic-version":"2023-06-01","content-type":"application/json"})
    for _ in range(3):
        try:
            resp=json.loads(urllib.request.urlopen(req,timeout=60).read())
            t=resp["content"][0]["text"]; t=t[t.find("{"):t.rfind("}")+1]
            g=json.loads(t); return {**base,**g}
        except Exception: time.sleep(2)
    return {**base,"activity":"","peds":"","vehicles":"","lit":"","note":"score_failed"}

def main():
    ts=datetime.now(NYC).isoformat(timespec="minutes")   # always NYC local time, even on UTC CI runners
    rows=[]
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        rows=list(ex.map(score,CAMS))
    scored=[r for r in rows if str(r.get("activity","")).strip()!=""]

    # FAIL LOUDLY: if nothing scored, do NOT write empty data over the good data — exit non-zero
    # so the GitHub Action goes red and emails instead of showing a misleading green check.
    if not scored:
        sys.stderr.write(f"{ts}  CAPTURE FAILED: scored 0/{len(rows)} cameras. "
                         f"Likely out of Anthropic API credits, or the camera feed is down. "
                         f"Not writing empty data.\n")
        sys.exit(1)
    if len(scored) < len(rows)*0.5:   # degraded but not dead — warn, keep going
        sys.stderr.write(f"{ts}  WARNING: only scored {len(scored)}/{len(rows)} cameras (degraded).\n")

    new=not os.path.exists(LOG)
    with open(LOG,"a",newline="") as f:
        w=csv.writer(f)
        if new: w.writerow(["ts","id","name","area","lat","lon","activity","peds","vehicles","lit","note"])
        for r in rows:
            w.writerow([ts,r["id"],r["name"],r["area"],r["lat"],r["lon"],
                        r.get("activity",""),r.get("peds",""),r.get("vehicles",""),r.get("lit",""),r.get("note","")])

    # latest.json: most-recent read per camera, for the map dots + leaderboard
    latest={"generated":ts,"scores":{}}
    for r in scored:
        latest["scores"][r["id"]]={"activity":int(r["activity"]),
            "peds":r.get("peds",""),"lit":r.get("lit","")}
    json.dump(latest, open(os.path.join(HERE,"data","latest.json"),"w"))

    # timeline.json: append this capture's citywide mean, for the rhythm chart
    tl_path=os.path.join(HERE,"data","timeline.json")
    tl=json.load(open(tl_path)) if os.path.exists(tl_path) else []
    if scored:
        vals=[int(r["activity"]) for r in scored]
        tl=[p for p in tl if p["ts"]!=ts]  # idempotent if re-run same minute
        tl.append({"ts":ts,"mean":round(sum(vals)/len(vals),2),"n":len(vals)})
        tl.sort(key=lambda p:p["ts"])
        json.dump(tl, open(tl_path,"w"))

    print(f"{ts}  scored {len(scored)}/{len(rows)} cameras -> {LOG} (+latest.json, timeline.json)")

if __name__=="__main__":
    main()
