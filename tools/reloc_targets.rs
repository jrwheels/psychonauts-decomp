// Optional bulk decoder for objmatch's i386 COFF relocation targets.
use std::slice;

#[no_mangle]
pub extern "C" fn psy_reloc_abi() -> u32 {
    1
}

/// All nonempty buffers must be valid for their stated lengths. Output buffers
/// must be writable and must not overlap inputs or one another. Zero marks a
/// missing target; its value is ignored. Returns 1 for invalid lengths/pointers.
#[no_mangle]
pub unsafe extern "C" fn psy_reloc_targets(
    text: *const u8, text_len: usize, text_va: u64,
    hits: *const u64, hit_count: usize,
    offsets: *const u32, kinds: *const u32, addends: *const u32, reloc_count: usize,
    values: *mut u32, present: *mut u8, output_len: usize,
) -> u32 {
    let Some(cells) = hit_count.checked_mul(reloc_count) else { return 1 };
    if cells != output_len
        || (text_len != 0 && text.is_null())
        || (hit_count != 0 && hits.is_null())
        || (reloc_count != 0 && (offsets.is_null() || kinds.is_null() || addends.is_null()))
        || (cells != 0 && (values.is_null() || present.is_null()))
        || text_len > isize::MAX as usize
        || hit_count > isize::MAX as usize / 8
        || reloc_count > isize::MAX as usize / 4
        || cells > isize::MAX as usize / 4
    {
        return 1;
    }
    if cells == 0 {
        return 0;
    }
    let text = if text_len == 0 { &[] } else { slice::from_raw_parts(text, text_len) };
    let hits = slice::from_raw_parts(hits, hit_count);
    let offsets = slice::from_raw_parts(offsets, reloc_count);
    let kinds = slice::from_raw_parts(kinds, reloc_count);
    let addends = slice::from_raw_parts(addends, reloc_count);
    let values = slice::from_raw_parts_mut(values, cells);
    let present = slice::from_raw_parts_mut(present, cells);
    for (i, &va) in hits.iter().enumerate() {
        for j in 0..reloc_count {
            let cell = i * reloc_count + j;
            present[cell] = 0;
            values[cell] = 0;
            if kinds[j] != 6 && kinds[j] != 0x14 {
                continue;
            }
            let Some(position) = va.checked_add(offsets[j] as u64)
                .and_then(|address| address.checked_sub(text_va))
                .and_then(|offset| usize::try_from(offset).ok()) else { continue };
            let Some(end) = position.checked_add(4) else { continue };
            let Some(raw) = text.get(position..end) else { continue };
            let mut value = u32::from_le_bytes([raw[0], raw[1], raw[2], raw[3]])
                .wrapping_sub(addends[j]);
            if kinds[j] == 0x14 {
                value = value.wrapping_add(va as u32).wrapping_add(offsets[j]).wrapping_add(4);
            }
            values[cell] = value;
            present[cell] = 1;
        }
    }
    0
}
