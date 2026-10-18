// File-backed resource input; stream class names are confirmed by RTTI.
#include "diagnostic.h"

class EStream {
public:
    EStream() : m_flags(0), m_error(false) {}
    virtual ~EStream() {}
    void operator delete(void *block) { _aligned_free(block); }
    virtual const char *GetName() { return 0; }
    virtual void Read(void *data, unsigned int size) = 0;

    unsigned int m_flags;          // +0x04
    unsigned int m_unknown8;
    bool m_error;                  // +0x0c
};

class EFileStream : public EStream {
public:
    EFileStream(DiagnosticFile *file, int mode) : m_file(file), m_owned(mode == 1) {}
    ~EFileStream();
    const char *GetName();

    DiagnosticFile *m_file;         // +0x10
    bool m_owned;                  // +0x14
};

class EFileReader : public EFileStream {
public:
    EFileReader(DiagnosticFile *file, int mode) : EFileStream(file, mode) {}
    void Read(void *data, unsigned int size);
    void ReadBytes(void *data, unsigned int size);
};

const char *EFileStream::GetName()
{
    const char *name = m_file->m_name;
    return name;
}

EFileStream::~EFileStream()
{
    if (m_owned) {
        if (m_file)
            m_file->Close();
        m_file = 0;
    }
}

void EFileReader::Read(void *data, unsigned int size)
{
    ReadBytes(data, size);
}

void EFileReader::ReadBytes(void *data, unsigned int size)
{
    if (data) {
        if (m_file->Read(data, size) != size)
            m_error = true;
    } else {
        m_file->Seek(size, 1);
    }
}

class MeshResourceReader {
public:
    void *LoadFile(const char *name, int flags);
    void *ReadResource(EFileReader *reader, int flags);
};

void *MeshResourceReader::LoadFile(const char *name, int flags)
{
    DiagnosticFile *file = g_diagnosticFileFactory->Open(name, 0x400, 0);
    if (!file)
        return 0;
    EFileReader reader(file, 1);
    return ReadResource(&reader, flags);
}

struct ResourceListNode {
    ResourceListNode *m_prev;
    ResourceListNode *m_next;
    void *m_data;
};

class ResourceList {
public:
    void *PopFront();
    void ReleaseNode(ResourceListNode *node);

    char pad0[0x10];
    ResourceListNode *m_last;       // +0x10
    ResourceListNode *m_first;      // +0x14
};

void *ResourceList::PopFront()
{
    ResourceListNode *first = m_first;
    void *data = first->m_data;
    m_first = first->m_next;
    if (m_first)
        m_first->m_prev = 0;
    else
        m_last = 0;
    ReleaseNode(first);
    return data;
}
