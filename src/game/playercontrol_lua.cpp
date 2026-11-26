// Script functions, file name made up.

#include "engine.h"
#include "luafunc.h"

// Constants the original gets from shared headers. Every file that includes them
// has its own copy, set up by a dynamic initializer at startup.
static const float CONST_150 = 150.0f;
static const float CONST_50 = 50.0f;
static const float CONST_125 = CONST_150 - CONST_50 * 0.5f;
static const EQuat IDENTITY_QUAT(0.0f, 0.0f, 0.0f, 1.0f);
static const Vector3 CONST_VEC3(0.0f, -182.6f, -40.0f);

extern float *g_slideTime;

// control handler 0
class ESlideHandler : public EControlHandler {
public:
    char pad4[0x284 - 4];
    float m_slideEndTime;           // 0x284
    float m_slideStartTime;         // 0x288
};


LUA_FUNCTION(PlayerControl_onSlide)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 1, 1))
        return 0;
    bool sliding = GetNumberArg(L, 1, false) != 0;
    EPhysics *plyr = g_game->GetPlayerControl()->m_player;
    ESlideHandler *pState = (ESlideHandler *)g_game->GetControlHandler(0);
    if (sliding) {
        pState->m_slideEndTime = *g_slideTime + g_game->GetTime();
        pState->m_slideStartTime = g_game->GetTime();
        plyr->m_flags.Set(24);
    } else {
        pState->m_slideEndTime = 0.0f;
        plyr->m_flags.Clear(24);
    }
    return 0;
}

LUA_FUNCTION(SetPlayerMovementScale)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 1, 1))
        return 0;
    float speed = GetNumberArg(L, 1, false);
    g_game->GetPlayerControl()->m_movementScale = speed;
    return 0;
}

LUA_FUNCTION(EnablePlayerJumping)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 1, 1))
        return 0;
    bool enable = GetNumberArg(L, 1, false) != 0;
    g_game->GetPlayerControl()->m_jumpingEnabled = enable;
    return 0;
}
