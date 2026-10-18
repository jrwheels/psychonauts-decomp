// Native mesh joint lookup; names and partial layouts follow script callers.
#include "engine.h"

struct EBoneInfo {
    const char *GetName() { return m_name; }

    char pad0[0x5c];
    const char *m_name;             // 0x5c
};

struct ESkeleton {
    char pad0[4];
    EBoneInfo *m_bones;             // 0x04
};

struct EBone {
    EBoneInfo *GetInfo() { return &m_skeleton->m_bones[m_index]; }
    EBone *Find(const char *name);
    EBone *GetNext();

    char pad0[0xa8];
    ESkeleton *m_skeleton;          // 0xa8
    unsigned char m_index;          // 0xac
    unsigned char m_ad;
    unsigned char m_next;           // 0xae; 0xff ends the sibling chain
    unsigned char m_flags : 2;
    unsigned char m_hasChildren : 1;
    unsigned char m_otherFlags : 5;
};

struct EJointInfo {
    const char *m_name;
};

struct EJoint {
    EJointInfo *m_info;             // 0x00
    char pad4[4];
    EBone *m_bone;                  // 0x08
};

class ETriggerA8 {
public:
    EBone *FindBone(const char *name);
    EJoint *FindJoint(const char *name);

    char pad0[0x54];
    TArray<EJoint *> m_joints;       // 0x54
};

EBone *ETriggerA8::FindBone(const char *name)
{
    EBone *bone;
    for (unsigned int i = 0; i < m_joints.m_count; i++) {
        bone = m_joints[i]->m_bone->Find(name);
        if (bone)
            return bone;
    }
    return 0;
}

EJoint *ETriggerA8::FindJoint(const char *name)
{
    for (unsigned int i = 0; i < m_joints.m_count; i++) {
        EJoint *joint = m_joints[i];
        const char *boneName = joint->m_info->m_name;
        if (strcmp(boneName, name) == 0)
            return joint;
    }
    return 0;
}

EBone *EBone::GetNext()
{
    return m_next != 0xff ? this - m_index + m_next : 0;
}

EBone *EBone::Find(const char *name)
{
    if (_stricmp(name, GetInfo()->GetName()) == 0)
        return this;
    EBone *child = m_hasChildren ? this + 1 : 0;
    for (; child; child = child->GetNext()) {
        EBone *bone = child->Find(name);
        if (bone)
            return bone;
    }
    return 0;
}
