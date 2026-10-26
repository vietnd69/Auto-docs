dofile("../../source-audit/class.lua")
local Counter = dofile("source/components/counter.lua")
local c = Counter({})
assert(c:GetCount("a") == 0 and c:OnSave() == nil)
c:Set("a", 2); c:Decrement("a", 2)
assert(c:GetCount("a") == 0 and c.counters.a == nil)
c:Set("private", 3); c:DoNotSave("private")
assert(c:OnSave().counters.private == nil)
c:Set("negative", -2); c:IncrementToZero("negative", 5)
assert(c:GetCount("negative") == 0)
print("PASS counter: zero/nil, bounded delta and save filtering")

local Saved = dofile("source/components/savedrotation.lua")
local rotation, loaded, delayed = 0, nil, nil
local entity = { Transform = {
 GetRotation = function() return rotation end,
 LoadRotation = function(self, angle) loaded = angle end,
 SetRotation = function(self, angle) rotation = angle end,
}, DoTaskInTime = function(self, delay, fn) assert(delay == 0); delayed = fn end }
local s = Saved(entity)
assert(s:OnSave() == nil and s.dodelayedpostpassapply == nil)
rotation = 40; assert(s:OnSave().rotation == 40)
s:LoadPostPass({}, {}); assert(loaded == 0 and delayed == nil)
s.dodelayedpostpassapply = true; s:LoadPostPass({}, {rotation = 90})
assert(loaded == 90 and rotation == 40 and delayed ~= nil)
delayed(entity); assert(rotation == 90)
print("PASS savedrotation: absent default, Transform and delayed postpass")

GetTime = function() return 0 end
local tasks, events = {}, {}
local inst = {
 DoTaskInTime = function(self, delay, fn, ...)
  local task = {fn=fn, args={...}, cancelled=false}
  task.Cancel = function(t) t.cancelled=true end
  table.insert(tasks,task); return task
 end,
 PushEvent = function(self, name, data) table.insert(events,{name=name,data=data}) end,
}
local Timer = dofile("source/components/timer.lua")
local t = Timer(inst)
t:StartTimer("a", 10); t:StartTimer("a", 20)
assert(#tasks == 1 and t:GetTimeLeft("a") == 10)
t:PauseTimer("a"); assert(t:IsPaused("a") and tasks[1].cancelled)
t:ResumeTimer("a"); assert(not t:IsPaused("a") and #tasks == 2)
t:StopTimer("a"); assert(not t:TimerExists("a") and #events == 0)
t:StartTimer("done", 1)
local task = tasks[#tasks]; task.fn(inst, unpack(task.args))
assert(not t:TimerExists("done") and #events == 1)
assert(events[1].name == "timerdone" and events[1].data.name == "done")
t:StartTimer("cleanup", 2); t:OnRemoveFromEntity(); assert(tasks[#tasks].cancelled)
print("PASS timer: duplicate start, pause/resume, stop vs completion, cleanup")
