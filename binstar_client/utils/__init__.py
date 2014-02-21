'''
Created on Apr 29, 2013

@author: sean
'''

from hashlib import md5
from os.path import exists, join, dirname, expanduser, isfile, isdir
import appdirs
import base64
import getpass
import os
import urlparse
import yaml
import sys

from ..errors import UserError
import json
import time
import urllib
import logging

def upload_print_callback(args):
    
    start_time = time.time()
    
    if args.no_progress or args.log_level >= logging.INFO:
        return lambda curr, total: None
    
    def callback(curr, total):
        curr_time = time.time()
        time_delta = curr_time - start_time

        remain = total - curr
        if curr and remain:
            eta = 1.0 * time_delta / curr * remain / 60.0
        else:
            eta = 0

        curr_kb = curr // 1024
        total_kb = total // 1024
        perc = 100.0 * curr / total if total else 0

        msg = '\r uploaded %(curr_kb)i of %(total_kb)iKb: %(perc).2f%% ETA: %(eta).1f minutes'
        sys.stderr.write(msg % locals())
        sys.stderr.flush()
        if curr == total:
            sys.stderr.write('\n')

    return callback


def jencode(*E, **F):
    return base64.b64encode(json.dumps(dict(*E, **F)))

def pv(version):
    return tuple(int(x) for x in version.split('.'))

class PackageSpec(object):
    def __init__(self, user, package, version=None, basename=None, attrs=None, spec_str=None):
        self._user = user
        self._package = package
        self._version = version
        self._basename = basename
        self.attrs = attrs
        self.spec_str = spec_str

    def __str__(self):
        return self.spec_str

    def __repr__(self):
        return '<PackageSpec %r>' % (self.spec_str)

    @property
    def user(self):
        if self._user is None:
            raise UserError('user not given (got %r expected <username> )' % (self.spec_str,))
        return self._user

    @property
    def name(self):
        if self._package is None:
            raise UserError('package not given in spec (got %r expected <username>/<package> )' %(self.spec_str, ))
        return self._package
    
    @property
    def package(self):
        if self._package is None:
            raise UserError('package not given in spec (got %r expected <username>/<package> )' % (self.spec_str,))
        return self._package

    @property
    def version(self):
        if self._version is None:
            raise UserError('version not given in spec (got %r expected <username>/<package>/<version> )' % (self.spec_str,))
        return self._version

    @property
    def basename(self):
        if self._basename is None:
            raise UserError('basename not given in spec (got %r expected <username>/<package>/<version>/<filename> )' % (self.spec_str,))
        return self._basename

def package_specs(spec):
    user = spec
    package = None
    attrs = {}
    if '/' in user:
        user, package = user.split('/',1)
    if '/' in package:
        raise TypeError('invalid package spec')
        
    return PackageSpec(user, package, None, None, attrs, spec)

def parse_specs(spec):
    user = spec
    package = version = basename = None
    attrs = {}
    if '/' in user:
        user, package = user.split('/', 1)
    if package and '/' in package:
        package, version = package.split('/', 1)

    if version and '/' in version:
        version, basename = version.split('/', 1)

    if basename and '?' in basename:
        basename, qsl = basename.rsplit('?', 1)
        attrs = dict(urlparse.parse_qsl(qsl))

    return PackageSpec(user, package, version, basename, attrs, spec)


def get_binstar(args=None):
    from binstar_client import Binstar

    config = get_config()
    url = config.get('url', 'https://api.binstar.org')
    
    if args and args.token:
        token = args.token
    else:
        data_dir = appdirs.user_data_dir('binstar', 'ContinuumIO')
        tokenfile = join(data_dir, '%s.token' % urllib.quote_plus(url))
        if isfile(tokenfile):
            with open(tokenfile) as fd:
                token = fd.read()
        else:
            token = None
            
    return Binstar(token, domain=url,)

def store_token(token):
    config = get_config()
    url = config.get('url', 'https://api.binstar.org')

    data_dir = appdirs.user_data_dir('binstar', 'ContinuumIO')
    if not isdir(data_dir):
        os.makedirs(data_dir)
    tokenfile = join(data_dir, '%s.token' % urllib.quote_plus(url))
    
    with open(tokenfile, 'wb') as fd:
        fd.write(token)

def remove_token():
    config = get_config()
    url = config.get('url', 'https://api.binstar.org')
    data_dir = appdirs.user_data_dir('binstar', 'ContinuumIO')
    tokenfile = join(data_dir, '%s.token' % urllib.quote_plus(url))
    
    if isfile(tokenfile):
        os.unlink(tokenfile)
    
def load_config(config_file):
    if exists(config_file):
        with open(config_file) as fd:
            data = yaml.load(fd)
            if data:
                return data

    return {}

SITE_CONFIG = join(appdirs.site_data_dir('binstar', 'ContinuumIO'), 'config.yaml')
USER_CONFIG = join(appdirs.user_data_dir('binstar', 'ContinuumIO'), 'config.yaml')
USER_LOGDIR = appdirs.user_log_dir('binstar', 'ContinuumIO')

def get_config(user=True, site=True):

    config = {}
    if site:
        config.update(load_config(SITE_CONFIG))
    if user:
        config.update(load_config(USER_CONFIG))

    return config

def set_config(data, user=True):

    config_file = USER_CONFIG if user else SITE_CONFIG

    data_dir = dirname(config_file)
    if not exists(data_dir):
        os.makedirs(data_dir)

    with open(config_file, 'w') as fd:
        yaml.dump(data, fd)



def compute_hash(fp, buf_size=8192, size=None, hash_algorithm=md5):
    hash_obj = hash_algorithm()
    spos = fp.tell()
    if size and size < buf_size:
        s = fp.read(size)
    else:
        s = fp.read(buf_size)
    while s:
        hash_obj.update(s)
        if size:
            size -= len(s)
            if size <= 0:
                break
        if size and size < buf_size:
            s = fp.read(size)
        else:
            s = fp.read(buf_size)
    hex_digest = hash_obj.hexdigest()
    base64_digest = base64.encodestring(hash_obj.digest())
    if base64_digest[-1] == '\n':
        base64_digest = base64_digest[0:-1]
    # data_size based on bytes read.
    data_size = fp.tell() - spos
    fp.seek(spos)
    return (hex_digest, base64_digest, data_size)


class upload_in_chunks(object):
    def __init__(self, fd, chunksize=1 << 13):
        self.fd = fd
        self.chunksize = chunksize
        self.totalsize = os.fstat(fd.fileno()).st_size
        self.readsofar = 0

    def __iter__(self):
        print 'Progress:'
        while True:
            data = self.fd.read(self.chunksize)
            if not data:
                sys.stderr.write("\n")
                break
            self.readsofar += len(data)
            percent = self.readsofar * 1e2 / self.totalsize
            sys.stderr.write("\r{percent:3.0f}%".format(percent=percent))
            yield data

    def __len__(self):
        return self.totalsize


def upload_with_progress(fd):
    it = upload_in_chunks(fd)
    IterableToFileAdapter(it)

class IterableToFileAdapter(object):
    def __init__(self, iterable):
        self.iterator = iter(iterable)
        self.length = len(iterable)

    def read(self, size= -1):  # TBD: add buffer for `len(data) > size` case
        return next(self.iterator, b'')

    def __len__(self):
        return self.length



def bool_input(prompt, default=True):
        default_str = '[Y|n]' if default else '[y|N]'
        while 1:
            inpt = raw_input('%s %s: ' % (prompt, default_str))
            if inpt.lower() in ['y', 'yes'] and not default:
                return True
            elif inpt.lower() in ['', 'n', 'no'] and not default:
                return False
            elif inpt.lower() in ['', 'y', 'yes']:
                return True
            elif inpt.lower() in ['n', 'no']:
                return False
            else:
                print 'please enter yes or no'
