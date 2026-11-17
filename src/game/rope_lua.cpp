// Script functions, file name made up.

#include <malloc.h>
#include "engine.h"
#include "luafunc.h"

class ERopeEntity {
public:
    ERopeEntity(class EDomain *domain, const char *name);
    void *operator new(size_t size) { return _aligned_malloc(size, 16); }
    static EEntity *Create(class EDomain *domain, const char *name) { return (EEntity *)new ERopeEntity(domain, name); }
    void SetPoint(Vector3 *dst, Vector3 *src);

    char pad0[0x13c];
    Vector3 m_end;                  // 0x13c
    Vector3 m_start;                // 0x148
    float m_k;                      // 0x154
    float m_m;                      // 0x158
    float m_damp;                   // 0x15c

    static EClassInfo s_class;
};


// Constants the original gets from shared headers. Every file that includes them
// has its own copy, set up by a dynamic initializer at startup.
static const double PI = 3.14159265358979323846;
static const double DEG_TO_RAD = PI / 180.0;
static const double RAD_TO_DEG = 180.0 / PI;
static const float DEG_TO_RAD_F = (float)DEG_TO_RAD;
static const float RAD_TO_DEG_F = (float)RAD_TO_DEG;
static const double PI2 = 3.14159265358979323846;
static const double DEG_TO_RAD2 = PI2 / 180.0;

EClassInfo ERopeEntity::s_class("ERopeEntity", -2, &ERopeEntity::Create, &g_meshEntityClass);

LUA_FUNCTION(RopeSetStart)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 4, 4))
        return 0;
    ERopeEntity *rope = (ERopeEntity *)GetEntityArg(L, 1, false, &ERopeEntity::s_class);
    Vector3 vPos(GetNumberArg(L, 2, false), GetNumberArg(L, 3, false), GetNumberArg(L, 4, false));
    if (rope)
        rope->SetPoint(&vPos, &rope->m_start);
    return 0;
}

LUA_FUNCTION(RopeSetEnd)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 4, 4))
        return 0;
    ERopeEntity *rope = (ERopeEntity *)GetEntityArg(L, 1, false, &ERopeEntity::s_class);
    Vector3 endPos(GetNumberArg(L, 2, false), GetNumberArg(L, 3, false), GetNumberArg(L, 4, false));
    if (rope)
        rope->SetPoint(&rope->m_end, &endPos);
    return 0;
}

LUA_FUNCTION(RopeSetK)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 2, 2))
        return 0;
    ERopeEntity *rope = (ERopeEntity *)GetEntityArg(L, 1, false, &ERopeEntity::s_class);
    float k = GetNumberArg(L, 2, false);
    if (rope)
        rope->m_k = k;
    return 0;
}

LUA_FUNCTION(RopeSetM)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 2, 2))
        return 0;
    ERopeEntity *rope = (ERopeEntity *)GetEntityArg(L, 1, false, &ERopeEntity::s_class);
    float m = GetNumberArg(L, 2, false);
    if (rope)
        rope->m_m = m;
    return 0;
}

LUA_FUNCTION(RopeSetDamp)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 2, 2))
        return 0;
    ERopeEntity *rope = (ERopeEntity *)GetEntityArg(L, 1, false, &ERopeEntity::s_class);
    float damp = GetNumberArg(L, 2, false);
    if (rope)
        rope->m_damp = damp;
    return 0;
}
