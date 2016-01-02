#!/usr/bin/python -tt

try:
    # RHEL 6 and earlier
    import simplejson as json
except ImportError:
    # RHEL 7 and later
    import json

import bz2
from ConfigParser import ConfigParser
import fakeco
import fakepo
from fnmatch import fnmatch
import multilib

# if you want to test the testing with the original mash code
#import mash.multilib as multilib

class test_methods(object):

    @classmethod
    def setup_class(cls):
        # read test data
        try:
            fd = bz2.BZ2File('testdata/RHEL-7.1-Server-x86_64.json.bz2', 'r')
            pj = json.load(fd)
        except IOError:
            print 'Run the tests in the same directory as multilib.py'
            print 'There should be a testdata subdirectory there'
            raise
        cls.packages = pj
        fd.close()

        # read multilib configuration
        cp = ConfigParser()
        assert len(cp.read('/etc/multilib.conf')) == 1, 'missing /etc/multilib.conf'
        cls.conf = cp
        cls.archmap = {'ppc64': 'ppc', 'x86_64': 'i686'}
        cls.revarchmap = dict((v, k) for k, v in cls.archmap.items())

    def disable_test(self):
        def wrapper(func):
             func.__test__ = False
             return func
        return wrapper

    def print_fpo(self, fpo):
        fpod = fpo.convert()
        return '%s.%s' % (fpod['name'], fpod['arch'])

    def confirm_true(self, fpo, meth, msg='should be true'):
        """confirm that a package is multilib in code and in test data"""
        code = meth.select(fpo)
        key = '%s.%s' % (fpo.name, fpo.arch)
        msg += ' (%s)' % self.print_fpo(fpo)
        print key
        print '  code says %s' % code
        if meth.name == 'devel':
            # the data assumes the 'devel' method was used in compose
            if fpo.arch in self.archmap.keys():
                # this is 64-bit
                key32 = '%s.%s' % (fpo.name, self.archmap[fpo.arch])
                data = self.packages.has_key(key32)
            else:
                # this is a 32-bit package
                key64 = '%s.%s' % (fpo.name, self.revarchmap[fpo.arch])
                data = self.packages.has_key(key64)
            print '  data says %s' % data
            assert code and data, msg
        assert code, msg

    def confirm_false(self, fpo, meth, msg='should be false'):
        """confirm that a package is NOT multilib in code and in test data"""
        code = not meth.select(fpo)
        key = '%s.%s' % (fpo.name, fpo.arch)
        msg += ' (%s)' % self.print_fpo(fpo)
        print key
        print '  code says %s' % code
        if meth.name == 'devel':
            # the data assumes the 'devel' method was used in compose
            if fpo.arch in self.archmap.keys():
                # this is 64-bit
                key32 = '%s.%s' % (fpo.name, self.archmap[fpo.arch])
                data = self.packages.has_key(key32)
            else:
                # this is a 32-bit package
                key64 = '%s.%s' % (fpo.name, self.revarchmap[fpo.arch])
                data = self.packages.has_key(key64)
            print '  data says %s' % data
            assert code and data, msg
        assert code, msg

    def do_runtime(self, fpo, meth):
        sect = 'runtime'
        wl = self.conf.get(sect, 'white')
        bl = self.conf.get(sect, 'black')
        if fpo.name in bl:
            self.confirm_false(fpo, meth, 'Blacklisted, should be False')
            return True
        if fpo.name in wl:
            self.confirm_true(fpo, meth, 'Whitelisted, should be True')
            return True
        if fpo.arch.find('64') != -1:
            if fpo.name in meth.PREFER_64:
                self.confirm_true(fpo, meth, 'preferred 64-bit, should be True')
                return True
            if fpo.name.startswith('kernel'):
                provides = False
                for (p_name, p_flag, (p_e, p_v, p_r)) in fpo.provides:
                    if p_name == 'kernel' or p_name == 'kernel-devel':
                        provides = True
                if provides:
                    self.confirm_true(fpo, meth, '64-bit kernel, should be True')
                    return True
        if fpo.name.startswith('kernel'):
            # looks redundant, but we're not 64-bit here
            for (p_name, p_flag, (p_e, p_v, p_r)) in fpo.provides:
                if p_name == 'kernel':
                    self.confirm_false(fpo, meth, '32-bit kernel should be False')
                    return # this is here intentionally
        for file in fpo.returnFileEntries():
            (dirname, filename) = file.rsplit('/', 1)
            # libraries in standard dirs
            if dirname in meth.LIBDIRS and fnmatch(filename, '*.so.*'):
                self.confirm_true(fpo, meth, '.so.x files, should be True')
                return True
            if dirname in meth.by_dir:
                self.confirm_true(fpo, meth, 'std dirs, should be True')
                return True
            # mysql, qt, etc.
            if dirname == '/etc/ld.so.conf.d' and filename.endswith('.conf'):
                self.confirm_true(fpo, meth, 'ld config, should be True')
                return True
            # nss (Some nss modules end in .so instead of .so.X)
            # db (db modules end in .so instead of .so.X)
            if dirname in meth.ROOTLIBDIRS and (filename.startswith('libnss_') or filename.startswith('libdb-')):
                self.confirm_true(fpo, meth, '.so files, should be True: %s')
                return True
            # Optimization:
            # All tests beyond here are for things in USRLIBDIRS
            if not dirname.startswith(tuple(meth.USRLIBDIRS)):
                # The dirname does not start with a USRLIBDIR so we can move
                # on to the next file
                continue
            if dirname.startswith(('/usr/lib/gtk-2.0', '/usr/lib64/gtk-2.0')):
                # gtk2-engines
                if fnmatch(dirname, '/usr/lib*/gtk-2.0/*/engines'):
                    self.confirm_true(fpo, meth, 'gtk2 engines should be True')
                    return True
                # accessibility
                if fnmatch(dirname, '/usr/lib*/gtk-2.0/*/modules'):
                    self.confirm_true(fpo, meth, 'gtk accessibility should be True')
                    return True
                # scim-bridge-gtk
                if fnmatch(dirname, '/usr/lib*/gtk-2.0/*/immodules'):
                    self.confirm_true(fpo, meth, 'scim-bridge-gtk should be True')
                    return True
                # images
                if fnmatch(dirname, '/usr/lib*/gtk-2.0/*/loaders'):
                    self.confirm_true(fpo, meth, 'image loaders should be True')
                    return True
                if fnmatch(dirname, '/usr/lib*/gtk-2.0/*/printbackends'):
                    self.confirm_true(fpo, meth, 'image backends should be True')
                    return True
                if fnmatch(dirname, '/usr/lib*/gtk-2.0/*/filesystems'):
                    self.confirm_true(fpo, meth, 'gtk filesystems should be True')
                    return True
                # Optimization:
                # No tests beyond here for things in /usr/lib*/gtk-2.0
                continue
            # gstreamer
            if dirname.startswith(('/usr/lib/gstreamer-', '/usr/lib64/gstreamer-')):
                self.confirm_true(fpo, meth, 'gstreamer should be True')
                return True
            # qt/kde fun
            if fnmatch(dirname, '/usr/lib*/qt*/plugins/*'):
                self.confirm_true(fpo, meth, 'qt plugins should be True')
                return True
            if fnmatch(dirname, '/usr/lib*/kde*/plugins/*'):
                self.confirm_true(fpo, meth, 'kde plugins should be True')
                return True
            # qml
            if fnmatch(dirname, '/usr/lib*/qt5/qml/*'):
                seflf.confirm_true(fpo, meth, 'qml should be True')
                return True
            # images
            if fnmatch(dirname, '/usr/lib*/gdk-pixbuf-2.0/*/loaders'):
                self.confirm_true(fpo, meth, 'gdk-pixbuf should be True')
                return True
            # xine-lib
            if fnmatch(dirname, '/usr/lib*/xine/plugins/*'):
                assert self.confirm_true(fpo, meth, 'xine-lib should be True')
                return True
            # oprofile
            if dirname in meth.OPROFILEDIRS and fnmatch(filename, '*.so.*'):
                self.confirm_true(fpo, meth, 'oprofile should be True')
                return True
            # wine
            if dirname in meth.WINEDIRS and filename.endswith('.so'):
                self.confirm_true(fpo, meth, 'wine .so should be True')
                return True
            # sane drivers
            if dirname in meth.SANEDIRS and filename.startswith('libsane-'):
                self.confirm_true(fpo, meth, 'sane drivers should be True')
                return True

    # test methods executed by nose start here

    def test_no(self):
        meth = multilib.NoMultilibMethod(None)
        for pinfo in self.packages.values():
            fpo = fakepo.FakePackageObject(d=pinfo)
            self.confirm_false(fpo, meth)

    def test_all(self):
        meth = multilib.AllMultilibMethod(None)
        for pinfo in self.packages.values():
            fpo = fakepo.FakePackageObject(d=pinfo)
            self.confirm_true(fpo, meth)

    def test_kernel(self):
        meth = multilib.KernelMultilibMethod(None)
        for pinfo in self.packages.values():
            fpo = fakepo.FakePackageObject(d=pinfo)
            if fpo.arch.find('64') != -1:
                if fpo.name.startswith('kernel'):
                    provides = False
                    for (p_name, p_flag, (p_e, p_v, p_r)) in fpo.provides:
                        if p_name == 'kernel' or p_name == 'kernel-devel':
                            provides = True
                    if provides:
                        self.confirm_true(fpo, meth)
                        continue
            self.confirm_false(fpo, meth)

    def test_yaboot(self):
        meth = multilib.YabootMultilibMethod(None)
        for pinfo in self.packages.values():
            fpo = fakepo.FakePackageObject(d=pinfo)
            if fpo.arch == 'ppc' and fpo.name.startswith('yaboot'):
                self.confirm_true(fpo, meth)
            else:
                self.confirm_false(fpo, meth)

    # if using mash.multlib, uncomment this. Test is known to fail since the input file
    # format changed in python-multilib
    # @disable_test
    def test_file(self):
        sect = 'runtime'
        self.list = self.conf.get(sect, 'white')
        meth = multilib.FileMultilibMethod(sect)
        for pinfo in self.packages.values():
            fpo = fakepo.FakePackageObject(d=pinfo)
            for item in meth.list:
                if fnmatch(fpo.name, item):
                    self.confirm_true(fpo, meth)
                    continue
            self.confirm_false(fpo, meth)

    def test_runtime(self):
        fco = fakeco.FakeConfigObject(self.conf)
        meth = multilib.RuntimeMultilibMethod(fco)
        for pinfo in self.packages.values():
            fpo = fakepo.FakePackageObject(d=pinfo)
            if not self.do_runtime(fpo, meth):
                self.confirm_false(fpo, meth)

    def test_devel(self):
        sect = 'devel'
        wl = self.conf.get(sect, 'white')
        bl = self.conf.get(sect, 'black')
        fco = fakeco.FakeConfigObject(self.conf)
        meth = multilib.DevelMultilibMethod(fco)
        for pinfo in self.packages.values():
            fpo = fakepo.FakePackageObject(d=pinfo)
            if fpo.name in bl:
                self.confirm_false(fpo, meth, 'Blacklisted, should be False')
                continue
            if fpo.name in wl:
                self.confirm_true(fpo, meth, 'Whitelisted, should be True')
                continue
            if self.do_runtime(fpo, meth):
                # returns True if a value was identified and asserted, False otherwise
                continue
            if fpo.name.startswith('ghc-'):
                self.confirm_false(fpo, meth, 'ghc package, should be False')
                continue
            if fpo.name.startswith('kernel'):
                # looks redundant, but we're not 64-bit here
                for (p_name, p_flag, (p_e, p_v, p_r)) in fpo.provides:
                    if p_name == 'kernel-devel':
                        self.confirm_false(fpo, meth, 'kernel-devel, should be False')
                        continue
                    if p_name.endswith('-devel') or p_name.endswith('-static'):
                        self.confirm_true(fpo, meth, 'kernel-*-devel, should be True')
                        continue
            if fpo.name.endswith('-devel'):
                self.confirm_true(fpo, meth, '-devel package, should be True')
                continue
            if fpo.name.endswith('-static'):
                self.confirm_true(fpo, meth, '-static package, should be True')
                continue
            self.confirm_false(fpo, meth)