import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from server import merge

def ex(id, name, hist=(), removed=(), updated=0, deleted=False):
    return {"id":id,"name":name,"history":list(hist),"removed":list(removed),
            "updated":updated,"deleted":deleted}
def get(s, id): return next(e for e in s["exercises"] if e["id"]==id)

A="2026-08-01T10:00:00.000Z"; B="2026-08-10T10:00:00.000Z"; C="2026-08-20T10:00:00.000Z"
fails=[]
def check(label, cond):
    print(("  ok  " if cond else "  FAIL")+"  "+label)
    if not cond: fails.append(label)

print("1. stale device cannot erase newer history")
server = {"version":2,"exercises":[ex("x","Squat",[A,B,C])]}
stale  = {"version":2,"exercises":[ex("x","Squat",[A])]}          # phone from a week ago
check("all three timestamps survive", get(merge(server,stale),"x")["history"]==[A,B,C])

print("2. offline logging merges upward")
server = {"version":2,"exercises":[ex("x","Squat",[A])]}
phone  = {"version":2,"exercises":[ex("x","Squat",[A,B,C])]}
check("phone's new entries land", get(merge(server,phone),"x")["history"]==[A,B,C])

print("3. undo is not resurrected")
server = {"version":2,"exercises":[ex("x","Squat",[A,B])]}
undone = {"version":2,"exercises":[ex("x","Squat",[A],removed=[B])]}
check("B stays gone", get(merge(server,undone),"x")["history"]==[A])
check("tombstone persisted", get(merge(server,undone),"x")["removed"]==[B])

print("4. undo survives a later push from the OTHER device that still has B")
merged = merge(server, undone)
other  = {"version":2,"exercises":[ex("x","Squat",[A,B])]}         # laptop never saw the undo
check("B still gone after other device syncs", get(merge(merged,other),"x")["history"]==[A])

print("5. rename last-write-wins")
server = {"version":2,"exercises":[ex("x","Squat",[A],updated=100)]}
newer  = {"version":2,"exercises":[ex("x","Back squat",[A],updated=200)]}
older  = {"version":2,"exercises":[ex("x","Old name",[A],updated=50)]}
check("newer rename wins", get(merge(server,newer),"x")["name"]=="Back squat")
check("older rename loses", get(merge(server,older),"x")["name"]=="Squat")

print("6. delete is a tombstone, not a resurrection loop")
server = {"version":2,"exercises":[ex("x","Squat",[A],updated=100)]}
deld   = {"version":2,"exercises":[ex("x","Squat",[A],updated=200,deleted=True)]}
m = merge(server,deld)
check("marked deleted", get(m,"x")["deleted"] is True)
check("stays deleted when stale device re-pushes", get(merge(m,server),"x")["deleted"] is True)

print("7. new exercise from either side is added")
server = {"version":2,"exercises":[ex("x","Squat")]}
addition = {"version":2,"exercises":[ex("y","Dips")]}
check("union of ids", sorted(e["id"] for e in merge(server,addition)["exercises"])==["x","y"])

print("8. garbage input is rejected, not stored")
server = {"version":2,"exercises":[ex("x","Squat",[A])]}
junk = {"version":2,"exercises":[{"id":"x","name":"S","history":["not-a-date",A,None,123]},
                                 {"no_id":True}, "string", None]}
m = merge(server,junk)
check("bad stamps dropped, good kept", get(m,"x")["history"]==[A])
check("malformed entries ignored", len(m["exercises"])==1)

print("9. idempotent")
server = {"version":2,"exercises":[ex("x","Squat",[A,B],removed=[C],updated=5)]}
check("merge(s,s) == s", merge(server,server)["exercises"]==merge(merge(server,server),server)["exercises"])

print("10. name length / count caps")
m = merge({"version":2,"exercises":[]}, {"version":2,"exercises":[ex("x","N"*500)]})
check("name truncated to 100", len(get(m,"x")["name"])==100)

print()
print("FAILED: "+", ".join(fails) if fails else "all merge tests passed")
sys.exit(1 if fails else 0)
