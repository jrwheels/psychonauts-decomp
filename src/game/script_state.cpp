// Script-state transitions reconstructed from the supported Steam PE32.
// Thread/state names are provisional; numeric status 4 has no asserted enum name.
#include "engine.h"

// Partial, nonallocating view of the fields touched by these helpers.
struct EScriptThread {
    void Reset();
    char unknown00[0x40];
    lua_State *m_L;             // 0x40
    char unknown44[0x4c - 0x44];
    int m_status;              // 0x4c
    char unknown50[0x58 - 0x50];
    unsigned int m_field58;     // 0x58
};

void EScriptObject::SetState(lua_State *L) // 0x005cb1e0, 323 bytes
{
    if (lua_gettop(L) < 1) {
        lua_error(L, "ScriptVM: Wrong call to SetState. Usage: object:SetState(object.NewState);");
        return;
    }
    if (!lua_istable(L, 1) || (!lua_isfunction(L, 2) && !lua_isnil(L, 2))) {
        lua_error(L, "ScriptVM: Wrong args passed to SetState. Usage: object:SetState(object.NewState);");
        return;
    }
    lua_pushstring(L, "CurrentState");
    lua_pushvalue(L, 2);
    lua_settable(L, 1);
    if (lua_isnil(L, 2))
        m_1c_2 = true;
    else
        m_1c_2 = false;
    if (m_threadIndex) {
        EScriptManager *manager = GetScriptManager();
        EScriptThread *thread = manager->GetThread(m_threadIndex);
        int state = thread->m_status;
        if (state == 4) {
            m_threadIndex = 0;
            thread->Reset();
            GetScriptManager()->ReleaseThread(thread);
        }
    }
}

EScriptThread *EScriptManager::GetThread(unsigned char index) // 0x005cdef0, 49
{
    if (!index)
        return 0;
    index = index - 1;
    return m_threads[index];
}

void EScriptThread::Reset() // 0x005ca870, 48
{
    m_L->top = m_L->stack;
    m_field58 = 0;
    m_status = 0;
}

void EScriptManager::ReleaseThread(EScriptThread *thread) // 0x005ce220, 147
{
    for (unsigned int i = 0; i < 64; ++i) {
        if (ThreadIsUsed(i) && m_threads[i] == thread) {
            ClearThreadUsed(i);
            break;
        }
    }
}
