"""Pin the existing HTTP-only host toolchain; never installs dependencies."""
import hashlib,json,os,shutil,stat,subprocess
from pathlib import Path
NODE_PATH=Path('/tmp/ns-m7-owned-dependencies-20261112/node_modules')
def need(ok,code):
    if not ok:raise RuntimeError(code)
def digest_file(path):
    h=hashlib.sha256();fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd);need(stat.S_ISREG(before.st_mode),'CLIENT_DEPENDENCY_FILE')
        while True:
            chunk=os.read(fd,1048576)
            if not chunk:break
            h.update(chunk)
        after=os.fstat(fd);need((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns),'CLIENT_DEPENDENCY_CHANGED')
        return h.hexdigest(),before
    finally:os.close(fd)
def capture(root=NODE_PATH):
    root=Path(root);need(root.is_dir()and root.resolve()==root,'CLIENT_DEPENDENCY_ROOT');binary=Path(shutil.which('node')).resolve();node_hash,_=digest_file(binary)
    git=Path(shutil.which('git')).resolve();git_hash,_=digest_file(git)
    version=subprocess.check_output([str(binary),'--version'],env={'PATH':str(binary.parent),'LANG':'C'},timeout=3).decode().strip()
    package=json.loads((root/'socket.io-client/package.json').read_bytes());need(package['version']=='4.8.3','CLIENT_STOCK_SOCKET_VERSION')
    h=hashlib.sha256();files=0;size=0
    for directory,dirs,names in os.walk(root,followlinks=False):
        dirs.sort();names.sort()
        # Symbolic directory entries are identity, never a new traversal root.
        for name in sorted(names+[d for d in dirs if (Path(directory)/d).is_symlink()]):
            file=Path(directory)/name;relative=str(file.relative_to(root));s=file.lstat();need(files<100000,'CLIENT_DEPENDENCY_FILE_BOUND');files+=1
            if stat.S_ISLNK(s.st_mode):
                target=file.resolve();need(target.is_relative_to(root),'CLIENT_DEPENDENCY_SYMLINK_ESCAPE');identity='link:'+os.readlink(file)
            else:
                identity,s=digest_file(file);size+=s.st_size;need(size<=1073741824,'CLIENT_DEPENDENCY_BYTE_BOUND')
            h.update((relative+'\0'+identity+'\0'+oct(s.st_mode&0o777)+'\n').encode())
    return {'gitBinary':str(git),'gitBinarySha256':git_hash,'nodeBinary':str(binary),'nodeBinarySha256':node_hash,'nodeVersion':version,'nodePath':str(root),'treeSha256':h.hexdigest(),'fileCount':files,'regularBytes':size,'stockSocketVersion':package['version'],'scope':'entire existing private host node_modules tree, no install or production-image dependency assumption'}
