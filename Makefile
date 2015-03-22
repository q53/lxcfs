NAME = pylxcfs
VERSION = $(shell awk '/^Version:/ {print $$2}' pylxcfs.spec)
RELEASE = $(shell awk '/^Release:/ {print $$2}' pylxcfs.spec)
UNITDIR = $(shell rpm --eval '%{_unitdir}' 2>/dev/null || echo /usr/lib/systemd/system)
TMPFILESDIR = $(shell rpm --eval '%{_tmpfilesdir}' 2>/dev/null || echo /usr/lib/tmpfiles.d)
VERSIONED_NAME = $(NAME)-$(VERSION)

DESTDIR = /
DOCDIR = /usr/share/doc/$(NAME)
PYTHON_SITELIB = /usr/lib/python2.7/site-packages

archive: clean

	mkdir -p $(VERSIONED_NAME)
	cp README $(VERSIONED_NAME)

	cp -a pylxcfs.spec pylxcfs.service pylxcfs.py pylxcfs pylxcfs.hook pylxcfs.sysconfig Makefile $(VERSIONED_NAME)

	tar cjf $(VERSIONED_NAME).tar.bz2 $(VERSIONED_NAME)

srpm: archive
	mkdir rpm-build-dir
	rpmbuild --define "_sourcedir `pwd`/rpm-build-dir" --define "_srcrpmdir `pwd`/rpm-build-dir" \
	    --define "_specdir `pwd`/rpm-build-dir" --nodeps -ts $(VERSIONED_NAME).tar.bz2

build:
	# nothing to build

install:
	mkdir -p $(DESTDIR)

	# library
	mkdir -p $(DESTDIR)$(PYTHON_SITELIB)
	cp -a pylxcfs $(DESTDIR)$(PYTHON_SITELIB)

	mkdir -p $(DESTDIR)/etc/sysconfig
	cp pylxcfs.sysconfig $(DESTDIR)/etc/sysconfig/pylxcfs

	# binaries
	install -Dpm 0755 pylxcfs.py $(DESTDIR)/usr/sbin/pylxcfs

	#hooks        
	mkdir -p $(DESTDIR)/usr/share/lxc/hooks
	install -Dpm 0755 pylxcfs.hook $(DESTDIR)/usr/share/lxc/hooks/ 

	# runtime directory
	mkdir -p $(DESTDIR)/run/pylxcfs

	mkdir -p $(DESTDIR)/var/lib/pylxcfs

	# systemd units
	install -Dpm 0644 pylxcfs.service $(DESTDIR)$(UNITDIR)/pylxcfs.service

	mkdir -p $(DESTDIR)$(DOCDIR)
	cp README $(DESTDIR)$(DOCDIR)

clean:
	find -name "*.pyc" | xargs rm -f
	rm -rf $(VERSIONED_NAME) rpm-build-dir

PHONY: clean archive srpm tag

