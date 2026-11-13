// Skeleton storage and input reconstructed from the supported Steam executable.
// Layout and helper names are provisional; recursive loading remains external.
#include "engine.h"

// Local value views preserve established shared empty default constructors.
struct BoneMatrix : EMatrix {
    BoneMatrix() { *(EMatrix *)this = g_identityMatrix; }
    BoneMatrix &operator=(const BoneMatrix &other) {
        memcpy(this, &other, sizeof(BoneMatrix));
        return *this;
    }
};
struct BoneTranslation : Vector3 {
    BoneTranslation() { x = y = z = 0.0f; }
};
extern EQuat g_identityQuaternion;
struct BoneRotation : EQuat {
    void SetIdentity() { x=g_identityQuaternion.x; y=g_identityQuaternion.y; z=g_identityQuaternion.z; w=g_identityQuaternion.w; }
    BoneRotation() { x=0.0f; y=0.0f; z=0.0f; w=1.0f; }
};
struct BoneScale : Vector3 {
    BoneScale() { x=1.0f; y=1.0f; z=1.0f; }
};
struct SkeletonData {
    SkeletonData();
    void *name;
    struct BoneInfo *info;
    unsigned int count;
    void *operator new(size_t size) { return _aligned_malloc(size,16); }
};
struct BoneInfo {
    BoneInfo();
    ~BoneInfo();
    void SetName(const char *name);
    BoneMatrix matrix;
    BoneTranslation translation;
    BoneRotation rotation;
    char *name;
    void *operator new[](size_t size) { return _aligned_malloc(size,16); }
};
struct Skeleton;
struct RuntimeBone {
    RuntimeBone();
    ~RuntimeBone();
    RuntimeBone *ReadInput(class EStream *,unsigned int,Skeleton *);
    void Transform(const EMatrix &);
    RuntimeBone *GetParent();
    BoneMatrix first,second;
    BoneRotation rotation;
    BoneScale scale;
    BoneTranslation translation;
    Skeleton *owner;
    unsigned char index,parent,next;
    unsigned char flag0:1,flag1:1,hasChildren:1,flag3:1,flag4:1,flag5:1,flag6:1,flag7:1;
    void *operator new[](size_t size) { return _aligned_malloc(size,16); }
};
BoneInfo::~BoneInfo() { SetName(0); }
RuntimeBone::~RuntimeBone() {}

SkeletonData::SkeletonData() { name=0; info=0; count=0; } // 0x499ac0,43
BoneInfo::BoneInfo() { name=0; } // 0x491a10,117; member default init does rest
RuntimeBone::RuntimeBone() // 0x491b00,419
{
    owner=0; index=0xff; parent=0xff; next=0xff;
    flag0=1; flag1=0; hasChildren=0; flag3=0; flag4=0; flag5=0; flag6=0; flag7=0;
    *(EMatrix *)&first=g_identityMatrix;
    second=first;
}

class EStream {
public:
    virtual ~EStream() {}
    virtual const char *GetName() { return 0; }
    virtual void Read(void *,unsigned int)=0;
    void ReadString(char *, unsigned int);
    template <class T> void Transfer(T *data) { Read(data, sizeof(T)); }
};
void ReadSkeletonName(EStream *,SkeletonData *); // cdecl 0x6a5a10
struct Skeleton {
    bool ReadInput(EStream *,unsigned int);
    SkeletonData *data;
    BoneInfo *info;
    RuntimeBone *root;
    void *group;
    RuntimeBone *allocation;
    char unknown14[0x3c-0x14];
    unsigned char flagsLow0:1,flag1:1,flagsHigh2:6;
};
bool Skeleton::ReadInput(EStream *stream,unsigned int version) // 0x49a040,608
{
    data=new SkeletonData;
    flag1=0;
    ReadSkeletonName(stream,data);
    stream->Transfer(&data->count);
    allocation=new RuntimeBone[data->count];
    data->info=new BoneInfo[data->count];
    info=data->info;
    for(unsigned int i=0;i<data->count;++i)
        allocation[i].index=(unsigned char)i;
    root=allocation;
    unsigned short serializedRootId;
    stream->Read(&serializedRootId,2);
    if(!root->ReadInput(stream,version,this)) return false;
    root->flag1=1;
    root->Transform(g_identityMatrix);
    return true;
}
// The 16-byte aligned value members give 0x60-byte info and 0xb0-byte runtime
// records. User-declared destructors preserve the observed 16-byte array cookies.

typedef char BoneInfoSize[(sizeof(BoneInfo) == 0x60) ? 1 : -1];
typedef char RuntimeBoneSize[(sizeof(RuntimeBone) == 0xb0) ? 1 : -1];
typedef char SkeletonDataSize[(sizeof(SkeletonData) == 12) ? 1 : -1];

// 0x00492010: preorder traversal of caller-owned contiguous runtime records.
extern EQuat g_identityQuaternion;
RuntimeBone *RuntimeBone::ReadInput(EStream *stream,unsigned int version,Skeleton *skeleton)
{
    owner=skeleton;
    BoneInfo *boneInfo=&owner->info[index];
    flag0=0;
    char nameBuffer[260];
    stream->ReadString(nameBuffer,255);
    boneInfo->SetName(nameBuffer);
    owner=skeleton;
    BoneTranslation rotationAngles;
    stream->Read(&boneInfo->translation,12);
    stream->Read(&rotationAngles,12);
    Vector3 zero(-1.0f,-1.0f,-1.0f);
    if ((rotationAngles.x==zero.x && rotationAngles.y==zero.y && rotationAngles.z==zero.z) ? true : false) {
        boneInfo->rotation.SetIdentity();
        flag3=1;
    } else {
        boneInfo->rotation.SetEuler(rotationAngles);
    }
    translation=boneInfo->translation;
    rotation.EQuat::operator=(boneInfo->rotation);
    if(version>294) {
        unsigned short extra;
        stream->Read(&extra,2);
    }
    unsigned int childCount;
    stream->Read(&childCount,4);
    hasChildren=childCount!=0;
    if(hasChildren) {
        RuntimeBone *previous=0;
        RuntimeBone *child=hasChildren ? this+1 : 0;
        unsigned int i=0;
        while(i<childCount) {
            child->parent=index;
            if(previous) previous->next=child->index;
            unsigned short serializedId;
            stream->Read(&serializedId,2);
            previous=child;
            child=child->ReadInput(stream,version,skeleton);
            ++i;
        }
        return child;
    } else {
        return this+1;
    }
}

// 0x00491ab0: category-8 string ownership; input may alias the freed name.
void FreeFileName(char *block, int category, int flags);
char *CopyFileName(const char *name, int category);
void BoneInfo::SetName(const char *value)
{
    if (name) {
        FreeFileName(name, 8, 1);
        name = 0;
    }
    if (value)
        name = CopyFileName(value, 8);
}

// 0x00492720: the indices are relative to contiguous runtime records.
RuntimeBone *RuntimeBone::GetParent()
{
    return parent != 0xff ? this - index + parent : 0;
}
