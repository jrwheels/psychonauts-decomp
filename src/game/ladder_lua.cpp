// Script functions, file name made up.

#include <malloc.h>
#include "engine.h"
#include "luafunc.h"

class EPlayerEntity {
public:
    EPlayerEntity(class EDomain *domain, const char *name);
    void *operator new(size_t size) { return _aligned_malloc(size, 16); }
    static EEntity *Create(class EDomain *domain, const char *name) { return (EEntity *)new EPlayerEntity(domain, name); }
    char pad0[0xa8];
    struct Model *m_model;          // 0xa8
    char padac[0x11c - 0xac];
    float m_lookTargetSearchDist;   // 0x11c
    char pad120[0x190 - 0x120];

    static EClassInfo s_class;
};

// control handler 15
class ELadderControlHandler : public EControlHandler {
public:
    EEntity *GetLadder() { return m_ladder; }

    char pad4[0x230 - 4];
    EEntity *m_ladder;              // 0x230
    char pad234[0x290 - 0x234];
    float m_290;
    float m_294;
};


// Constants the original gets from shared headers. Every file that includes them
// has its own copy, set up by a dynamic initializer at startup.
static const float CONST_150 = 150.0f;
static const float CONST_50 = 50.0f;
static const float CONST_125 = CONST_150 - CONST_50 * 0.5f;

EClassInfo EPlayerEntity::s_class("EPlayerEntity", -2, &EPlayerEntity::Create, &g_meshEntityClass);

LUA_FUNCTION(PlayerGetLadderLSO)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 1, 1))
        return 0;
    EPlayerEntity *pEnt = (EPlayerEntity *)GetEntityArg(L, 1, false, &EPlayerEntity::s_class);
    if (!pEnt)
        return 0;
    ELadderControlHandler *pc = (ELadderControlHandler *)g_game->GetControlHandler(15);
    PushEntity(L, pc->GetLadder(), false);
    float height = pc->m_294;
    float width = pc->m_290;
    lua_pushnumber(L, height);
    lua_pushnumber(L, width);
    return 3;
}

LUA_FUNCTION(PlayerSetLookTargetSearchDist)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 2, 2))
        return 0;
    EPlayerEntity *pEnt = (EPlayerEntity *)GetEntityArg(L, 1, false, &EPlayerEntity::s_class);
    float dist = GetNumberArg(L, 2, false);
    if (!pEnt)
        return 0;
    pEnt->m_lookTargetSearchDist = dist;
    return 0;
}

LUA_FUNCTION_TODO(PlayerGetSuckStatus_LLLL)

LUA_FUNCTION(Cutscene_DisableBackpackBounce)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 1, 1))
        return 0;
    bool off = GetNumberArg(L, 1, false) != 0;
    g_game->GetPlayerControl()->GetBackpack()->m_bounceDisabled = off;
    return 0;
}
