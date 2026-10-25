local function onmax(self, max)
    self.inst.replica.health:SetMax(max)
end

local Health = Class(function(self, inst)
    self.inst = inst
    self.maxhealth = 100
    self.currenthealth = 100
    inst:AddTag("health")
end,
nil,
{
    maxhealth = onmax,
})

function Health:GetPercent()
    return self.currenthealth / self.maxhealth
end

function Health:DoDelta(amount, overtime, cause)
    local old = self.currenthealth
    self.currenthealth = math.clamp(old + amount, 0, self.maxhealth)
    self.inst:PushEvent("healthdelta", { oldpercent = old / self.maxhealth, newpercent = self:GetPercent() })
    return amount
end

function Health.Static(a, b)
    return a + b
end

return Health
