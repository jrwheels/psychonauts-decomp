// EReadBufferedFile identity is verified by RTTI; method/member names are
// provisional. Partial layout only: construction and lifetime are unresolved.
#include "diagnostic.h"
#include <string.h>

struct EReadBufferedFile {
    char opaque0[8];
    DiagnosticFile *m_file;       // +0x08
    char *m_buffer;               // +0x0c
    unsigned int m_capacity;      // +0x10
    unsigned int m_valid;         // +0x14
    unsigned int m_position;      // +0x18

    unsigned int Read(void *data, unsigned int size);
    void Refill();
    unsigned int Size();
};

unsigned int EReadBufferedFile::Read(void *data, unsigned int size)
{
    unsigned int result, refillAvailable, refillCopy;
    unsigned int bytesLeft = size;
    unsigned int availableCount = m_valid - m_position;
    // Both minima use signed comparisons in the original x86 code. Keep
    // arithmetic unsigned so subtraction/addition retain their 32-bit wrap.
    unsigned int initialCopy = (int)bytesLeft < (int)availableCount ? bytesLeft : availableCount;
    if (initialCopy) {
        memcpy(data, m_buffer + m_position, initialCopy);
        m_position += initialCopy;
        bytesLeft -= initialCopy;
        data = (char *)data + initialCopy;
    }
    if (!bytesLeft)
        return initialCopy;
    if (bytesLeft > m_capacity) {
        result = m_file->Read(data, bytesLeft);
        return initialCopy + result;
    } else {
        Refill();
        refillAvailable = m_valid - m_position;
        refillCopy = (int)bytesLeft < (int)refillAvailable ? bytesLeft : refillAvailable;
        if (refillCopy) {
            memcpy(data, m_buffer + m_position, refillCopy);
            m_position += refillCopy;
            bytesLeft -= refillCopy;
        }
        return initialCopy + refillCopy;
    }
}

void EReadBufferedFile::Refill()
{
    m_valid = m_file->Read(m_buffer, m_capacity);
    m_position = 0;
}

unsigned int EReadBufferedFile::Size()
{
    return m_file->Size();
}

// Separate layout from EReadBufferedFile: the buffer is at +0x18 here.
// RTTI confirms EWriteBufferedFile; this is still an opaque partial view.
// In-class Flush is deliberately retained: RTM declines to inline its body
// but reserves its temporary stack space in Write/Seek, as in the executable.
struct EWriteBufferedFile {
    char opaque0[8];
    DiagnosticFile *m_file;
    unsigned int m_capacity, m_pending, m_start;
    char *m_buffer;
    unsigned int Write(const void *data, unsigned int size);
    void Flush()
    {
        if (m_pending == 0)
            return;
        unsigned int result = m_file->Write(m_buffer, m_pending);
        m_pending = 0;
        m_start = 0;
    }
    unsigned int Seek(int offset, int origin);
};

unsigned int EWriteBufferedFile::Write(const void *data, unsigned int size)
{
    if (size >= m_capacity) {
        Flush();
        return m_file->Write(data, size);
    } else {
        if (m_pending + size >= m_capacity)
            Flush();
        if (m_pending == 0)
            m_start = m_file->Seek(0, 1);
        memcpy(m_buffer + m_pending, data, size);
        m_pending += size;
        return size;
    }
}

unsigned int EWriteBufferedFile::Seek(int offset, int origin)
{
    Flush();
    return m_file->Seek(offset, origin);
}
