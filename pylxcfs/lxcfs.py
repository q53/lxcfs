#!/usr/bin/python

import errno
import os
import stat
import time
import sys
import pylxcfs.fuse as fuse



class ProcCache:
    '''
    Simple "file cache" class. Any entry with the timestamp > __utd_time assumes as outdated 
    and should be updated. Any read do refresh the timestamp for a cgroup, cgroups with the
    timestamp > __retention  wipes out during update().
    '''

    __retention = 60
    __utd_time = 10

    def __init__(self):
        self.__cache = {}

    def __cached(self,cgroup,entry):
        return cgroup in self.__cache.keys() and entry in self.__cache[cgroup].keys()

    def cache_isuptodate(self,cgroup,entry):
        if cgroup not in self.__cache.keys():  self.__cache[cgroup] = {}
        self.__cache[cgroup]['t'] = time.time()
        return self.__cached(cgroup,entry) and self.__cache[cgroup][entry]['t'] > self.__cache[cgroup]['t'] - self.__utd_time

    def get(self,cgroup,entry):
        #if self.__cached(self,cgroup,entry):
        #    self.__cache[cgroup]['t'] = time.time()
            return self.__cache[cgroup][entry]['c']
        #else:
        #    return None

    def update(self,cgroup,entry,content):
        if cgroup not in self.__cache.keys():  self.__cache[cgroup] = {}
        if entry not in self.__cache[cgroup].keys(): self.__cache[cgroup][entry] = {}
        self.__cache[cgroup]['t'] = time.time()
        self.__cache[cgroup][entry]['t'] = self.__cache[cgroup]['t']
        self.__cache[cgroup][entry]['c'] = content
        for e in filter(lambda x:
                                  self.__cache[cgroup]['t'] -
                                  self.__cache[x]['t'] >
                                  self.__retention, self.__cache.keys()):
           del self.__cache[e]
        

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


def get_controller_paths():
    controlles = {'cpuset':None, 'cpu':None, 'cpuacct':None, 'memory':None, 'devices':None,
                  'freezer':None, 'net_cls':None, 'blkio':None, 'perf_event':None, 'hugetlb':None}
    with open("/proc/mounts","r") as fd:
        for line in fd:
            if line.startswith("cgroup") and filter(lambda k: k in line, controlles.keys()):
               fields = line.split()
               for k in filter(lambda c: c in controlles.keys(), fields[3].split(",")):
                   controlles[k] = fields[1]
    return controlles


def get_cgroup_value(c_path,cgroup,key):
    with open("%s/%s/%s" % (c_path,cgroup,key), "r") as fd:
        v = fd.read()
    return v.strip()


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

    cgroup = get_cgroup(pid, "cpuset")

    if cache.cache_isuptodate(cgroup,"cpuinfo"):
        return cache.get(cgroup,"cpuinfo")

    if not cache.cache_isuptodate(cgroup,"ctrs"):
        cache.update(cgroup,"ctrs",get_controller_paths())
     
    ctrs = cache.get(cgroup,"ctrs") 

    # Grab the current global values
    with open("/proc/cpuinfo", "r") as fd:
        cpus = fd.read().split("\n\n")

    value = get_cgroup_value(ctrs["cpuset"],
                             cgroup,
                            "cpuset.cpus")

    # Generate the new cpuinfo
    entries = []
    count = 0
    for i in expand_range(value):
        entries.append(cpus[i].replace("processor\t: %s" % i,
                                       "processor\t: %s" % count))
        count += 1

    cache.update(cgroup,"cpuinfo","%s\n" % "\n\n".join(entries))
    return cache.get(cgroup,"cpuinfo")


def get_meminfo():
    """
        Generates a new /proc/meminfo
    """

    uid, gid, pid = fuse.fuse_get_context()

    # Grab the current cgroup values
    cgroup = get_cgroup(pid, "memory")

    if cache.cache_isuptodate(cgroup,"meminfo"):
        return cache.get(cgroup,"meminfo")

    if not cache.cache_isuptodate(cgroup,"ctrs"):
        cache.update(cgroup,"ctrs",get_controller_paths())

    ctrs = cache.get(cgroup,"ctrs")

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

    cgm = {}
    cgm['limit_in_bytes'] = int(get_cgroup_value(ctrs["memory"],cgroup,
                                                 "memory.limit_in_bytes"))
    cgm['vlimit_in_bytes'] = int(get_cgroup_value(ctrs["memory"],cgroup,
                                                  "memory.memsw.limit_in_bytes"))
    cgm['usage_in_bytes'] = int(get_cgroup_value(ctrs["memory"],cgroup,
                                                 "memory.usage_in_bytes"))
    cgm['vusage_in_bytes'] = int(get_cgroup_value(ctrs["memory"],cgroup,
                                                  "memory.memsw.usage_in_bytes"))


    cgm_stat = get_cgroup_value(ctrs["memory"], cgroup, "memory.stat")
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

        if key == "SwapTotal":
            if cgm['vlimit_in_bytes'] - cgm['limit_in_bytes'] < value * 1024:
                value = ( cgm['vlimit_in_bytes'] - cgm['limit_in_bytes'] ) / 1024

        elif key == "MemFree":
            value = meminfo_dict['MemTotal'] - cgm['usage_in_bytes'] / 1024

        elif key == "SwapFree":
            value = ( cgm['vlimit_in_bytes'] - cgm['limit_in_bytes']
              - cgm['vusage_in_bytes'] + cgm['usage_in_bytes'] ) / 1024

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

    cache.update(cgroup,"meminfo",output)
    return cache.get(cgroup,"meminfo")


def get_stat():
    """
        Generates a new /proc/stat
    """

    uid, gid, pid = fuse.fuse_get_context()

    cgroup = get_cgroup(pid, "cpuset")

    if cache.cache_isuptodate(cgroup,"stat"):
        return cache.get(cgroup,"stat")

    if not cache.cache_isuptodate(cgroup,"ctrs"):
        cache.update(cgroup,"ctrs",get_controller_paths())

    ctrs = cache.get(cgroup,"ctrs")

    value = expand_range(get_cgroup_value(ctrs["cpuset"],
                                          cgroup,
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

    cache.update(cgroup,"stat",output)
    return cache.get(cgroup,"stat")


def get_uptime():
    """
        Generates a new /proc/uptime
    """

    uid, gid, pid = fuse.fuse_get_context()

    cgroup = get_cgroup(pid, "cpuset")

    if not cache.cache_isuptodate(cgroup,"ctrs"):
        cache.update(cgroup,"ctrs",get_controller_paths())

    ctrs = cache.get(cgroup,"ctrs")

    if not cache.cache_isuptodate(cgroup,"oldest_pid"):
        value = [ int(v) 
                  for v in get_cgroup_value(ctrs["cpuset"],cgroup,"tasks").split("\n") ]
        oldest_pid = sorted([os.stat("/proc/%s" % entry).st_ctime
                             for entry in value])[0]
        cache.update(cgroup,"oldest_pid",oldest_pid)

    oldest_pid = cache.get(cgroup,"oldest_pid")

    with open("/proc/uptime", "r") as fd:
        fields = fd.read().split()
        fields[0] = str(round(time.time() - oldest_pid, 2))

    return "%s\n" % " ".join(fields)


# List of supported files with their callback function
files = {'/proc/cpuinfo': get_cpuinfo,
         '/proc/meminfo': get_meminfo,
         '/proc/stat': get_stat,
         '/proc/uptime': get_uptime}


class LXCFuse(fuse.LoggingMixIn, fuse.Operations):
    def __init__(self, path='.'):
        self.root = path

    def getattr(self, path, fh=None):
        st = {}
        st['st_atime'] = time.time()
        st['st_ctime'] = time.time()
        st['st_mtime'] = time.time()

        if path == "/":
            st['st_mode'] = stat.S_IFDIR | 0o755
            st['st_nlink'] = 2
        elif path == "/proc":
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
        if path == "/":
            return ['.', '..', 'proc']
        elif path == "/proc":
            return ['.', '..'] + [os.path.basename(entry)
                                  for entry in files.keys()
                                  if entry.startswith("/proc/")]
        else:
            raise fuse.FuseOSError(errno.ENOENT)

    def read(self, path, size, offset, fh):
        if path in files:
            content = files[path]()
        else:
            raise fuse.FuseOSError(errno.ENOENT)

        slen = len(content)
        if offset < slen:
            if offset + size > slen:
                size = slen - offset
            buf = content[offset:offset+size]
        else:
            buf = ''
        return buf

cache = ProcCache()

