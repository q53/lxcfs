#!/usr/bin/python

import dbus
import errno
import fuse
import stat
import sys


bus = dbus.connection.Connection("unix:path=/sys/fs/cgroup/cgmanager/sock")

cgmanager = bus.get_object("org.linuxcontainers.cgmanager",
                           "/org/linuxcontainers/cgmanager")


def expand_range(intrange):
    result = []
    for part in intrange.split(','):
        if '-' in part:
            a, b = part.split('-')
            a, b = int(a), int(b)
            result.extend(range(a, b + 1))
        else:
            a = int(part)
            result.append(a)
    return result


def get_cgroup(pid, controller):
    with open("/proc/%s/cgroup" % pid, "r") as fd:
        for line in fd:
            fields = line.split(":")
            if fields[1] == controller:
                return fields[2].strip()


def get_cpuinfo():
    uid, gid, pid = fuse.fuse_get_context()

    with open("/proc/cpuinfo", "r") as fd:
        cpus = fd.read().split("\n\n")

    value = cgmanager.GetValue("cpuset",
                               get_cgroup(pid, "cpuset"),
                               "cpuset.cpus")

    entries = []

    count = 0
    for i in expand_range(value):
        entries.append(cpus[i].replace("processor\t: %s" % i,
                                       "processor\t: %s" % count))
        count += 1

    return "%s\n" % "\n\n".join(entries)


def get_meminfo():
    uid, gid, pid = fuse.fuse_get_context()

    meminfo = []
    with open("/proc/meminfo", "r") as fd:
        for line in fd:
            fields = line.split(":")

            key = fields[0].strip()

            value_fields = fields[1].strip().split()
            value = int(value_fields[0])
            unit = ""
            if len(value_fields) > 1:
                unit = value_fields[1]

            meminfo.append((key, value, unit))

    # Update the values
    for i in range(len(meminfo)):
        key, value, unit = meminfo[i]
        if key == "MemTotal":
            cgm_value = cgmanager.GetValue("memory",
                                           get_cgroup(pid, "memory"),
                                           "memory.limit_in_bytes")
            if int(cgm_value) < value * 1024:
                value = int(cgm_value) / 1024
                meminfo[i] = (key, value, unit)

    output = ""
    for key, value, unit in meminfo:
        if unit:
            output += "{key:15} {value} {unit}\n".format(key="%s:" % key,
                                                         value="%8lu" % value,
                                                         unit=unit)
        else:
            output += "{key:15} {value}\n".format(key="%s:" % key,
                                                  value="%8lu" % value)

    return output


files = {'/cpuinfo': get_cpuinfo,
         '/meminfo': get_meminfo}


class LXCFuse(fuse.LoggingMixIn, fuse.Operations):
    def __init__(self, path='.'):
        self.root = path

    def getattr(self, path, fh=None):
        st = {}

        if path == '/':
            st['st_mode'] = stat.S_IFDIR | 0o755
            st['st_nlink'] = 2
        elif path in files:
            st['st_mode'] = stat.S_IFREG | 0o444
            st['st_nlink'] = 1
            st['st_size'] = len(files[path]())
        else:
            raise fuse.FuseOSError(errno.ENOENT)
        return st

    def readdir(self, path, fh):
        return ['.', '..'] + ["".join(entry[1:]) for entry in files.keys()]

    def read(self, path, size, offset, fh):
        if path not in files:
            raise fuse.FuseOSError(errno.ENOENT)

        content = files[path]()

        slen = len(content)
        if offset < slen:
            if offset + size > slen:
                size = slen - offset
            buf = content[offset:offset+size]
        else:
            buf = ''
        return buf


server = fuse.FUSE(LXCFuse(), sys.argv[1], foreground=True)
