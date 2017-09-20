#!/usr/bin/env python2

'''
list-installs.py - Show all known ansible installation paths
'''

import os
import pip
import stat
import subprocess
import tempfile
from pprint import pprint

SITE_SCRIPTS = [
    '''"import site; print(';'.join(site.getsitepackages()))"''',
    '''"import distutils.sysconfig; print(distutils.sysconfig.get_python_lib())"'''
]

ANSIBLE_HOME_SCRIPT = '''import ansible; print(ansible.__file__)'''
ANSIBLE_HOME_SCRIPT_SP = '''import sys; sys.path.insert(0, '%s'); import ansible; print(ansible.__file__)'''
ANSIBLE_LIBRARY_SCRIPT = '''from ansible import constants; print(constants.DEFAULT_MODULE_PATH)'''


def run_command(args):
    p = subprocess.Popen(args,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         shell=True)
    (so, se) = p.communicate()
    return (p.returncode, so, se)


class AnsibleInstallLister(object):
    def __init__(self):
        self.paths = self.get_paths()
        print("## $PATH")
        pprint(self.paths)
        self.python_paths = self.get_python_paths()
        print("## PYTHON PATHS")
        pprint(self.python_paths)
        self.site_packages_paths = self.get_site_packages_paths()
        print("## SITE-PACKAGES")
        pprint(self.site_packages_paths)
        self.ansible_paths = self.get_ansible_paths()
        print("## ANSIBLE PATHS")
        pprint(self.ansible_paths)
        self.ansible_homedirs = self.get_ansible_homedirs()
        print("## ANSIBLE HOME DIRS")
        pprint(self.ansible_homedirs)
        self.ansible_moduledirs = self.get_ansible_moduledirs()
        print("## ANSIBLE LIBRARY PATHS")
        pprint(self.ansible_moduledirs)
        print("## PYTHON MODULES ##")
        self.python_modules = self.get_python_modules()
        pprint(self.python_modules)

    def get_paths(self):
        """List user's environment path(s)"""
        paths = []
        rawpath = os.environ.get('PATH', '')
        for rp in rawpath.split(os.pathsep):
            path = os.path.expanduser(rp)
            paths.append(path)
        return paths

    def get_python_paths(self):
        ppaths = []
        for path in self.paths:
            if not os.path.exists(path):
                continue
            pfiles = os.listdir(path)
            for pf in pfiles:
                if 'pythonw' in pf:
                    continue
                if pf.endswith('-config'):
                    continue
                if pf.endswith('-build'):
                    continue
                if '-' in pf:
                    continue
                if pf.startswith('python'):
                    ppaths.append(os.path.join(path, pf))
        return ppaths

    def get_site_packages_paths(self):
        site_paths = []
        for ppath in self.python_paths:
            for SITE_SCRIPT in SITE_SCRIPTS:
                cmd = ppath + ' -c %s' % SITE_SCRIPT
                (rc, so, se) = run_command(cmd)
                if rc != 0:
                    continue
                xpaths = so.split(';')
                for xpath in xpaths:
                    xpath = xpath.strip()
                    site_paths.append(xpath)
        site_paths = sorted(set(site_paths))
        return site_paths

    def get_ansible_paths(self):
        apaths = []
        for path in self.paths:
            checkfile = os.path.join(path, 'ansible')
            if os.path.exists(checkfile):
                checkfile = os.path.realpath(checkfile)
                apaths.append(checkfile)
        return apaths

    def get_ansible_homedirs(self):
        home_dirs = []
        for ap in self.ansible_paths:
            shebang = self.read_file_lines(ap)
            if not shebang:
                continue
            shebang = shebang.strip()

            scripts = []
            if 'python' in shebang.lower():

                # run with default sys.path
                scripts.append(shebang + '\n' + ANSIBLE_HOME_SCRIPT)

                # try combination of this shebang plus all known site-packages
                for sp in self.site_packages_paths:
                    sp_script = shebang + '\n' + ANSIBLE_HOME_SCRIPT_SP % sp
                    scripts.append(sp_script)

            elif 'bash' in shebang:
                scripts.append(self.get_homebrew_script(ap))

            for script in scripts:
                output = self.run_script(script)
                if not output:
                    continue
                output = output.strip()
                if not output.endswith('.pyc'):
                    continue
                hd = os.path.dirname(output)
                home_dirs.append(hd)

        home_dirs = sorted(set(home_dirs))
        return home_dirs

    def get_homebrew_script(self, binpath, pyscript=None):
        """homebrew handler ... make assumptions"""
        lines = self.read_file_lines(binpath, lines=2)
        lines = lines.split('\n')
        brewcmd = lines[1].strip()
        cparts = brewcmd.split()
        PYPATH = [x for x in cparts if 'PYTHONPATH' in x]
        if not PYPATH:
            return None
        PYPATH = PYPATH[0]
        script = lines[0] + '\n'
        script += PYPATH
        script += ' '
        if pyscript:
            script += '/usr/bin/python -c "' + pyscript + '"'
        else:
            script += '/usr/bin/python -c "' + ANSIBLE_HOME_SCRIPT + '"'
        return script

    def run_script(self, script):
        fo, fn = tempfile.mkstemp()
        with open(fn, 'wb') as f:
            f.write(script)
        os.close(fo)
        st = os.stat(fn)
        os.chmod(fn, st.st_mode | stat.S_IEXEC)
        (rc, so, se) = run_command(fn)
        os.remove(fn)
        return str(so) + str(se)

    def read_file_lines(self, filename, lines=1):
        data = ''
        with open(filename, 'rb') as f:
            for x in xrange(0, lines):
                data += f.readline()
        return data

    def get_ansible_moduledirs(self):

        library_paths = []
        for hpath in self.ansible_homedirs:
            checkpath = os.path.join(hpath, 'modules')
            if os.path.exists(checkpath):
                library_paths.append(checkpath)
        library_paths = sorted(set(library_paths))
        return library_paths

    def get_python_modules(self):
        installed_packages = pip.get_installed_distributions()
        installed_packages_list = sorted(["%s==%s" % (i.key, i.version) for i in installed_packages])

        return installed_packages_list


if __name__ == "__main__":
    AnsibleInstallLister()
