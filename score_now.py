#!/usr/bin/env python3
"""Block Pulse: capture the 99 pristine cameras and score street-level activity 0-10.
Appends one row per camera to data/activity_log.csv. Designed to run hourly."""
import json, base64, subprocess, urllib.request, concurrent.futures as cf, time, csv, os
from datetime import datetime, timezone

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

PROMPT = """Rate the street-level human activity in this NYC street camera frame for an "how alive is this block" index.
Respond ONLY with compact JSON, no prose:
{"activity":0-10,"peds":<approx pedestrians visible>,"vehicles":<approx moving/parked vehicles>,"lit":"day|dusk|night","note":"<=6 words"}
activity scale: 0=empty/dead, 3=a few people, 5=steady foot traffic, 8=busy/crowded, 10=packed.
Count people on sidewalks/crosswalks. Ignore vehicles for the activity score itself."""

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
    ts=datetime.now(timezone.utc).astimezone().isoformat(timespec="minutes")
    rows=[]
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        rows=list(ex.map(score,CAMS))
    new=not os.path.exists(LOG)
    with open(LOG,"a",newline="") as f:
        w=csv.writer(f)
        if new: w.writerow(["ts","id","name","area","lat","lon","activity","peds","vehicles","lit","note"])
        for r in rows:
            w.writerow([ts,r["id"],r["name"],r["area"],r["lat"],r["lon"],
                        r.get("activity",""),r.get("peds",""),r.get("vehicles",""),r.get("lit",""),r.get("note","")])
    scored=[r for r in rows if str(r.get("activity","")).strip()!=""]

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
