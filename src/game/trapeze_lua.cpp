// Script functions, file name made up.

#include <malloc.h>
#include "engine.h"
#include "luafunc.h"

class ETrapezePhysics {
public:
    float GetSwingSpeed();
    void SetSwingSpeed(float speed);

    char pad0[0x1c4];
    float m_maxEnergyPct;           // 0x1c4
};

class ETrapezeEntity {
public:
    ETrapezeEntity(class EDomain *domain, const char *name);
    void *operator new(size_t size) { return _aligned_malloc(size, 16); }
    static EEntity *Create(class EDomain *domain, const char *name) { return (EEntity *)new ETrapezeEntity(domain, name); }
    ETrapezePhysics *GetPhysics() { return m_physics; }
    void Reset();

    char pad0[0x10];
    ETrapezePhysics *m_physics;     // 0x10
    char pad14[0x11c - 0x14];

    static EClassInfo s_class;
};


// Constants the original gets from shared headers. Every file that includes them
// has its own copy, set up by a dynamic initializer at startup.
static const double PI = 3.14159265358979323846;
static const double DEG_TO_RAD = PI / 180.0;
static const double RAD_TO_DEG = 180.0 / PI;
static const float DEG_TO_RAD_F = (float)DEG_TO_RAD;
static const float RAD_TO_DEG_F = (float)RAD_TO_DEG;

EClassInfo ETrapezeEntity::s_class("EntityType_Trapeze", 6, &ETrapezeEntity::Create, &g_meshEntityClass);

LUA_FUNCTION(TrapezeGetSwingSpeed)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 1, 1))
        return 0;
    ETrapezeEntity *trapeze = (ETrapezeEntity *)GetEntityArg(L, 1, false, &ETrapezeEntity::s_class);
    if (!trapeze)
        return 0;
    lua_pushnumber(L, trapeze->GetPhysics()->GetSwingSpeed());
    return 1;
}

LUA_FUNCTION(TrapezeSetSwingSpeed)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 2, 2))
        return 0;
    ETrapezeEntity *trapeze = (ETrapezeEntity *)GetEntityArg(L, 1, false, &ETrapezeEntity::s_class);
    float rate = GetNumberArg(L, 2, false);
    if (!trapeze)
        return 0;
    trapeze->GetPhysics()->SetSwingSpeed(rate);
    return 0;
}

LUA_FUNCTION(TrapezeSetMaxEnergyPct)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 2, 2))
        return 0;
    ETrapezeEntity *trapeze = (ETrapezeEntity *)GetEntityArg(L, 1, false, &ETrapezeEntity::s_class);
    float max = GetNumberArg(L, 2, false);
    if (!trapeze)
        return 0;
    max = Clamp(max, 0.1f, 2.0f);
    trapeze->GetPhysics()->m_maxEnergyPct = max;
    return 0;
}

LUA_FUNCTION(TrapezeReset)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 1, 1))
        return 0;
    ETrapezeEntity *trapeze = (ETrapezeEntity *)GetEntityArg(L, 1, false, &ETrapezeEntity::s_class);
    if (!trapeze)
        return 0;
    trapeze->Reset();
    return 0;
}
