Summary: Python fuse lxcfs 
Name: pylxcfs
Version: 0.1.0
Release: 1%{?dist}
License: GPLv2+
Source: pylxcfs-%{version}.tar.bz2
#URL: 
BuildArch: noarch
BuildRequires: python
Requires: python, systemd

%description
Based on early implementation of lxcfs. No dependences on cgmanager and dbus.


%prep
%setup -q


%build


%install
make install DESTDIR=%{buildroot}

%post
%systemd_post pylxcfs.service


%preun
%systemd_preun pylxcfs.service


%postun

%posttrans

%files
%defattr(-,root,root,-)
%dir %{python_sitelib}/pylxcfs
%{python_sitelib}/pylxcfs/*
%{_sbindir}/pylxcfs
 /usr/lib/systemd/system/pylxcfs.service
%config(noreplace) /etc/sysconfig/pylxcfs
/usr/share/doc/pylxcfs/README
/usr/share/lxc/hooks/pylxcfs.hook
%dir /var/lib/pylxcfs
%dir /run/pylxcfs


%changelog
* Sun Mar 22 2015 Alexey Kurnosov <pylxcfs@kurnosov.spb.ru> - 0.1.0
- first  release
