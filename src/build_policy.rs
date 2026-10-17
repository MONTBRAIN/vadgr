//! Artifact classification, not publisher authentication or release authority.

pub const UNSIGNED_QUALIFICATION: bool = cfg!(feature = "linux-unsigned-qualification");
pub const UNSIGNED_WARNING: &str = "Unsigned development build. Not for release.";

#[cfg(target_os = "linux")]
#[repr(C, align(4))]
struct PolicyNote {
    name_size: u32,
    descriptor_size: u32,
    kind: u32,
    owner: [u8; 8],
    schema: u32,
    mode: u32,
}

// build.rs roots this symbol so linker garbage collection cannot remove it.
#[cfg(target_os = "linux")]
#[used]
#[unsafe(no_mangle)]
#[unsafe(link_section = ".note.vadgr.build")]
static VADGR_BUILD_POLICY_NOTE: PolicyNote = PolicyNote {
    name_size: 6,
    descriptor_size: 8,
    kind: 0x5644_4752,
    owner: *b"VADGR\0\0\0",
    schema: 1,
    mode: if UNSIGNED_QUALIFICATION { 2 } else { 1 },
};
