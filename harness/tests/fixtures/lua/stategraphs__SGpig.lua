require("stategraphs/commonstates")

local actionhandlers =
{
    ActionHandler(ACTIONS.EAT, "eat"),
    ActionHandler(ACTIONS.CHOP, "chop"),
}

local events =
{
    EventHandler("attacked", function(inst)
        inst.sg:GoToState("hit")
    end),
}

local states =
{
    State{
        name = "idle",
        tags = { "idle", "canrotate" },
        onenter = function(inst)
            inst.AnimState:PlayAnimation("idle_loop", true)
        end,
        events =
        {
            EventHandler("animover", function(inst) inst.sg:GoToState("idle") end),
        },
    },
    State{
        name = "hit",
        tags = { "busy" },
        onenter = function(inst)
            inst:ListenForEvent("onhitother", function() end)
        end,
    },
}

return StateGraph("pig", states, events, "idle", actionhandlers)
