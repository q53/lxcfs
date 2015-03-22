#!/usr/bin/python

from  pylxcfs.lxcfs import LXCFuse
import  pylxcfs.fuse as fuse
import sys

if __name__ == "__main__":

    server = fuse.FUSE(LXCFuse(), sys.argv[1], allow_other=True,
                   foreground=True,nothreads=True)

