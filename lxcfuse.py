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
    """
        Takes a string representing a list of integers and integer
        ranges and returns an expanded list of integers.
    """

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
    """
        Takes a pid and a cgroup controller name and returns the full
        cgroup path for that task.
    """

    with open("/proc/%s/cgroup" % pid, "r") as fd:
        for line in fd:
            fields = line.split(":")
            if fields[1] == controller:
                return fields[2].strip()


def get_cpuinfo():
    """
        Generates a new /proc/cpuinfo
    """

    uid, gid, pid = fuse.fuse_get_context()

    # Grab the current global values
    with open("/proc/cpuinfo", "r") as fd:
        cpus = fd.read().split("\n\n")

    # Grab the current cgroup values
    value = cgmanager.GetValue("cpuset",
                               get_cgroup(pid, "cpuset"),
                               "cpuset.cpus")

    # Generate the new cpuinfo
    entries = []
    count = 0
    for i in expand_range(value):
        entries.append(cpus[i].replace("processor\t: %s" % i,
                                       "processor\t: %s" % count))
        count += 1

    return "%s\n" % "\n\n".join(entries)


def get_meminfo():
    """
        Generates a new /proc/meminfo
    """

    uid, gid, pid = fuse.fuse_get_context()

    # Grab the current global values
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

    # Grab the current cgroup values
    cgroup = get_cgroup(pid, "memory")

    cgm = {}
    cgm['limit_in_bytes'] = int(cgmanager.GetValue("memory", cgroup,
                                                   "memory.limit_in_bytes"))
    cgm['usage_in_bytes'] = int(cgmanager.GetValue("memory", cgroup,
                                                   "memory.usage_in_bytes"))

    cgm_stat = cgmanager.GetValue("memory", cgroup, "memory.stat")
    cgm['stat'] = {}
    for line in cgm_stat.split("\n"):
        fields = line.split()
        cgm['stat'][fields[0].strip()] = fields[1].strip()

    # Update the values
    meminfo_dict = {}
    for i in range(len(meminfo)):
        key, value, unit = meminfo[i]
        if key == "MemTotal":
            if cgm['limit_in_bytes'] < value * 1024:
                value = cgm['limit_in_bytes'] / 1024

        elif key == "MemFree":
            value = meminfo_dict['MemTotal'] - cgm['usage_in_bytes'] / 1024

        elif key == "MemAvailable":
            value = meminfo_dict['MemFree']

        elif key == "Cached":
            value = int(cgm['stat']['total_cache']) / 1024

        elif key in ("Buffers", "SwapCached"):
            value = 0

        meminfo[i] = (key, value, unit)
        meminfo_dict[key] = value

    # Generate the new meminfo file
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


def get_stat():
    """
        Generates a new /proc/stat
    """

    uid, gid, pid = fuse.fuse_get_context()

    value = expand_range(cgmanager.GetValue("cpuset",
                                            get_cgroup(pid, "cpuset"),
                                            "cpuset.cpus"))

    output = ""
    count = 0
    with open("/proc/stat", "r") as fd:
        for line in fd:
            if line.startswith("cpu") and not line.startswith("cpu "):
                for cpu in value:
                    if not line.startswith("cpu%s" % cpu):
                        continue

                    line = line.replace("cpu%s" % cpu, "cpu%s" % count)
                    count += 1
                    break
                else:
                    continue
            output += line

    return output


# List of supported files with their callback function
files = {'/cpuinfo': get_cpuinfo,
         '/meminfo': get_meminfo,
         '/stat': get_stat}


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


server = fuse.FUSE(LXCFuse(), sys.argv[1], allow_other=True,
                   foreground=True)
