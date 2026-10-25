--[[ long
comment with function inside: function Fake() end ]]
return Class(function(self, inst)
    local _cave = inst:HasTag("cave")
    local s = [==[ a string with ]] end ]==]
    function self:OnUpdate(dt)
        return dt
    end
    function self:GetDebugString()
        return "x"
    end
    inst:ListenForEvent("phasechanged", function() end)
end)
