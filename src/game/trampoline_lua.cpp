// Script functions, file name made up.

#include <malloc.h>
#include "engine.h"
#include "luafunc.h"

class ETrampolineEntity {
public:
    ETrampolineEntity(class EDomain *domain, const char *name);
    void *operator new(size_t size) { return _aligned_malloc(size, 16); }
    static EEntity *Create(class EDomain *domain, const char *name) { return (EEntity *)new ETrampolineEntity(domain, name); }
    void OnBeginLevel();
    void OnEntered(ETriggerBase *trigger);
    void SetBouncer(EEntity *bouncer);

    char pad0[0x170];

    static EClassInfo s_class;
};


// Constants the original gets from shared headers. Every file that includes them
// has its own copy, set up by a dynamic initializer at startup.
static const double PI = 3.14159265358979323846;
static const double DEG_TO_RAD = PI / 180.0;
static const float CONST_150 = 150.0f;
static const float CONST_50 = 50.0f;
static const float CONST_125 = CONST_150 - CONST_50 * 0.5f;
static const Vector2 s_bounceCurve[6] = {
    Vector2(0.0f, 0.0f), Vector2(1.0f, 1.0f), Vector2(0.33f, 0.33f),
    Vector2(1.0f, 1.0f), Vector2(0.66f, 0.66f), Vector2(1.0f, 1.0f)
};

EClassInfo ETrampolineEntity::s_class("ETrampolineEntity", -2, &ETrampolineEntity::Create, &g_meshEntityClass);

LUA_FUNCTION(Trampoline_onBeginLevel)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 1, 1))
        return 0;
    ETrampolineEntity *trampoline = (ETrampolineEntity *)GetEntityArg(L, 1, false, &ETrampolineEntity::s_class);
    if (!trampoline)
        return 0;
    trampoline->OnBeginLevel();
    return 0;
}

LUA_FUNCTION(Trampoline_onEntered)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 2, 2))
        return 0;
    ETrampolineEntity *trampoline = (ETrampolineEntity *)GetEntityArg(L, 1, false, &ETrampolineEntity::s_class);
    if (!trampoline)
        return 0;
    ETriggerBase *trg = GetTriggerArg(L, 2, false);
    if (!trg)
        return 0;
    trampoline->OnEntered(trg);
    return 0;
}

LUA_FUNCTION(Trampoline_onExited)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 2, 2))
        return 0;
    ETrampolineEntity *trampoline = (ETrampolineEntity *)GetEntityArg(L, 1, false, &ETrampolineEntity::s_class);
    if (!trampoline)
        return 0;
    ETriggerBase *trg = GetTriggerArg(L, 2, false);
    if (!trg)
        return 0;
    return 0;
}

LUA_FUNCTION(Trampoline_ClearBouncer)
{
    int n = lua_gettop(L);
    if (!CheckArgs(L, 1, 1))
        return 0;
    ETrampolineEntity *trampoline = (ETrampolineEntity *)GetEntityArg(L, 1, false, &ETrampolineEntity::s_class);
    if (!trampoline)
        return 0;
    trampoline->SetBouncer(0);
    return 0;
}
