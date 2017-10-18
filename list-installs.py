#!/usr/bin/env python2

'''
list-installs.py - Show all known ansible installation paths
'''

# ls -lh /usr/lib/python2.7/site-packages/ansible*
# ansible/
# ansible-2.4.0-py2.7.egg/
# ansible-2.4.0.0-py2.7.egg-info/
# ansible_tower_cli-3.2.0-py2.7.egg-info/


import glob
import logging
import os
import stat
import sys
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



class Args(object):
    debug = False


def run_command(args):
    p = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True
    )
    (so, se) = p.communicate()
    return (p.returncode, so, se)


class AnsibleInstallLister(object):

    ansible_paths = []
    ansible_homedirs = []
    ansible_moduledirs = []
    packages = {}
    paths = []
    python_paths = []
    site_packages_paths = []

    def __init__(self, args):

        self.args = args
        self.set_logger()

        print("## PACKAGES")
        self.packages = self.get_packages()
        pprint(self.packages)
        print("## $PATH")
        self.paths = self.get_paths()
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

    def set_logger(self):
        if hasattr(self.args, 'debug') and self.args.debug:
            logging.level = logging.DEBUG
        else:
            logging.level = logging.INFO

        logFormatter = \
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        rootLogger = logging.getLogger()

        if hasattr(self.args, 'debug') and self.args.debug:
            rootLogger.setLevel(logging.DEBUG)
        else:
            rootLogger.setLevel(logging.INFO)

        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(logFormatter)
        rootLogger.addHandler(consoleHandler)

    def get_packages(self):
        packages = {'rpm':[], 'pip': []}

        logging.debug('checking for rpm command')
        (rc, so, se) = run_command('which rpm')
        if rc == 0:
            (rc, so, se) = run_command('rpm -qa | egrep -i ^ansible')
            _packages = [x.strip() for x in so.split('\n') if x.strip()]
            for _p in _packages:

                data = {'version': _p}

                (rc, so, se) = run_command('rpm -qV {}'.format(_p))
                if so.strip():
                    data['verify'] = so.split('\n')
                else:
                    data['verify'] = []

                packages['rpm'].append(data)

        SITEDIRS = self.get_site_packages_paths()[:]
        SITEDIRS.append(None)
        locations = []

        logging.debug('getting pip paths')
        pips = self.get_pip_paths()

        for pip in pips:
            for SD in SITEDIRS:

                if SD is None:
                    cmd = '{} show -f ansible'.format(pip)
                else:
                    cmd = 'PYTHONUSERBASE={} {} show -f ansible'.format(SD, pip)

                logging.debug(cmd)
                (rc, so, se) = run_command(cmd)

                if rc == 0:

                    logging.debug(so)

                    version = None
                    prefix = None
                    filechecks = []

                    lines = so.split('\n')
                    infiles = False
                    for line in lines:

                        if line.startswith('Version:'):
                            version = line.split(None, 1)[-1].strip()
                            continue

                        if line.startswith('Location:'):
                            prefix = line.split(None, 1)[-1].strip()
                            continue

                        if line.startswith('Files:'):
                            infiles = True
                            continue

                        if infiles:
                            fp = line.strip()
                            fp = os.path.join(prefix, fp)

                            if not os.path.exists(fp):
                                filechecks.append('M {}'.format(fp))

                    if prefix not in locations:
                        data = {
                            'location': prefix,
                            'version': version,
                            'verify': filechecks
                        }
                        packages['pip'].append(data)
                        locations.append(prefix)

        return packages

    def get_paths(self):
        """List user's environment path(s)"""
        paths = []
        rawpath = os.environ.get('PATH', '')
        for rp in rawpath.split(os.pathsep):
            path = os.path.expanduser(rp)
            paths.append(path)
        return paths

    def get_pip_paths(self):
        pips = []
        paths = self.get_paths()
        for path in paths:
            fps = glob.glob('{}/pip*'.format(path))
            if fps:
                pips += fps
        return pips

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

        if self.site_packages_paths:
            return self.site_packages_paths

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

        (rc, so, se) = run_command('find /usr -type d -iname "site-packages"')
        site_paths += [x.strip() for x in so.split('\n') if x.strip()]

        (rc, so, se) = run_command('find /lib* -type d -iname "site-packages"')
        site_paths += [x.strip() for x in so.split('\n') if x.strip()]

        (rc, so, se) = run_command('find ~ -type d -iname "site-packages"')
        site_paths += [x.strip() for x in so.split('\n') if x.strip()]

        (rc, so, se) = run_command('find /var/lib/awx/venv -type d -iname "site-packages"')
        site_paths += [x.strip() for x in so.split('\n') if x.strip()]

        for hd in site_paths[:]:
            gf = glob.glob('{}*egg*'.format(hd))
            if gf:
                site_paths += gf

        # hack for jtanner's machine
        site_paths = [x for x in site_paths if '/workspace' not in x]

        site_paths = sorted(set(site_paths))

        self.site_packages_paths = site_paths
        return site_paths

    def get_ansible_paths(self):
        paths = self.paths

        # pip install --user
        local_bin = os.path.expanduser('~/.local/bin')
        if local_bin not in paths:
            paths.append(local_bin)

        # tower
        (rc, so, se) = run_command('find /var/lib/awx/venv -type d -iname bin')
        if rc == 0:
            _paths = so.split('\n')
            _paths = [x.strip() for x in _paths if x.strip()]
            paths += _paths

        # look for venv bin dirs near the lib dir
        if self.site_packages_paths:
            for spp in self.site_packages_paths:
                if not spp or '/lib' not in spp:
                    continue
                spp_parts = [x for x in spp.split('/') if x]
                ix = [n for n, l in enumerate(spp_parts) if l.startswith('lib')]
                if ix:
                    binpath = '/'.join(spp_parts[:ix[0]] + ['bin'])
                    if os.path.isdir(binpath):
                        paths.append(binpath)
                #import epdb; epdb.st()

        apaths = []
        for path in paths:

            checkfile = os.path.join(path, 'ansible')
            gfs = glob.glob(checkfile + '*')
            if gfs:
                for gf in gfs:
                    rp = os.path.realpath(gf)
                    if rp != gf:
                        apaths.append('{} -> {}'.format(gf, rp))
                    else:
                        apaths.append(gf)

        return apaths

    def get_ansible_homedirs(self):
        home_dirs = []
        for ap in self.ansible_paths:
            if ap is None:
                continue
            if '->' in ap:
                ap = ap.split('->')[-1].strip()
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
                if script is None:
                    continue
                output = self.run_script(script)
                if not output:
                    continue
                output = output.strip()
                if not output.endswith('.pyc'):
                    continue
                hd = os.path.dirname(output)
                home_dirs.append(hd)

        home_dirs = sorted(set(home_dirs))

        #for hd in home_dirs[:]:
        #    gf = glob.glob('{}*egg*'.format(hd))
        #    if gf:
        #        home_dirs += gf

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


if __name__ == "__main__":

    args = Args()
    if '--debug' in sys.argv:
        args.debug = True

    AnsibleInstallLister(args)
