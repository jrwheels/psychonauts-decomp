// Script functions, file name made up.

#include "engine.h"
#include "luafunc.h"

#include "classes.h"

static const Color s_lineColor(0.7f, 0.7f, 0.3f, 1.0f);

static const double PI = 3.14159265358979323846;
const double DEG_TO_RAD = PI / 180.0;
const double RAD_TO_DEG = 180.0 / PI;
const float RAD_TO_DEG_F = (float)RAD_TO_DEG;

static const Color s_normalColor(0.4f, 0.4f, 0.6f, 1.0f);

// the points the scripts collect between StartLineCollision and EndLineCollision
TArray<Vector3> g_linePoints(0, false);
TArray<Vector3> g_lineNormals(0, false);


LUA_FUNCTION(StartLineCollision)
{
    g_linePoints.Clear();
    g_lineNormals.Clear();
    return 0;
}

LUA_FUNCTION_TODO(AddLineCollision)

LUA_FUNCTION(EndLineCollision)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 2, 2))
        return 0;
    EEntity *ent = GetEntityArg(L, 1, false, 0);
    if (!ent)
        return 0;
    float fRadius = GetNumberArg(L, 2, false);
    ent->m_splineCollision = new ESplineCollision(ent);
    ent->m_splineCollision->m_radius = fRadius;
    ent->m_splineCollision->createFromPoints(&g_linePoints, &g_lineNormals, 3, 0, 0);
    ((EEntityVirtuals *)ent)->UpdateCollision();
    return 0;
}

LUA_FUNCTION_TODO(CreateTightropeCollision)

LUA_FUNCTION_TODO(Spline_AddSkip)

LUA_FUNCTION(Spline_ClearSkips)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 1, 1))
        return 0;
    EEntity *ent = GetEntityArg(L, 1, false, 0);
    if (!ent)
        return 0;
    ESplineCollision *spline = ent->m_splineCollision;
    if (!spline)
        return 0;
    spline->clearSkips();
    return 0;
}

LUA_FUNCTION(Spline_ParametricToPoint)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 2, 2))
        return 0;
    EEntity *ent = GetEntityArg(L, 1, false, 0);
    if (!ent)
        return 0;
    float t = GetNumberArg(L, 2, false);
    ESplineCollision *spline = ent->m_splineCollision;
    if (!spline)
        return 0;
    Vector3 point = spline->parametricToPoint(t, 0);
    PushVector(L, point);
    return 3;
}

LUA_FUNCTION_TODO(Spline_GetRight)

LUA_FUNCTION_TODO(Spline_FindClosestTo)

LUA_FUNCTION_TODO(Spline_FindClosest)
