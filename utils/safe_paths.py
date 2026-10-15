"""Descriptor/handle guards for destructive operations on untrusted trees."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import sys


def destructive_absolute(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    # macOS exposes these administrator-owned system aliases by default.
    # Normalize only their exact standard destinations, never user aliases.
    if sys.platform == "darwin":
        for name in ("var", "tmp", "etc"):
            alias, target = Path("/") / name, Path("/private") / name
            if (absolute == alias or alias in absolute.parents) and alias.is_symlink():
                if os.readlink(alias) == str(target):
                    return target / absolute.relative_to(alias)
    return absolute


@contextmanager
def pinned_directories(path: Path, *, include_leaf: bool = False):
    """On Windows deny directory replacement/reparse changes during pathname use."""
    handles = []
    if os.name != "nt":
        yield
        return
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    class Attributes(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]
    absolute = destructive_absolute(path)
    paths = list(absolute.parents)
    paths.reverse()
    if include_leaf:
        paths.append(absolute)
    try:
        for parent in paths:
            # Read access; share reads but deny writes/deletes so a
            # checked directory cannot become a junction or be renamed.
            handle = api.CreateFileW(str(parent), 0x80000000, 1, None, 3, 0x02200000, None)
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
            info = Attributes()
            if not api.GetFileInformationByHandleEx(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
                raise ctypes.WinError(ctypes.get_last_error())
            if info.attributes & 0x400 or not info.attributes & 0x10:
                raise OSError("Directory links/reparse points are not permitted")
        yield
    finally:
        for handle in reversed(handles):
            api.CloseHandle(handle)


@contextmanager
def parent_descriptor(path: Path):
    """Walk every POSIX parent without following aliases, retaining its descriptor."""
    absolute = destructive_absolute(path)
    descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in absolute.parts[1:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor, absolute.name
    finally:
        os.close(descriptor)


@contextmanager
def overwrite_file(path: Path):
    """Open once, refuse aliases/special files and retain identity through all passes."""
    if os.name == "nt":
        import ctypes
        import msvcrt
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        with pinned_directories(path):
            handle = api.CreateFileW(str(path), 0xC0000000, 1, None, 3, 0x00200000, None)
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
            with os.fdopen(descriptor, "r+b", buffering=0) as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400 or metadata.st_nlink > 1:
                    raise OSError("Only unshared regular files may be overwritten")
                yield stream
    else:
        with parent_descriptor(path) as (parent, name):
            descriptor = os.open(name, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(descriptor, "r+b", buffering=0) as stream:
                metadata = os.fstat(stream.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink > 1:
                    raise OSError("Only unshared regular files may be overwritten")
                yield stream


def remove_posix(path: Path, protected, contains_protected) -> bool:
    """Remove relative to held directories; replacement names never redirect recursion."""
    def remove_at(parent, name, display):
        if protected(display):
            return False
        metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode):
            return False
        if stat.S_ISDIR(metadata.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            complete = True
            removed = False
            try:
                for entry in os.listdir(child):
                    if protected(display / entry):
                        continue
                    try:
                        removed = remove_at(child, entry, display / entry) or removed
                    except OSError:
                        complete = False
            finally:
                os.close(child)
            if not contains_protected(display):
                try:
                    os.rmdir(name, dir_fd=parent)
                    removed = True
                except OSError:
                    complete = False
            return complete and removed
        else:
            os.unlink(name, dir_fd=parent)
        return True
    with parent_descriptor(path) as (parent, name):
        return remove_at(parent, name, path)
