// Script functions, file name made up.

#include "engine.h"
#include "luafunc.h"

// Constants the original gets from shared headers. Every file that includes them
// has its own copy, set up by a dynamic initializer at startup.
static const double PI = 3.14159265358979323846;
static const double DEG_TO_RAD = PI / 180.0;
static const double RAD_TO_DEG = 180.0 / PI;
static const float DEG_TO_RAD_F = (float)DEG_TO_RAD;
static const float RAD_TO_DEG_F = (float)RAD_TO_DEG;
static const float EPSILON = 0.00001f;
static const double ONE_OVER_255 = 1.0f / 255.0f;
static const float ONE_OVER_255_EPS = ONE_OVER_255 - EPSILON;
static const float EIGHTH = 0.125f;
static const float SEVEN_EIGHTHS = 1.0f - EIGHTH;
static const float MS_PER_SEC = 1000.0f;
static const float FRAMES_PER_SEC = 60.0f;
static const float MS_PER_FRAME = MS_PER_SEC / FRAMES_PER_SEC;
static const float FRAMES_PER_MS = FRAMES_PER_SEC / MS_PER_SEC;

class EAnimManager {
public:
    void SetCacheSize(unsigned int bytes);
    void PurgeCache(bool all);
    void SqueezeCache(bool all);
};

extern EAnimManager *g_animManager;


LUA_FUNCTION(AnimManager_SqueezeCache)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 0, 1))
        return 0;
    bool all = n >= 1 ? GetNumberArg(L, 1, true) != 0 : false;
    g_animManager->SqueezeCache(all);
    return 0;
}

LUA_FUNCTION(AnimManager_PurgeCache)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 0, 1))
        return 0;
    bool all = n >= 1 ? GetNumberArg(L, 1, true) != 0 : false;
    g_animManager->PurgeCache(all);
    return 0;
}

LUA_FUNCTION(AnimManager_SetCacheSize)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 1, 1))
        return 0;
    unsigned int kb = GetNumberArg(L, 1, false);
    if (kb > 128 && kb < 65536)
        g_animManager->SetCacheSize(kb * 1024);
    return 0;
}
